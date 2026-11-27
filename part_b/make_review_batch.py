"""Generate one local leak-review batch: 30 random UNFLAGGED, never-reviewed narratives, sanitized.

Order: verify -> select -> sanitize all in memory -> record 'reserved' -> save and re-verify exclusions -> write review files -> 'ready'.
So no review text reaches disk before its records are excluded. Prints counts only. No network, no LLM.

  python -I part_b/make_review_batch.py <export.zip>
"""
import datetime, hashlib, os, random, re, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import SEED
from part_b import review_batches as rb
from part_b.eligibility import EligibilityError, fingerprint, load_eligible, sanitize_configured
from part_b.exclusions import ExclusionError, add_exclusions, keep_mask, narrative_hash
from part_b.sensitive_flags import is_sensitive_failclosed

VERDICT_HEADER = "item,direct_leak,direct_types,indirect_concern,visible_sensitive,visible_sensitive_category"
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")          # untrusted text is read in a terminal: no escape sequences
BANNER = ("LOCAL ONLY. Sanitized text that may STILL contain personal information: treat it like raw data.\n"
          "Read in macOS Terminal with:  LESSHISTFILE=- less <this file>   (never in VS Code; never copy, screenshot or upload). Do not edit.\n"
          "Definitions and pass rule: part_b/review_guide.md. Record answers in verdicts.csv (fixed choices only).\n\n")


def batch_seed(k: int) -> str:
    return f"{SEED}-review-batch-{k:02d}"


def select(texts: list, excluded: set, seed: str, size: int = rb.BATCH_SIZE) -> tuple:
    """(chosen indices, pool size): simple random sample of narratives that are neither reviewed before nor flagged."""
    keep = keep_mask(texts, excluded)
    pool = [i for i, text in enumerate(texts) if keep[i] and not is_sensitive_failclosed(text)]
    if len(pool) < size:
        raise rb.BatchError("not enough unflagged, unreviewed records for a batch")
    return random.Random(seed).sample(pool, size), len(pool)


def _write_new(path: Path, content: str) -> None:
    with open(path, "x", encoding="utf-8", opener=lambda p, flags: os.open(p, flags, 0o600)) as f:
        f.write(content)


def create_batch(eligible, nlp, paths, day: str, sanitize_fn=sanitize_configured, fingerprint_fn=fingerprint) -> dict:
    if any(os.path.lexists(p) for p in (paths.signoff, paths.sample_dir, paths.sample_record)):
        raise rb.BatchError("the sign-off decision or sampling has happened: no new review batches (they could overlap the sample)")
    batches, excluded = rb.verify(paths)
    fp = fingerprint_fn(eligible.protected, nlp)
    rb.check_may_create(batches, fp)
    guide_sha = hashlib.sha256(paths.guide.read_bytes()).hexdigest()   # definitions are frozen before anything is read
    k = len(batches) + 1
    folder = rb.batch_dir(paths, k)
    if os.path.lexists(folder):
        raise rb.BatchError("review output already exists and will not be overwritten")
    chosen, pool_size = select(eligible.texts, excluded, batch_seed(k))
    hashes = {narrative_hash(eligible.texts[i]) for i in chosen}
    if len(hashes) != rb.BATCH_SIZE:
        raise rb.BatchError("selected records are not distinct")
    # ALL 30 must sanitize before anything is written; never silently replace a failing record.
    cleaned = [_CONTROL.sub(" ", sanitize_fn(eligible.texts[i], nlp, eligible.protected)) for i in chosen]
    items = BANNER + "\n".join(f"=== ITEM {n} ===\n{text}\n" for n, text in enumerate(cleaned, 1))
    sheet = "\n".join([VERDICT_HEADER] + [f"{n},,,,," for n in range(1, rb.BATCH_SIZE + 1)]) + "\n"

    entry = {"batch": k, "date": day, "seed": batch_seed(k), "size": rb.BATCH_SIZE, "status": "reserved", "counts": None,
             "fingerprint": fp, "guide_sha256": guide_sha, "archive_sha256": eligible.archive_sha256, "pool_size": pool_size, "items_sha256": None}
    batches = batches + [entry]
    rb.save(paths, batches)
    add_exclusions(hashes, rb.source_tag(k), day, paths.exclusions)
    _, now_excluded = rb.verify(paths)
    if not hashes <= now_excluded:
        raise rb.BatchError("exclusions were not saved completely")
    folder.mkdir(mode=0o700)
    _write_new(folder / "items.txt", items)
    _write_new(folder / "verdicts.csv", sheet)
    entry["items_sha256"] = hashlib.sha256((folder / "items.txt").read_bytes()).hexdigest()
    entry["status"] = "ready"
    rb.save(paths, batches)
    return {"batch": k, "records": rb.BATCH_SIZE, "unflagged_unreviewed_pool": pool_size, "eligible": len(eligible.texts),
            "records_by_product": dict(sorted(Counter(eligible.products[i] for i in chosen).items()))}


def main(zip_path: str) -> int:
    try:
        from part_b.sanitizer import load_nlp
        paths = rb.DEFAULT_PATHS
        rb.verify(paths)                                          # fail before reading the archive
        counts = create_batch(load_eligible(zip_path), load_nlp(), paths, datetime.date.today().isoformat())
    except (rb.BatchError, EligibilityError, ExclusionError) as e:
        print(f"FAIL: {e}"); return 1
    except Exception as e:                                        # library errors can quote data: print the type only
        print(f"FAIL: unexpected {type(e).__name__} (details suppressed)"); return 1
    print("PASS: batch ready for local review")
    for key, value in counts.items():
        print(f"{key}: {value}")
    print(f"folder: data/processed/sanitizer_review/batch_{counts['batch']:02d}/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
