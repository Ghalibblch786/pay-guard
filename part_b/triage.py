"""Triage pipeline for ONE complaint: sanitize -> (flagged? route to a human, no model) -> local model with schema enforcement and
bounded retries -> safety rules -> record. Every input produces exactly one record; any failure becomes a safe fallback.
"""
import hashlib, json, time
from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from part_b.llm_client import TransportError
from part_b.prompts import TAXONOMY, build_messages
from part_b.safety_rules import fired_rules
from part_b.sensitive_flags import is_sensitive_failclosed

MAX_ATTEMPTS = 3
Category = Enum("Category", {c["id"]: c["id"] for c in TAXONOMY["categories"]}, type=str)


class ModelTriage(BaseModel):
    """What the model must return. Unknown fields, invented categories and wrong types are rejected."""
    model_config = ConfigDict(extra="forbid", strict=False)
    category: Category
    urgency: Literal["low", "medium", "high"]
    summary: str = Field(min_length=10, max_length=600)
    requires_human: bool = Field(strict=True)
    confidence_note: str = Field(min_length=5, max_length=400)


class TriageRecord(ModelTriage):
    """The pipeline's output: the five required fields plus how they were produced."""
    requires_human: bool
    route: Literal["model", "flagged_human_only", "fallback"]
    model_requires_human: Optional[bool] = None     # the model's own answer, before safety rules
    safety_rules: list = Field(default_factory=list)
    flagged: bool = False
    attempts: int = 0
    errors: list = Field(default_factory=list)      # short error codes, never complaint text
    prompt_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0                          # model time of all attempts
    cached: bool = False


def _human_record(route: str, note: str, **extra) -> TriageRecord:
    """Safe record when there is no model answer. 'high' is a placeholder so it is not queued last, not an assessment."""
    return TriageRecord(category="other", urgency="high", summary="Not summarized automatically. A person must read this complaint.",
                        requires_human=True, confidence_note=note, route=route, **extra)


def _error_codes(error: ValidationError) -> list:
    """'field: error_type' only; pydantic messages can quote the model's output."""
    return [f"{'.'.join(map(str, e['loc'])) or 'json'}: {e['type']}" for e in error.errors()][:5]


def call_model(client, messages: list, sleep=time.sleep) -> tuple:
    """Bounded retries. Invalid output is retried WITH the validation errors fed back; transport errors with backoff.
    Returns (ModelTriage or None, stats)."""
    stats = {"attempts": 0, "errors": [], "prompt_tokens": 0, "output_tokens": 0, "latency_s": 0.0}
    conversation = list(messages)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        stats["attempts"] = attempt
        try:
            reply = client.chat(conversation, ModelTriage.model_json_schema())
        except TransportError as error:
            stats["errors"].append(f"transport: {error}")
            if attempt < MAX_ATTEMPTS:
                sleep(2 ** (attempt - 1))
            continue
        for key in ("prompt_tokens", "output_tokens", "latency_s"):
            stats[key] += reply[key]
        if reply["prompt_tokens"] >= client.options["num_ctx"] - client.options["num_predict"]:
            stats["errors"].append("input_too_long")             # the server would silently cut the text: do not trust the answer
            return None, stats
        try:
            if reply["done_reason"] == "length":
                stats["errors"].append("output_truncated")
            else:
                return ModelTriage.model_validate_json(reply["content"]), stats
            codes = ["output was cut off: be shorter"]
        except ValidationError as error:
            codes = _error_codes(error)
            stats["errors"].extend(codes)
        conversation = list(messages) + [{"role": "assistant", "content": reply["content"][:1500]},
                                         {"role": "user", "content": "That reply was invalid (" + "; ".join(codes) + "). Reply again with one valid JSON object only."}]
    return None, stats


class ResponseCache:
    """One JSON file per (model build, options, prompt messages). Holds model text, so it stays in a gitignored folder."""
    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def _path(self, key: str) -> Path:
        return self.folder / f"{key}.json"

    @staticmethod
    def key(model_digest: str, options: dict, messages: list) -> str:
        return hashlib.sha256(json.dumps([model_digest, options, messages], sort_keys=True).encode()).hexdigest()

    def get(self, key: str):
        return json.loads(self._path(key).read_text()) if self._path(key).is_file() else None

    def put(self, key: str, value: dict) -> None:
        self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._path(key).write_text(json.dumps(value))
        self._path(key).chmod(0o600)


def triage_one(raw_text: str, client, sanitize_fn, prompt_version: str = "v2", cache: ResponseCache = None, model_digest: str = "",
               sleep=time.sleep) -> TriageRecord:
    """sanitize_fn(raw) -> sanitized text, raising on failure. Never raises: problems become a fallback record."""
    rules, flagged = [], True
    try:
        rules = fired_rules(raw_text)
        flagged = is_sensitive_failclosed(raw_text)
        if flagged:                                              # D-23: no model call at all
            return _human_record("flagged_human_only", "Flagged as sensitive: not processed by a model.", flagged=True, safety_rules=rules)
        messages = build_messages(prompt_version, sanitize_fn(raw_text))
        key = ResponseCache.key(model_digest, client.options, messages) if cache else None
        hit = cache.get(key) if cache else None
        if hit:
            answer, stats = ModelTriage.model_validate(hit["answer"]), hit["stats"]
        else:
            answer, stats = call_model(client, messages, sleep=sleep)
            if cache and answer is not None:                     # failures are not cached, so a rerun tries again
                cache.put(key, {"answer": answer.model_dump(mode="json"), "stats": stats})
        if answer is None:
            return _human_record("fallback", "The model gave no valid answer: triage manually.", safety_rules=rules, **stats)
        data = answer.model_dump(mode="json")
        model_flag = data.pop("requires_human")
        return TriageRecord(**data, requires_human=model_flag or bool(rules), model_requires_human=model_flag, route="model",
                            safety_rules=rules, cached=bool(hit), **stats)
    except Exception as error:                                   # never drop a row; keep only the error type
        return _human_record("fallback", "The pipeline failed on this complaint: triage manually.", safety_rules=rules, flagged=flagged,
                             errors=[f"pipeline: {type(error).__name__}"])
