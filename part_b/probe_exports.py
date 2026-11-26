"""Stage 3b: bounded, AGGREGATE-ONLY probe of official CFPB archive exports using HTTP Range requests.

Technique (ZIP + deflate): read the central directory from the file tail (method, sizes, offset), then fetch a PREFIX of the
single member's compressed data and inflate it from the stream start. A deflate stream cannot be decoded from an arbitrary middle
offset (back-references need the earlier window), so only prefixes are valid; they are a random sample only if row order is random
(tested below, not assumed). Never prints or stores narrative text.

Usage (isolated mode):  python -I part_b/probe_exports.py validate|probe <out.json> [prefix_bytes]
"""
import csv, io, json, math, re, struct, sys, urllib.request, zipfile, zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inspect_archive import PII  # our own code: same PII regexes as Stage 3a

csv.field_size_limit(10**8)
BASE = "https://files.consumerfinance.gov/f/documents/"
CANDIDATES = {
    "Nov-Dec 2025": BASE + "CCDB_Export_14_November_2025_through_December_2025.zip",
    "Jul-Aug 2025": BASE + "CCDB_Export_12_July_2025_through_August_2025.zip",
    "Jan-Feb 2025": BASE + "CCDB_Export_9_January_2025_through_February_2025.zip",
    "Sep 2023-Mar 2024": BASE + "CCDB_Export_5_September_2023_through_March_2024.zip",
}
CANDIDATES_2026 = {
    "Jan-Feb 2026": BASE + "CCDB_Export_15_January_2026_through_February_2026.zip",
    "Mar 2026": BASE + "CCDB_Export_16_March_2026.zip",
    "Apr 2026": BASE + "CCDB_Export_17_April_2026.zip",
    "May 2026": BASE + "CCDB_Export_18_May_2026.zip",
    "Jun 2026": BASE + "CCDB_Export_19_June_2026.zip",
    "Jul 2026": BASE + "CCDB_Export_20_July_2026.zip",
}
REF_COLS = ["Date received", "Product", "Sub-product", "Issue", "Sub-issue", "Consumer complaint narrative", "Company public response",
            "Company", "State", "ZIP code", "Tags", "Submitted via", "Date sent to company", "Company response to consumer",
            "Timely response?", "Complaint ID"]
AUG_URL = BASE + "CCDB_Export_21_August_2026.zip"
AUG_LOCAL = Path("data/raw/CCDB_Export_21_August_2026.zip")
LIVE_URL = "https://files.consumerfinance.gov/ccdb/complaints.csv.zip"
PAY_KW = ("money transfer", "virtual currency", "money service", "checking", "savings", "bank account", "credit card", "prepaid", "wallet")


