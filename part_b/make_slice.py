"""Record the sanitizer sign-off DECISION, then draw the pilot, the main sample and the labeling order (SPECS D-13, D-20, D-23, D-29).

  python -I part_b/make_slice.py decide <export.zip> --signed-off | --not-signed-off     # final, before sampling
  python -I part_b/make_slice.py sample <export.zip>

Reviewed records are excluded through the VERIFIED exclusion records. Flags are applied after the main draw (flagged records stay in it);
flagged pilot draws are replaced within the product. IDs, hashes and text stay in gitignored files; the tracked record has aggregates only.
Prints counts only. No network, no LLM.
"""
import argparse, csv, datetime, hashlib, io, json, os, random, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import SEED
from part_b import review_batches as rb
from part_b.eligibility import EligibilityError, fingerprint, load_eligible, sanitize_configured
from part_b.exclusions import ExclusionError, keep_mask, narrative_hash
from part_b.make_review_batch import _CONTROL, _write_new
from part_b.sensitive_flags import is_sensitive_failclosed

PILOT_PER_PRODUCT, MAIN_N, LABEL_N, RESERVE_N = 5, 400, 60, 20
MANIFEST_FIELDS = ["complaint_id", "sha256", "product", "role", "flagged", "label_position", "reserve_position"]
PILOT_BANNER = ("LOCAL ONLY. Pilot narratives, sanitized but they may STILL contain personal information. Read in macOS Terminal with:\n"
                "  LESSHISTFILE=- less data/processed/sample/pilot_items.txt   (never in VS Code; never copy, screenshot or upload)\n"
                "Purpose: check the draft categories and rules. Report problems with INVENTED examples only.\n\n")


# --- sign-off decision ---
def read_decision(paths) -> dict:
    try:
        decision = json.loads(paths.signoff.read_text(encoding="utf-8"))
        decision["decision"], decision["batch"], decision["fingerprint"]
    except Exception:
        raise rb.BatchError("the sign-off decision has not been recorded or is unreadable") from None
    if decision["decision"] not in ("signed_off", "not_signed_off"):
        raise rb.BatchError("the sign-off decision is invalid")
    return decision


def record_decision(protected, nlp, paths, signed_off: bool, day: str, fingerprint_fn=fingerprint) -> dict:
    """Signing off requires a passed latest batch AND unchanged code and configuration. Declining requires a finished review. Written once."""
    batches, _ = rb.verify(paths)
    if not batches or batches[-1]["status"] not in ("passed", "failed"):
        raise rb.BatchError("no finished review batch")
    if os.path.lexists(paths.signoff):
        raise rb.BatchError("a sign-off decision already exists and will not be overwritten")
    fp = fingerprint_fn(protected, nlp)
    if signed_off:
        rb.check_signoff(batches, fp)
    decision = {"decision": "signed_off" if signed_off else "not_signed_off", "date": day, "batch": batches[-1]["batch"],
                "batch_outcomes": [b["status"] for b in batches], "fingerprint": fp}
    with open(paths.signoff, "x", encoding="utf-8") as f:
        f.write(json.dumps(decision, indent=2, sort_keys=True) + "\n")
    return decision


