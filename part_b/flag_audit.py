"""M3 optional EXPLORATORY audit of the sensitive-content flagger: ~20 flagged narratives for the user to inspect LOCALLY.

NOT a reliable per-category precision estimate (about 3 items per category, flagged narratives only: it says nothing about false NEGATIVES).
Narrative text goes ONLY to gitignored local files under data/processed/flag_audit/ (mode 600); no text, Complaint IDs or hashes are printed
or saved elsewhere; the verdict sheet contains NO text. No network, no LLM.

  python -I part_b/flag_audit.py <export.zip>            # writes the two local files, prints counts only
It refuses to run if either output file already exists, so completed verdicts cannot be overwritten.
"""
import hashlib, os, random, re, sys, unicodedata, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SEED = 7001
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "processed" / "flag_audit"


def pick_audit(flagged, quotas, seed=SEED):
    """flagged: list of (item_key, frozenset_of_categories) in a deterministic order. quotas: {category: n}.
    Each narrative is assigned to its RAREST category (rarity = number of flagged narratives carrying it) so rare categories get coverage.
    Returns a list of chosen item_keys; shortfalls in a stratum are filled from the remaining flagged narratives."""
    freq = {}
    for _, cats in flagged:
        for c in cats: freq[c] = freq.get(c, 0) + 1
    rank = sorted(freq, key=lambda c: (freq[c], c))
    strata = {c: [] for c in rank}
    for key, cats in flagged:
        strata[min(cats, key=lambda c: (freq[c], c))].append(key)
    rng, chosen = random.Random(seed), []
    for c in rank:
        pool = strata[c]; n = min(quotas.get(c, 0), len(pool)); chosen += rng.sample(pool, n)
    target = sum(quotas.values())
    if len(chosen) < target:
        rest = [k for k, _ in flagged if k not in set(chosen)]; chosen += rng.sample(rest, min(target - len(chosen), len(rest)))
    return chosen


def highlight(raw, category_regexes, extra_spans=()):
    """Return raw text with every flagging match wrapped as «match»[cat1,cat2]; overlapping matches are merged."""
    spans = [(m.start(), m.end(), c) for c, rx in category_regexes.items() for m in rx.finditer(raw)] + list(extra_spans)
    spans.sort()
    merged = []
    for a, b, c in spans:
        if merged and a <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], b); merged[-1][2].add(c)
        else: merged.append([a, b, {c}])
    out, pos = [], 0
    for a, b, cats in merged:
        out += [raw[pos:a], "«", raw[a:b], "»[", ",".join(sorted(cats)), "]"]; pos = b
    out.append(raw[pos:])
    return "".join(out)


def build_audit(zp):
    """Rebuild the seeded audit selection IN MEMORY; writes nothing (also used by export_audit_hashes.py to verify the existing items file).
    Returns a dict of strings and lists that contain narrative text: never print or log it."""
    import pandas as pd
    from part_b.run_sanitizer_aggregate import EXPECTED, N, PAY, norm
    from part_b.sensitive_flags import CATEGORIES, _LONG_DIGITS, detect_sensitive
    z = zipfile.ZipFile(zp)
    with z.open(z.namelist()[0]) as f: df = pd.read_csv(f, dtype=str, keep_default_na=False)
    d = df[df["Product"].isin(PAY) & (df[N].str.strip() != "")].copy()
    d["key"] = d[N].map(lambda s: hashlib.sha256(norm(s).encode()).hexdigest()); d["cid"] = d["Complaint ID"].astype("int64")
    d = d.sort_values(["Date received", "cid"]).drop_duplicates("key", keep="first"); d["w"] = d[N].str.split().str.len(); d = d[d.w.between(30, 1500)]
    assert d["Product"].value_counts().to_dict() == EXPECTED
    texts = list(d[N]); flagged = [(i, detect_sensitive(t).categories) for i, t in enumerate(texts)]
    flagged = [(i, c) for i, c in flagged if c]
    freq = {}
    for _, cats in flagged:
        for c in cats: freq[c] = freq.get(c, 0) + 1
    rank = sorted(freq, key=lambda c: (freq[c], c)); quotas = {c: 3 for c in rank}; quotas[rank[-1]] = 2   # 6 x 3 + 2 = 20
    chosen = pick_audit(flagged, quotas)
    rng = random.Random(SEED + 1); rng.shuffle(chosen)                    # blind item order: not grouped by stratum
    items, rows = [], ["item,category,verdict,note"]
    for n, i in enumerate(chosen, 1):
        raw = texts[i]; cats = sorted(detect_sensitive(raw).categories)
        extra = [(m.start(), m.end(), "financial_account_details") for m in _LONG_DIGITS.finditer(raw)]
        items.append(f"=== ITEM {n} | flags that fired: {', '.join(cats)} ===\n{highlight(raw, CATEGORIES, extra)}\n")
        rows += [f"{n},{c},," for c in cats]
    header = ("LOCAL ONLY: contains consumer narratives (CFPB-redacted, NOT sanitized). Do not commit, share, upload or paste into chat.\n"
              "For each item and each flag that fired, decide whether the flag is CORRECT: does the narrative really contain that kind of sensitive content?\n"
              "Matches that triggered flags are marked «like this»[category]. Record y / n / u (unclear) in flag_audit_verdicts.csv (no text in that file).\n"
              "Exploratory only: about 3 items per category and flagged narratives only, so this is NOT a reliable precision estimate and says nothing about missed flags.\n\n")
    return {"items_text": header + "\n".join(items), "verdicts_text": "\n".join(rows) + "\n", "chosen_texts": [texts[i] for i in chosen],
            "eligible_texts": texts, "n_rows": len(rows) - 1, "quotas": quotas, "n_flagged": len(flagged)}


def _owner_only(path, flags):
    return os.open(path, flags, 0o600)


def main(zp):
    """Write a NEW audit. Never overwrites: if either output already exists (it may hold completed verdicts), stop. There is no override flag."""
    paths = [OUT_DIR / "flag_audit_items.txt", OUT_DIR / "flag_audit_verdicts.csv"]
    refusal = "REFUSING to run: an audit output file already exists and will not be overwritten. Nothing was changed."
    if any(os.path.lexists(p) for p in paths):                    # checked before any work; lexists also catches broken symlinks
        raise SystemExit(refusal)
    audit = build_audit(zp)
    OUT_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    created = []
    try:
        for path, text in zip(paths, [audit["items_text"], audit["verdicts_text"]]):
            with open(path, "x", encoding="utf-8", opener=_owner_only) as f:   # "x": fails if the file appeared since the check
                created.append(path)
                f.write(text)
    except BaseException as e:
        for path in created:                                      # remove only what THIS run created, so no mismatched pair is left
            path.unlink()
        if isinstance(e, FileExistsError):
            raise SystemExit(refusal) from None
        raise
    print(f"wrote {len(audit['chosen_texts'])} items and {audit['n_rows']} verdict rows to data/processed/flag_audit/ (gitignored, mode 600); "
          f"strata quotas: {audit['quotas']}; flagged pool {audit['n_flagged']}")


if __name__ == "__main__":
    main(sys.argv[1])
