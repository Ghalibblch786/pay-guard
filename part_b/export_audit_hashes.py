"""D-29 step 1: save the hashes of the narratives reviewed in the flag audit, ONLY after proving which narratives those were.

The seeded selection is rebuilt in memory and must reproduce the existing local items file BYTE FOR BYTE; otherwise nothing is saved.
Reads the audit items file only to compare bytes; never opens the verdict sheet; never writes to the audit folder. Prints counts and PASS/FAIL only.

  python -I part_b/export_audit_hashes.py <export.zip>
"""
import datetime, hashlib, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from part_b.exclusions import DEFAULT_PATH, ExclusionError, add_exclusions, keep_mask, load_exclusions, narrative_hash
from part_b.flag_audit import OUT_DIR, build_audit

ACCEPTED_ZIP_SHA256 = "3021c8af9eeed4971a92f15be21c7ce08cf3c1337151de255e5b12bf782049df"   # SPECS D-16
SOURCE_TAG = "flag_audit"
N_AUDIT = 20


class VerificationError(RuntimeError):
    """Messages must never include file contents."""


def export(audit: dict, items_path: Path, out_path: Path, day: str, n_expected: int = N_AUDIT) -> dict:
    """Verify, then save. Raises BEFORE writing anything if any check fails. Returns aggregate counts only."""
    if not Path(items_path).is_file():
        raise VerificationError("audit items file is missing")
    if audit["items_text"].encode("utf-8") != Path(items_path).read_bytes():
        raise VerificationError("rebuilt selection does not match the existing items file byte for byte")
    hashes = {narrative_hash(t) for t in audit["chosen_texts"]}
    if len(audit["chosen_texts"]) != n_expected or len(hashes) != n_expected:
        raise VerificationError("unexpected number of distinct audit records")
    n_eligible = len(audit["eligible_texts"])
    n_matched = sum(narrative_hash(t) in hashes for t in audit["eligible_texts"])
    if n_matched != n_expected:                                  # each audit hash must hit exactly one eligible narrative
        raise VerificationError("audit hashes do not match the expected number of eligible records")
    added = add_exclusions(hashes, SOURCE_TAG, day, out_path)
    excluded = load_exclusions(out_path)
    n_kept = sum(keep_mask(audit["eligible_texts"], excluded))
    return {"audit_records_verified": len(hashes), "rows_added": added, "unique_hashes_in_file": len(excluded),
            "eligible_before": n_eligible, "eligible_excluded": n_eligible - n_kept, "eligible_after": n_kept}


def main(zip_path: str) -> int:
    try:
        if hashlib.sha256(Path(zip_path).read_bytes()).hexdigest() != ACCEPTED_ZIP_SHA256:
            raise VerificationError("archive is not the accepted D-16 file")
        counts = export(build_audit(zip_path), OUT_DIR / "flag_audit_items.txt", DEFAULT_PATH, datetime.date.today().isoformat())
    except (VerificationError, ExclusionError) as e:
        print(f"FAIL: {e}"); return 1
    except Exception as e:                                       # library errors can quote data: print the type only
        print(f"FAIL: unexpected {type(e).__name__} (details suppressed)"); return 1
    print("PASS: rebuilt selection matches the existing items file byte for byte")
    for k, v in counts.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
