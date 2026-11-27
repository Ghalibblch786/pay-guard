"""Batch tracking for the manual leak review (SPECS Step 3). Two records must agree, plus the exclusion file:
  - local ledger (gitignored): status, fingerprints, file hashes;
  - part_b/review_batches.json (meant to be tracked by git): batch number, date, seed, size, status, aggregate counts. No hashes, no text.
Anything missing, extra or inconsistent raises. There is deliberately no repair command: recovery needs the author's approval.
"""
import json, os, tempfile
from dataclasses import dataclass
from pathlib import Path

from part_b.exclusions import DEFAULT_PATH, load_by_source

ROOT = Path(__file__).resolve().parents[1]
BATCH_SIZE, MAX_BATCHES, N_AUDIT = 30, 3, 20
PUBLIC_FIELDS = ["batch", "date", "seed", "size", "status", "counts"]
LOCAL_FIELDS = PUBLIC_FIELDS + ["fingerprint", "guide_sha256", "archive_sha256", "pool_size", "items_sha256"]
STATUSES = {"reserved", "ready", "passed", "failed"}
RETEST_FILES = ["part_b/sanitizer.py", "part_b/sensitive_flags.py"]   # a retest needs a change in at least one of these


class BatchError(RuntimeError):
    """Messages must never include data."""


@dataclass(frozen=True)
class Paths:
    exclusions: Path = DEFAULT_PATH
    review_dir: Path = ROOT / "data" / "processed" / "sanitizer_review"
    tracked: Path = ROOT / "part_b" / "review_batches.json"
    guide: Path = ROOT / "part_b" / "review_guide.md"
    signoff: Path = ROOT / "part_b" / "signoff.json"                      # tracked: the final sign-off decision
    sample_dir: Path = ROOT / "data" / "processed" / "sample"             # local: manifest and pilot reading file
    sample_record: Path = ROOT / "part_b" / "sample_record.json"          # tracked: aggregate counts only
    labeling_dir: Path = ROOT / "data" / "processed" / "labeling"         # local: reading file and label sheet

    @property
    def ledger(self) -> Path:
        return self.review_dir / "ledger.json"


DEFAULT_PATHS = Paths()


def source_tag(k: int) -> str:
    return f"sanitizer_review_{k:02d}"


def batch_dir(paths: Paths, k: int) -> Path:
    return paths.review_dir / f"batch_{k:02d}"


def _read_json(path: Path, what: str) -> list:
    try:
        batches = json.loads(path.read_text(encoding="utf-8"))["batches"]
    except Exception:
        raise BatchError(f"{what} is missing or unreadable") from None
    if not isinstance(batches, list) or not all(isinstance(b, dict) for b in batches):
        raise BatchError(f"{what} is missing or unreadable")
    return batches


def _check_records(paths: Paths) -> list:
    public = _read_json(paths.tracked, "tracked batch log")
    local = _read_json(paths.ledger, "local batch ledger") if paths.ledger.exists() else []
    if any(set(b) != set(PUBLIC_FIELDS) for b in public) or any(set(b) != set(LOCAL_FIELDS) for b in local):
        raise BatchError("a batch record has missing or unexpected fields")
    if [{k: b[k] for k in PUBLIC_FIELDS} for b in local] != public:
        raise BatchError("local ledger and tracked batch log disagree")
    if [b["batch"] for b in local] != list(range(1, len(local) + 1)) or len(local) > MAX_BATCHES:
        raise BatchError("batch numbers have gaps, repeats or exceed the cap")
    if any(b["status"] not in STATUSES or b["size"] != BATCH_SIZE for b in local):
        raise BatchError("a batch record has an invalid status or size")
    if any(b["status"] != "failed" for b in local[:-1]):
        raise BatchError("only the latest batch may be anything other than failed")
    known = {batch_dir(paths, b["batch"]).name for b in local}
    if any(p.name.startswith("batch_") and p.name not in known for p in paths.review_dir.glob("*")):
        raise BatchError("a review folder exists that no record mentions")
    return local


def verify(paths: Paths) -> tuple:
    """(batches, set of excluded hashes), only if the audit and every recorded batch are completely excluded."""
    batches = _check_records(paths)
    by_source = load_by_source(paths.exclusions)                  # fails closed if missing or malformed
    expected = {"flag_audit": N_AUDIT, **{source_tag(b["batch"]): BATCH_SIZE for b in batches}}
    if set(by_source) != set(expected):
        raise BatchError("exclusion sources are missing or unknown")
    for source, n in expected.items():
        if len(by_source[source]) != n or len(set(by_source[source])) != n:
            raise BatchError("an exclusion source has the wrong number of records")
    everything = [h for hashes in by_source.values() for h in hashes]
    if len(set(everything)) != len(everything):
        raise BatchError("a record appears in more than one exclusion source")
    return batches, set(everything)


def _write_json(path: Path, batches: list, mode: int) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps({"batches": batches}, indent=2, sort_keys=True) + "\n")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def save(paths: Paths, batches: list) -> None:
    """Local first, then the tracked projection. A crash in between leaves them disagreeing, which blocks (fail closed)."""
    paths.review_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    _write_json(paths.ledger, batches, 0o600)
    _write_json(paths.tracked, [{k: b[k] for k in PUBLIC_FIELDS} for b in batches], 0o644)


def check_may_create(batches: list, fp: dict) -> None:
    if not batches:
        return
    status = batches[-1]["status"]
    if status in ("reserved", "ready"):
        raise BatchError("the previous batch is unfinished")
    if status == "passed":
        raise BatchError("the latest batch passed; a new batch needs the author's approval")
    if len(batches) >= MAX_BATCHES:
        raise BatchError("batch cap reached: stop and reconsider")
    for b in batches:                                             # compare with EVERY failed batch, so reverting is not a change
        if all(b["fingerprint"][f] == fp[f] for f in RETEST_FILES):
            raise BatchError("a retest needs a changed sanitizer or flagger")


def check_signoff(batches: list, fp: dict) -> None:
    """For later steps: raise unless the latest batch passed AND nothing that affects sanitizing or selection has changed since."""
    if not batches or batches[-1]["status"] != "passed":
        raise BatchError("no passed review batch")
    if batches[-1]["fingerprint"] != fp:
        raise BatchError("sign-off is invalid: code or configuration changed after the passed review")