def rng_get(url, rng):
    req = urllib.request.Request(url, headers={"Range": f"bytes={rng}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        assert r.status == 206, f"server did not honour Range (status {r.status})"
        return r.read(), r.headers.get("Content-Range")


def central_directory(url):
    tail, cr = rng_get(url, "-16384")
    total = int(cr.split("/")[1])
    i = tail.rfind(b"PK\x05\x06")
    assert i >= 0, "EOCD not found"
    n_entries, cd_size, cd_off = struct.unpack("<10xHII", tail[i + 0:i + 20])[0:3] if False else (struct.unpack("<H", tail[i + 10:i + 12])[0], *struct.unpack("<II", tail[i + 12:i + 20]))
    assert cd_off != 0xFFFFFFFF, "ZIP64 not handled"
    cd = tail[len(tail) - (total - cd_off): len(tail) - (total - cd_off) + cd_size] if total - cd_off <= len(tail) else rng_get(url, f"{cd_off}-{cd_off + cd_size - 1}")[0]
    assert cd[:4] == b"PK\x01\x02"
    flags, method = struct.unpack("<HH", cd[8:12]); csize, usize = struct.unpack("<II", cd[20:28])
    nl, el, cl = struct.unpack("<HHH", cd[28:34]); lho = struct.unpack("<I", cd[42:46])[0]
    return {"total_bytes": total, "entries": n_entries, "name": cd[46:46 + nl].decode(), "method": method, "flags": flags,
            "comp_size": csize, "uncomp_size": usize, "local_header_offset": lho}


def prefix_text(url, cdinfo, prefix_bytes):
    lh, _ = rng_get(url, f"{cdinfo['local_header_offset']}-{cdinfo['local_header_offset'] + 1023}")
    assert lh[:4] == b"PK\x03\x04"
    n, m = struct.unpack("<HH", lh[26:30]); lmethod = struct.unpack("<H", lh[8:10])[0]; lname = lh[30:30 + n].decode(); start = cdinfo["local_header_offset"] + 30 + n + m
    comp, _ = rng_get(url, f"{start}-{start + prefix_bytes - 1}")
    d = zlib.decompressobj(-15); out = d.decompress(comp)  # raises zlib.error on a corrupt stream
    meta = {"local_name_matches_cd": lname == cdinfo["name"], "local_method_matches_cd": lmethod == cdinfo["method"], "stream_reached_end_of_member": d.eof}
    return out, len(comp), meta


def wilson(k, n, z=1.96):
    if n == 0: return [None, None]
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(100 * (c - h) / d, 2), round(100 * (c + h) / d, 2)]


def analyse(raw):
    text = raw.decode("utf-8", "replace")
    rows = list(csv.reader(io.StringIO(text)))
    header, body = rows[0], rows[1:-1]  # last record may be cut off mid-field: dropped
    body_ok = [r for r in body if len(r) == len(header)]
    out = {"columns": header, "records_inspected": len(body_ok), "malformed_dropped": len(body) - len(body_ok)}
    col = {c.lower(): i for i, c in enumerate(header)}
    ci_n = next((i for c, i in col.items() if "narrative" in c), None); ci_p = col.get("product"); ci_d = col.get("date received")
    out["has_narrative_column"] = ci_n is not None
    if ci_n is None or not body_ok: return out
    has = [bool(r[ci_n].strip()) for r in body_ok]; n = len(has); k = sum(has)
    out["narratives_non_empty"] = {"n": k, "pct": round(100 * k / n, 2), "wilson95_pct": wilson(k, n),
                                   "pct_first_half": round(100 * sum(has[: n // 2]) / (n // 2), 2), "pct_second_half": round(100 * sum(has[n // 2:]) / (n - n // 2), 2)}
    prods = [r[ci_p] for r in body_ok]
    # ordering diagnostics: is the file order random w.r.t. Product and Date? (needed for prefix = sample)
    from collections import Counter
    cnt = Counter(prods); runs = 1 + sum(prods[i] != prods[i - 1] for i in range(1, n))
    exp_runs = n + 1 - sum(v * v for v in cnt.values()) / n
    dates = [r[ci_d] for r in body_ok]
    order = {d: i for i, d in enumerate(sorted(set(dates)))}
    xs = list(range(n)); ys = [order[d] for d in dates]
    mx, my = sum(xs) / n, sum(ys) / n
    corr = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    out["ordering_diagnostics"] = {"product_runs_observed": runs, "product_runs_expected_if_random": round(exp_runs),
                                   "date_rank_vs_row_index_corr": round(corr, 3), "date_min": min(dates), "date_max": max(dates), "distinct_dates": len(order)}
    from datetime import date, timedelta
    wk = {}
    for d_, h in zip(dates, has):
        dd = date.fromisoformat(d_[:10]); key = (dd - timedelta(days=dd.weekday())).isoformat()
        t = wk.setdefault(key, [0, 0]); t[0] += 1; t[1] += h
    out["fill_by_week_received"] = [{"week_start": k, "rows": a, "with_narrative": b, "pct": round(100 * b / a, 1)} for k, (a, b) in sorted(wk.items())]
    tab = {}
    for p, h in zip(prods, has):
        t = tab.setdefault(p, [0, 0]); t[0] += 1; t[1] += h
    out["products"] = sorted([{"product": p, "rows": a, "with_narrative": b, "payment_related": any(w in p.lower() for w in PAY_KW)} for p, (a, b) in tab.items()],
                             key=lambda d: (-d["with_narrative"], -d["rows"]))
    nar = [r[ci_n] for r, h in zip(body_ok, has) if h]
    if nar:
        wl = sorted(len(s.split()) for s in nar); q = lambda f: wl[min(len(wl) - 1, int(f * len(wl)))]
        out["narrative_words"] = {"n": len(wl), "p5": q(.05), "p25": q(.25), "p50": q(.5), "p75": q(.75), "p95": q(.95), "max": wl[-1]}
        pay = [r[ci_n] for r, h in zip(body_ok, has) if h and any(w in r[ci_p].lower() for w in PAY_KW)]
        out["payment_related_with_narrative"] = len(pay)
        out["pii_counts_narratives_with_match"] = {name: sum(bool(re.search(pat, s)) for s in nar) for name, pat in PII.items()}
    return out


def validate(out_path):
    """Prove the method on the August file we already hold: HTTP-range prefix == locally decompressed prefix."""
    res = {}
    cdi = central_directory(AUG_URL); res["central_directory_via_http"] = cdi
    zi = zipfile.ZipFile(AUG_LOCAL).infolist()[0]
    res["central_directory_matches_local_zip"] = (cdi["method"], cdi["comp_size"], cdi["uncomp_size"], cdi["name"]) == (zi.compress_type, zi.compress_size, zi.file_size, zi.filename)
    raw, got, _meta = prefix_text(AUG_URL, cdi, 2_000_000)
    with zipfile.ZipFile(AUG_LOCAL).open(zi) as f: local = f.read(len(raw))
    res["prefix_bytes_fetched"] = got; res["decompressed_bytes"] = len(raw); res["prefix_identical_to_local_decompression"] = (raw == local)
    a = analyse(raw); res["august_prefix_analysis"] = {k: a[k] for k in ("records_inspected", "narratives_non_empty", "ordering_diagnostics") if k in a}
    live = central_directory(LIVE_URL); res["live_metadata_csv_reference"] = {"comp_size": live["comp_size"], "uncomp_size": live["uncomp_size"], "ratio": round(live["uncomp_size"] / live["comp_size"], 1), "method": live["method"]}
    res["august_ratio"] = round(cdi["uncomp_size"] / cdi["comp_size"], 1)
    json.dump(res, open(out_path, "w"), indent=2); print(json.dumps(res, indent=2))


def probe(out_path, prefix_bytes, candidates=CANDIDATES):
    res = {}
    for name, url in candidates.items():
        r = {"url": url}
        try:
            cdi = central_directory(url); r["zip"] = {**cdi, "ratio_uncomp_over_comp": round(cdi["uncomp_size"] / cdi["comp_size"], 1)}
            if cdi["method"] != 8: r["note"] = f"compression method {cdi['method']} not deflate: cannot partially inspect"; res[name] = r; continue
            raw, got, meta = prefix_text(url, cdi, prefix_bytes)
            r["prefix_bytes_fetched"] = got; r["decompressed_bytes"] = len(raw); r["integrity"] = meta; r.update(analyse(raw))
            r["integrity"]["columns_identical_to_reference"] = r["columns"] == REF_COLS; r["integrity"]["zlib_error"] = None
            r["technically_successful"] = True
        except Exception as e:
            r["technically_successful"] = False; r["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        res[name] = r
    json.dump(res, open(out_path, "w"), indent=2); print("wrote", out_path)


if __name__ == "__main__":
    mode, out = sys.argv[1], sys.argv[2]
    if mode == "validate": validate(out)
    else: probe(out, int(sys.argv[3]) if len(sys.argv) > 3 else 3_000_000, CANDIDATES_2026 if mode == "probe2026" else CANDIDATES)
