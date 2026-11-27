"""Batch runner (B3, B4, B10). Real records stay local; the console shows operational counts only.

  python -m part_b.run_triage pilot|eval|main  --zip data/raw/CCDB_Export_19_June_2026.zip     # real records
  python -m part_b.run_triage dev|adversarial --prompt v1                                       # synthetic cases

For eval and main it deliberately prints NO category/urgency/summary information: labels must be made before model output is seen.
"""
import argparse, csv, json, statistics, sys, time
from collections import Counter
from pathlib import Path

from part_b.llm_client import DEFAULT_MODEL, DEFAULT_URL, OllamaClient
from part_b.triage import ResponseCache, triage_one

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "data" / "processed" / "runs"          # gitignored
SYNTHETIC = {"dev": ROOT / "part_b" / "dev_cases.jsonl", "adversarial": ROOT / "part_b" / "adversarial" / "cases.jsonl"}
FINAL_PROMPT = "v3"
MAX_SERVER_FAILURES = 3      # consecutive records lost to connection errors before the batch stops


class ServerDown(RuntimeError):
    pass


def lost_to_transport(record: dict) -> bool:
    return record["route"] == "fallback" and bool(record["errors"]) and record["errors"][-1].startswith("transport")


def load_real(subset: str, zip_path: str) -> tuple:
    """[(record key, raw text)] for the pilot, the 60 labeling items (in frozen order) or the 400 main records, plus the sanitizer."""
    from part_b import review_batches as rb
    from part_b.eligibility import load_eligible, sanitize_configured
    from part_b.exclusions import narrative_hash
    from part_b.freeze_plan import verify_freeze
    from part_b.sanitizer import load_nlp
    verify_freeze()
    eligible, nlp = load_eligible(zip_path), load_nlp()
    with (rb.DEFAULT_PATHS.sample_dir / "manifest.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    if subset == "eval":
        rows = sorted((r for r in rows if r["label_position"]), key=lambda r: int(r["label_position"]))
        keys = [r["label_position"] for r in rows]
    else:
        rows = [r for r in rows if r["role"] == subset]
        keys = [str(n) for n in range(1, len(rows) + 1)]
    by_hash = {narrative_hash(t): t for t in eligible.texts}
    return [(k, by_hash[r["sha256"]]) for k, r in zip(keys, rows)], lambda raw: sanitize_configured(raw, nlp, eligible.protected)


def load_synthetic(subset: str) -> tuple:
    from part_b.sanitizer import load_nlp, sanitize
    nlp = load_nlp()
    cases = [json.loads(line) for line in SYNTHETIC[subset].read_text().splitlines() if line.strip()]
    return [(c["id"], c["text"]) for c in cases], lambda raw: sanitize(raw, nlp=nlp).text


def run(records, sanitize_fn, client, prompt: str, out_path: Path, cache: ResponseCache, digest: str, progress_every: int = 20) -> list:
    out_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    results, started, down = [], time.time(), 0
    with out_path.open("w", encoding="utf-8") as f:
        out_path.chmod(0o600)
        for n, (key, raw) in enumerate(records, 1):
            record = triage_one(raw, client, sanitize_fn, prompt, cache, digest).model_dump(mode="json")
            results.append({"key": key, **record})
            f.write(json.dumps(results[-1]) + "\n"); f.flush()
            down = down + 1 if lost_to_transport(record) else (0 if record["attempts"] else down)     # flagged records say nothing about the server
            if down >= MAX_SERVER_FAILURES:
                raise ServerDown("the model server stopped responding; restart it and rerun (finished answers are cached)")
            if n % progress_every == 0:
                print(f"{n}/{len(records)} done, {time.time() - started:.0f}s", flush=True)
    return results


def operational_summary(results: list, wall_s: float) -> dict:
    """Aggregates that say nothing about what the model answered."""
    calls = [r for r in results if r["attempts"] and not r["cached"]]
    latency = sorted(r["latency_s"] for r in calls)
    return {"records": len(results), "routes": dict(Counter(r["route"] for r in results)),
            "model_calls_not_cached": len(calls), "records_needing_retry": sum(r["attempts"] > 1 for r in results),
            "error_codes": dict(Counter(e for r in results for e in r["errors"])),
            "latency_s": {"median": round(statistics.median(latency), 2), "p95": round(latency[int(0.95 * (len(latency) - 1))], 2),
                          "mean": round(statistics.mean(latency), 2)} if latency else None,
            "prompt_tokens_mean": round(statistics.mean(r["prompt_tokens"] for r in calls)) if calls else None,
            "output_tokens_mean": round(statistics.mean(r["output_tokens"] for r in calls)) if calls else None,
            "wall_seconds": round(wall_s, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("subset", choices=["pilot", "eval", "main", "dev", "adversarial"])
    ap.add_argument("--zip"); ap.add_argument("--prompt", default=FINAL_PROMPT); ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--url", default=DEFAULT_URL, help="local Ollama server (non-local addresses are refused)")
    args = ap.parse_args(argv)
    synthetic = args.subset in SYNTHETIC
    if not synthetic and not args.zip:
        ap.error("--zip is required for real records")
    try:
        client = OllamaClient(model=args.model, url=args.url)
        digest = client.digest()
        records, sanitize_fn = load_synthetic(args.subset) if synthetic else load_real(args.subset, args.zip)
        name = f"{args.subset}_{args.prompt}"
        started = time.time()
        results = run(records, sanitize_fn, client, args.prompt, RUNS / name / "results.jsonl", ResponseCache(RUNS / "cache"), digest)
        summary = {"subset": args.subset, "prompt": args.prompt, "model": args.model, "model_digest": digest, "options": client.options,
                   **operational_summary(results, time.time() - started)}
        (ROOT / "outputs" / f"m5_run_{name}.json").write_text(json.dumps(summary, indent=2))
    except ServerDown as e:
        print(f"FAIL: {e}"); return 1
    except Exception as e:
        print(f"FAIL: {type(e).__name__} (details suppressed)"); return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
