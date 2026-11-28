"""Run the invented demo complaints through the local model once and save the answers, so the dashboard can show
them when no model is running.   python -m app.save_demo
"""
import json

from app import engine
from part_b.eligibility import sanitize_configured
from part_b.llm_client import OllamaClient
from part_b.run_triage import FINAL_PROMPT
from part_b.sanitizer import load_nlp
from part_b.triage import triage_one


def main() -> None:
    cases = json.loads((engine.ROOT / "app" / "demo_cases.json").read_text())
    client, nlp = OllamaClient(), load_nlp()
    client.digest()                                   # stops here if the local model is not available
    saved = {}
    for case in cases:
        record = triage_one(case["text"], client, lambda raw: sanitize_configured(raw, nlp, set()), FINAL_PROMPT)
        if record.route == "fallback":
            raise SystemExit(f"no valid answer for '{case['title']}': {record.errors}. Nothing was saved.")
        saved[case["title"]] = record.model_dump(mode="json")
        print(f"{case['title']}: route={record.route} category={record.category.value} person={record.requires_human}")
    (engine.ROOT / "app" / "demo_saved.json").write_text(json.dumps(saved, indent=2))


if __name__ == "__main__":
    main()