# --- selection ---
def allocate(counts: dict, n: int) -> dict:
    """Proportional allocation of n by largest remainder (ties broken by name); the parts sum to exactly n."""
    total = sum(counts.values())
    if n > total:
        raise rb.BatchError("not enough records for the requested sample size")
    base = {k: n * v // total for k, v in counts.items()}
    order = sorted(counts, key=lambda k: (-(n * counts[k] % total), k))
    for k in order[: n - sum(base.values())]:
        base[k] += 1
    return base


def _sample(seed_name: str, items: list, k: int) -> list:
    return random.Random(f"{SEED}-{seed_name}").sample(items, k)


def _by_product(indices, products) -> dict:
    out: dict = {}
    for i in indices:
        out.setdefault(products[i], []).append(i)
    return dict(sorted(out.items()))


def draw(texts, products, excluded, is_flagged=is_sensitive_failclosed, main_n=MAIN_N, label_n=LABEL_N, reserve_n=RESERVE_N) -> dict:
    """Indices only. pilot: first 5 UNFLAGGED in a seeded random order per product; main: proportional random draw from the rest."""
    keep = keep_mask(texts, excluded)
    available = _by_product([i for i in range(len(texts)) if keep[i]], products)
    pilot, skipped = [], []                                   # skipped = (index, draw position) of flagged pilot draws that were replaced
    for product, indices in available.items():
        taken = 0
        for position, i in enumerate(_sample(f"pilot-{product}", indices, len(indices)), 1):
            if taken == PILOT_PER_PRODUCT:
                break
            if is_flagged(texts[i]):
                skipped.append((i, position))
            else:
                pilot.append(i); taken += 1
        if taken != PILOT_PER_PRODUCT:
            raise rb.BatchError("not enough unflagged records for the pilot")
    rest = {p: [i for i in idx if i not in set(pilot)] for p, idx in available.items()}   # replaced flagged draws stay eligible for main
    share = allocate({p: len(v) for p, v in rest.items()}, main_n)
    main = [i for p in rest for i in _sample(f"main-{p}", rest[p], share[p])]
    in_main = _by_product(sorted(main), products)
    label_share = allocate({p: len(v) for p, v in in_main.items()}, label_n)
    label = [i for p in in_main for i in _sample(f"label-{p}", in_main[p], label_share[p])]
    label = _sample("label-order", label, len(label))
    reserve = _sample("reserve", sorted(set(main) - set(label)), reserve_n)    # one simple random extension batch (D-13)
    return {"pilot": pilot, "pilot_skipped": skipped, "main": sorted(main), "label": label, "reserve": reserve,
            "flagged": {i for i in main if is_flagged(texts[i])}}


def _csv_text(header: list, rows: list) -> str:
    buffer = io.StringIO(); w = csv.writer(buffer, lineterminator="\n"); w.writerow(header); w.writerows(rows)
    return buffer.getvalue()


def create_sample(eligible, nlp, paths, day: str, sanitize_fn=sanitize_configured, fingerprint_fn=fingerprint, **sizes) -> dict:
    batches, excluded = rb.verify(paths)
    decision = read_decision(paths)
    if not batches or batches[-1]["status"] not in ("passed", "failed") or decision["batch"] != batches[-1]["batch"]:
        raise rb.BatchError("the review is unfinished or changed after the sign-off decision")
    fp = fingerprint_fn(eligible.protected, nlp)
    if fp != decision["fingerprint"]:
        raise rb.BatchError("code or configuration changed after the sign-off decision")
    if os.path.lexists(paths.sample_dir) or os.path.lexists(paths.sample_record):
        raise rb.BatchError("a sample already exists and will not be overwritten")
    texts, products = eligible.texts, eligible.products
    d = draw(texts, products, excluded, **sizes)
    # Everything that will ever be shown must sanitize NOW, before anything is written; no silent replacement.
    cleaned = {i: _CONTROL.sub(" ", sanitize_fn(texts[i], nlp, eligible.protected)) for i in d["pilot"] + d["label"] + d["reserve"]}
    label_at = {i: n for n, i in enumerate(d["label"], 1)}
    reserve_at = {i: n for n, i in enumerate(d["reserve"], 1)}

    def row(i, role):
        return [eligible.ids[i], narrative_hash(texts[i]), products[i], role, int(i in d["flagged"]), label_at.get(i, ""), reserve_at.get(i, "")]
    manifest = _csv_text(MANIFEST_FIELDS, [row(i, "pilot") for i in d["pilot"]] + [row(i, "main") for i in d["main"]])
    replaced = _csv_text(["complaint_id", "sha256", "product", "draw_position"],
                         [[eligible.ids[i], narrative_hash(texts[i]), products[i], position] for i, position in d["pilot_skipped"]])
    order = _sample("pilot-reading-order", d["pilot"], len(d["pilot"]))
    pilot_text = PILOT_BANNER + "\n".join(f"=== PILOT {n} ===\n{cleaned[i]}\n" for n, i in enumerate(order, 1))

    paths.sample_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    _write_new(paths.sample_dir / "manifest.csv", manifest)
    _write_new(paths.sample_dir / "pilot_replacements.csv", replaced)
    _write_new(paths.sample_dir / "pilot_items.txt", pilot_text)

    def count(indices):
        return dict(sorted(Counter(products[i] for i in indices).items()))
    record = {"date": day, "seed": SEED, "archive_sha256": eligible.archive_sha256, "eligible": len(texts),
              "excluded_reviewed": sum(not k for k in keep_mask(texts, excluded)), "sanitizer_decision": decision["decision"],
              "pilot_by_product": count(d["pilot"]), "pilot_flagged_draws_replaced": len(d["pilot_skipped"]),
              "main_by_product": count(d["main"]), "main_flagged_total": len(d["flagged"]),
              "label_by_product": count(d["label"]), "reserve_n": len(d["reserve"]),          # label-set flag count deliberately not shown before labeling
              "manifest_sha256": hashlib.sha256(manifest.encode()).hexdigest(), "fingerprint": fp}
    with open(paths.sample_record, "x", encoding="utf-8") as f:          # written LAST: a folder without a record means an interrupted run
        f.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return record


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("command", choices=["decide", "sample"]); ap.add_argument("zip")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--signed-off", action="store_true"); group.add_argument("--not-signed-off", action="store_true")
    args = ap.parse_args(argv)
    if args.command == "decide" and not (args.signed_off or args.not_signed_off):
        ap.error("decide needs --signed-off or --not-signed-off")
    try:
        from part_b.sanitizer import load_nlp
        paths = rb.DEFAULT_PATHS
        rb.verify(paths)                                          # fail before reading the archive
        eligible, nlp, day = load_eligible(args.zip), load_nlp(), datetime.date.today().isoformat()
        if args.command == "decide":
            result = record_decision(eligible.protected, nlp, paths, args.signed_off, day)
            shown = {k: result[k] for k in ("decision", "batch", "batch_outcomes")}
        else:
            result = create_sample(eligible, nlp, paths, day)
            shown = {k: v for k, v in result.items() if k not in ("fingerprint", "manifest_sha256", "archive_sha256")}
    except (rb.BatchError, EligibilityError, ExclusionError) as e:
        print(f"FAIL: {e}"); return 1
    except Exception as e:                                        # library errors can quote data: print the type only
        print(f"FAIL: unexpected {type(e).__name__} (details suppressed)"); return 1
    print("PASS")
    for key, value in shown.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
