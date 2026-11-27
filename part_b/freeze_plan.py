"""Freeze the M3 plan by file hash, and make the local labeling pack (reading file + blank label sheet).

  python -I part_b/freeze_plan.py freeze <version>          # writes part_b/m3_freeze_v<version>.json; never overwrites
  python -I part_b/freeze_plan.py label-pack <export.zip>   # requires a matching freeze

A later change to any frozen file means a NEW version (old freeze files are kept). The labeling files show sanitized text only:
no Complaint ID, no CFPB Product/Issue, no sensitivity flag. Prints counts only. No network, no LLM.
"""
import argparse, csv, datetime, hashlib, json, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from part_b import review_batches as rb
from part_b.eligibility import EligibilityError, fingerprint, load_eligible, sanitize_configured
from part_b.exclusions import ExclusionError, narrative_hash
from part_b.make_review_batch import _CONTROL, _write_new

ROOT = Path(__file__).resolve().parents[1]
FROZEN_FILES = ["part_b/taxonomy.json", "part_b/labeling_guide.md", "part_b/evaluation_plan.md", "part_b/make_slice.py",
                "part_b/signoff.json", "part_b/sample_record.json"]
LABEL_HEADER = "item,category,urgency,requires_human,ambiguous"
LABEL_BANNER = ("LOCAL ONLY. Sanitized narratives that may STILL contain personal information. Read in macOS Terminal with:\n"
                "  LESSHISTFILE=- less data/processed/labeling/items.txt   (never in VS Code; never copy, screenshot or upload). Do not edit.\n"
                "Label with part_b/labeling_guide.md into labels.csv, in order from item 1, without skipping. Label BEFORE seeing any model output.\n\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _versions(root: Path) -> dict:
    found = {}
    for p in (root / "part_b").glob("m3_freeze_v*.json"):
        m = re.fullmatch(r"m3_freeze_v(\d+)\.json", p.name)
        if m:
            found[int(m.group(1))] = p
    return found


def freeze(version: int, day: str, root: Path = ROOT) -> dict:
    existing = _versions(root)
    if version != max(existing, default=0) + 1:
        raise rb.BatchError("freeze versions must be consecutive and are never overwritten")
    if any(not (root / f).is_file() for f in FROZEN_FILES):
        raise rb.BatchError("a file to be frozen is missing")
    record = {"version": version, "date": day, "files": {f: _sha(root / f) for f in FROZEN_FILES}}
    with open(root / "part_b" / f"m3_freeze_v{version}.json", "x", encoding="utf-8") as f:
        f.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return record


def verify_freeze(root: Path = ROOT) -> dict:
    """The LATEST freeze must match every frozen file."""
    existing = _versions(root)
    if not existing:
        raise rb.BatchError("nothing has been frozen")
    record = json.loads(existing[max(existing)].read_text(encoding="utf-8"))
    if set(record["files"]) != set(FROZEN_FILES):
        raise rb.BatchError("the freeze does not cover the expected files")
    for f, digest in record["files"].items():
        if not (root / f).is_file() or _sha(root / f) != digest:
            raise rb.BatchError(f"frozen file changed or missing: {f}")
    return record


def make_label_pack(eligible, nlp, paths, root: Path = ROOT, sanitize_fn=sanitize_configured, fingerprint_fn=fingerprint, expected_n=60) -> dict:
    version = verify_freeze(root)["version"]
    record = json.loads(paths.sample_record.read_text(encoding="utf-8"))
    manifest_path = paths.sample_dir / "manifest.csv"
    if not manifest_path.is_file() or _sha(manifest_path) != record["manifest_sha256"]:
        raise rb.BatchError("the sample manifest is missing or has changed")
    if fingerprint_fn(eligible.protected, nlp) != record["fingerprint"]:
        raise rb.BatchError("code or configuration changed since sampling")
    with manifest_path.open(newline="", encoding="utf-8") as f:
        labelled = sorted((r for r in csv.DictReader(f) if r["label_position"]), key=lambda r: int(r["label_position"]))
    if [int(r["label_position"]) for r in labelled] != list(range(1, expected_n + 1)):
        raise rb.BatchError("the labeling order in the manifest is incomplete")
    by_hash = {narrative_hash(t): t for t in eligible.texts}
    if any(r["sha256"] not in by_hash for r in labelled):
        raise rb.BatchError("a sampled record is not in the eligible population")
    if os.path.lexists(paths.labeling_dir):
        raise rb.BatchError("labeling files already exist and will not be overwritten")
    items = LABEL_BANNER + "\n".join(
        f"=== ITEM {n} ===\n{_CONTROL.sub(' ', sanitize_fn(by_hash[r['sha256']], nlp, eligible.protected))}\n" for n, r in enumerate(labelled, 1))
    sheet = "\n".join([LABEL_HEADER] + [f"{n},,,," for n in range(1, expected_n + 1)]) + "\n"
    paths.labeling_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    _write_new(paths.labeling_dir / "items.txt", items)
    _write_new(paths.labeling_dir / "labels.csv", sheet)
    return {"freeze_version": version, "items": expected_n}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("command", choices=["freeze", "label-pack"]); ap.add_argument("arg")
    args = ap.parse_args(argv)
    try:
        if args.command == "freeze":
            result = {"frozen_version": freeze(int(args.arg), datetime.date.today().isoformat())["version"]}
        else:
            from part_b.sanitizer import load_nlp
            verify_freeze()
            result = make_label_pack(load_eligible(args.arg), load_nlp(), rb.DEFAULT_PATHS)
    except (rb.BatchError, EligibilityError, ExclusionError) as e:
        print(f"FAIL: {e}"); return 1
    except Exception as e:
        print(f"FAIL: unexpected {type(e).__name__} (details suppressed)"); return 1
    print("PASS")
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
