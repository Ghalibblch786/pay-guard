"""Validate a completed verdict sheet and report AGGREGATES ONLY. Never prints a cell's content (someone could paste private text into it).

  python -I part_b/summarize_review.py <batch number>            # preview: validates and shows counts, changes nothing
  python -I part_b/summarize_review.py <batch number> --record   # FINAL: stores the outcome; it cannot be changed afterwards
"""
import argparse, csv, hashlib, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from part_b import review_batches as rb
from part_b.exclusions import ExclusionError
from part_b.make_review_batch import VERDICT_HEADER
from part_b.sensitive_flags import CATEGORIES

DIRECT_TYPES = {"name", "email", "phone", "address", "account_or_card_number", "government_id", "birth_date", "handle_or_url", "other"}
VERDICTS = {"y", "n", "u"}
FINDINGS = ["direct_leak", "indirect_concern", "visible_sensitive"]
DETAIL = {"direct_leak": ("direct_types", DIRECT_TYPES), "visible_sensitive": ("visible_sensitive_category", set(CATEGORIES))}


def parse_verdicts(path: Path, size: int = rb.BATCH_SIZE) -> list:
    """Strictly validated rows. Errors name the row and column only."""
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        table = list(csv.reader(f))
    columns = VERDICT_HEADER.split(",")
    if not table or table[0] != columns:
        raise rb.BatchError("verdict sheet header is wrong")
    if len(table) - 1 != size:
        raise rb.BatchError("verdict sheet has the wrong number of rows")
    rows = []
    for n, cells in enumerate(table[1:], 1):
        if len(cells) != len(columns) or cells[0].strip() != str(n):
            raise rb.BatchError(f"row {n}: wrong item number or number of columns")
        row = {c: v.strip().lower() for c, v in zip(columns, cells)}
        for column in FINDINGS:
            if row[column] not in VERDICTS:
                raise rb.BatchError(f"row {n}: {column} must be y, n or u")
        for finding, (column, allowed) in DETAIL.items():
            values = [v.strip() for v in row[column].split(";") if v.strip()]
            if any(v not in allowed for v in values):
                raise rb.BatchError(f"row {n}: {column} has a value outside the fixed choices")
            if row[finding] == "y" and not values:
                raise rb.BatchError(f"row {n}: {column} is required when {finding} is y")
            if row[finding] == "n" and values:
                raise rb.BatchError(f"row {n}: {column} must be empty when {finding} is n")
            row[column] = sorted(set(values))
        rows.append(row)
    return rows


def aggregate(rows: list) -> dict:
    """Counts only. PASS RULE: every row is 'n' for all three findings; 'y' and 'u' both fail."""
    counts = {column: {v: sum(r[column] == v for r in rows) for v in ["y", "n", "u"]} for column in FINDINGS}
    for column, _ in DETAIL.values():
        counts[column] = dict(sorted(Counter(v for r in rows for v in r[column]).items()))
    counts["items_failing"] = sum(any(r[c] != "n" for c in FINDINGS) for r in rows)
    return counts


def summarize_batch(k: int, paths, record: bool) -> dict:
    batches, _ = rb.verify(paths)
    if not 1 <= k <= len(batches) or batches[k - 1]["status"] != "ready":
        raise rb.BatchError("this batch is not awaiting review (unknown, unfinished or already recorded)")
    entry, folder = batches[k - 1], rb.batch_dir(paths, k)
    items = folder / "items.txt"
    if not items.is_file() or hashlib.sha256(items.read_bytes()).hexdigest() != entry["items_sha256"]:
        raise rb.BatchError("review text file is missing or has changed")
    if hashlib.sha256(paths.guide.read_bytes()).hexdigest() != entry["guide_sha256"]:
        raise rb.BatchError("review definitions changed after this batch was generated")
    if not (folder / "verdicts.csv").is_file():
        raise rb.BatchError("verdict sheet is missing")
    counts = aggregate(parse_verdicts(folder / "verdicts.csv"))
    outcome = "passed" if counts["items_failing"] == 0 else "failed"
    if record:
        entry["status"], entry["counts"] = outcome, counts
        rb.save(paths, batches)
    return {"batch": k, "outcome": outcome, "recorded": record, "counts": counts}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("batch", type=int); ap.add_argument("--record", action="store_true")
    args = ap.parse_args(argv)
    try:
        result = summarize_batch(args.batch, rb.DEFAULT_PATHS, args.record)
    except (rb.BatchError, ExclusionError) as e:
        print(f"FAIL: {e}"); return 1
    except Exception as e:
        print(f"FAIL: unexpected {type(e).__name__} (details suppressed)"); return 1
    print(f"batch {result['batch']}: {result['outcome'].upper()} " + ("(recorded, final)" if result["recorded"] else "(PREVIEW only; nothing recorded)"))
    for key, value in result["counts"].items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
