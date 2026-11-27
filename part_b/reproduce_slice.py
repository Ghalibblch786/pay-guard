"""Rebuild the exact sample from the PUBLIC archive alone and check it against the recorded hash (B1).

The 50 reviewed records that were excluded are themselves reproducible: both review selections were seeded draws.
  python -m part_b.reproduce_slice data/raw/CCDB_Export_19_June_2026.zip
Writes data/processed/sample/manifest.csv only if it does not exist (needed by run_triage in a fresh clone). Prints counts only.
"""
import hashlib, json, os, sys

from part_b import review_batches as rb
from part_b.eligibility import load_eligible
from part_b.exclusions import narrative_hash
from part_b.flag_audit import build_audit
from part_b.make_review_batch import batch_seed, select
from part_b.make_slice import MANIFEST_FIELDS, _csv_text, draw


def manifest_text(eligible, d: dict) -> str:
    """Same rows and order as make_slice.create_sample (which is frozen, so it is mirrored here and checked by hash)."""
    label_at = {i: n for n, i in enumerate(d["label"], 1)}
    reserve_at = {i: n for n, i in enumerate(d["reserve"], 1)}
    rows = [[eligible.ids[i], narrative_hash(eligible.texts[i]), eligible.products[i], role, int(i in d["flagged"]), label_at.get(i, ""), reserve_at.get(i, "")]
            for role in ("pilot", "main") for i in d[role]]
    return _csv_text(MANIFEST_FIELDS, rows)


def main(zip_path: str) -> int:
    record = json.loads(rb.DEFAULT_PATHS.sample_record.read_text(encoding="utf-8"))
    eligible = load_eligible(zip_path)
    excluded = {narrative_hash(t) for t in build_audit(zip_path)["chosen_texts"]}          # 20 flag-audit records
    chosen, _ = select(eligible.texts, excluded, batch_seed(1))                            # 30 records of review batch 1
    excluded |= {narrative_hash(eligible.texts[i]) for i in chosen}
    text = manifest_text(eligible, draw(eligible.texts, eligible.products, excluded))
    matches = hashlib.sha256(text.encode()).hexdigest() == record["manifest_sha256"]
    print(f"excluded reviewed records rebuilt: {len(excluded)} | manifest rows: {text.count(chr(10)) - 1}")
    print("PASS: rebuilt sample matches the recorded manifest hash" if matches else "FAIL: rebuilt sample differs from the record")
    path = rb.DEFAULT_PATHS.sample_dir / "manifest.csv"
    if matches and not path.exists():
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(path, "x", encoding="utf-8", opener=lambda p, flags: os.open(p, flags, 0o600)) as f:
            f.write(text)
        print("wrote data/processed/sample/manifest.csv")
    return 0 if matches else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
