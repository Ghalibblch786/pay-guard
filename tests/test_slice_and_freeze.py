"""Tests for sign-off, sampling, freezing and the labeling pack. SYNTHETIC data in temporary folders only."""
import csv, hashlib, json, stat

import pytest

from part_b import freeze_plan as fz, make_review_batch as mk, make_slice as ms, review_batches as rb, summarize_review as sm
from part_b.eligibility import Eligible, EligibilityError
from part_b.exclusions import add_exclusions, load_exclusions, narrative_hash

DAY, MARK = "2026-01-01", "ZEBRAWORD"
PRODUCTS = {"Card": 300, "Checking": 340, "Transfer": 140, "Prepaid": 40}
AUDITED = [f"{MARK} audited {i}" for i in range(20)]


def fake_fp(protected, nlp, code="v1"):
    return {"part_b/sanitizer.py": code, "part_b/sensitive_flags.py": "f1"}


def changed_fp(protected, nlp):
    return fake_fp(protected, nlp, "v2")


def fake_sanitize(raw, nlp, protected):
    return "clean " + raw


@pytest.fixture(autouse=True)
def paths(tmp_path, monkeypatch):
    p = rb.Paths(exclusions=tmp_path / "ex" / "h.csv", review_dir=tmp_path / "review", tracked=tmp_path / "log.json", guide=tmp_path / "guide.md",
                 signoff=tmp_path / "signoff.json", sample_dir=tmp_path / "sample", sample_record=tmp_path / "record.json", labeling_dir=tmp_path / "labeling")
    p.tracked.write_text('{"batches": []}'); p.guide.write_text("synthetic")
    add_exclusions({narrative_hash(t) for t in AUDITED}, "flag_audit", DAY, p.exclusions)
    monkeypatch.setattr(rb, "DEFAULT_PATHS", p)
    return p


@pytest.fixture(scope="module")
def eligible():
    texts, products = list(AUDITED), ["Card"] * 20
    for product, n in PRODUCTS.items():
        for i in range(n):
            texts.append(f"{MARK} {product} story {i}" + (" I shared my password." if i % 5 == 0 else ""))
            products.append(product)
    return Eligible(texts, products, {"acme"}, "z" * 64, [f"ID{i}" for i in range(len(texts))])


def review(eligible, paths, passed: bool):
    mk.create_batch(eligible, None, paths, DAY, sanitize_fn=fake_sanitize, fingerprint_fn=fake_fp)
    rows = [f"{n},n,,n,n," for n in range(1, 31)]
    if not passed:
        rows[0] = "1,n,,y,n,"
    (rb.batch_dir(paths, 1) / "verdicts.csv").write_text("\n".join([mk.VERDICT_HEADER] + rows) + "\n")
    sm.summarize_batch(1, paths, record=True)


def decide(eligible, paths, signed_off, fp=fake_fp):
    return ms.record_decision(eligible.protected, None, paths, signed_off, DAY, fingerprint_fn=fp)


def sample(eligible, paths, **kw):
    kw.setdefault("sanitize_fn", fake_sanitize); kw.setdefault("fingerprint_fn", fake_fp)
    return ms.create_sample(eligible, None, paths, DAY, **kw)


def read_manifest(paths):
    with (paths.sample_dir / "manifest.csv").open(newline="") as f:
        return list(csv.DictReader(f))


# --- sign-off decision ---
def test_signoff_needs_a_passed_batch_and_unchanged_code(eligible, paths):
    with pytest.raises(rb.BatchError, match="no finished"):
        decide(eligible, paths, False)
    review(eligible, paths, passed=True)
    with pytest.raises(rb.BatchError, match="invalid"):
        decide(eligible, paths, True, fp=changed_fp)
    assert not paths.signoff.exists()
    assert decide(eligible, paths, True)["decision"] == "signed_off"
    with pytest.raises(rb.BatchError, match="already exists"):
        decide(eligible, paths, False)


def test_failed_review_cannot_be_signed_off_but_can_be_declined(eligible, paths):
    review(eligible, paths, passed=False)
    with pytest.raises(rb.BatchError, match="no passed"):
        decide(eligible, paths, True)
    assert decide(eligible, paths, False)["batch_outcomes"] == ["failed"]


def test_no_review_batch_after_the_decision(eligible, paths):
    review(eligible, paths, passed=False); decide(eligible, paths, False)
    with pytest.raises(rb.BatchError, match="no new review batches"):
        mk.create_batch(eligible, None, paths, DAY, sanitize_fn=fake_sanitize, fingerprint_fn=changed_fp)


@pytest.mark.parametrize("name", ["sample_dir", "sample_record"])
def test_no_review_batch_once_sampling_started(eligible, paths, name):
    getattr(paths, name).write_text("x")
    with pytest.raises(rb.BatchError, match="no new review batches"):
        mk.create_batch(eligible, None, paths, DAY, sanitize_fn=fake_sanitize, fingerprint_fn=fake_fp)


# --- allocation and selection ---
def test_allocation_is_proportional_and_exact():
    counts = {"Checking": 3130, "Card": 2700, "Transfer": 1280, "Prepaid": 203}
    share = ms.allocate(counts, 400)
    assert sum(share.values()) == 400 and all(abs(share[k] - 400 * v / sum(counts.values())) < 1 for k, v in counts.items())
    assert ms.allocate({"a": 1, "b": 1, "c": 1}, 2) == {"a": 1, "b": 1, "c": 0}
    with pytest.raises(rb.BatchError):
        ms.allocate({"a": 3}, 4)


def test_draw_rules(eligible, paths):
    excluded = load_exclusions(paths.exclusions)
    d = ms.draw(eligible.texts, eligible.products, excluded)
    assert d == ms.draw(eligible.texts, eligible.products, excluded)                     # reproducible
    pilot, main = set(d["pilot"]), set(d["main"])
    assert len(d["pilot"]) == 20 and {p: sum(eligible.products[i] == p for i in pilot) for p in PRODUCTS} == {p: 5 for p in PRODUCTS}
    assert not any("password" in eligible.texts[i] for i in pilot)
    assert all("password" in eligible.texts[i] for i, _ in d["pilot_skipped"]) and not {i for i, _ in d["pilot_skipped"]} & pilot
    assert len(main) == 400 and not pilot & main and not any(i < 20 for i in pilot | main)        # first 20 = reviewed
    assert {narrative_hash(eligible.texts[i]) for i in pilot}.isdisjoint({narrative_hash(eligible.texts[i]) for i in main})
    assert d["flagged"] == {i for i in main if "password" in eligible.texts[i]} and d["flagged"]    # flagged STAY in main
    assert len(d["label"]) == 60 == len(set(d["label"])) and len(d["reserve"]) == 20 == len(set(d["reserve"]))
    assert set(d["label"]) <= main and set(d["reserve"]) <= main - set(d["label"])
    assert [eligible.products[i] for i in d["label"]] != sorted(eligible.products[i] for i in d["label"])    # order is shuffled


def test_flags_do_not_change_which_records_enter_main_from_a_given_pool(eligible, paths):
    excluded = load_exclusions(paths.exclusions)
    a = ms.draw(eligible.texts, eligible.products, excluded, is_flagged=lambda t: False)
    marked = {eligible.texts[i] for i in a["main"][::3]}
    b = ms.draw(eligible.texts, eligible.products, excluded, is_flagged=lambda t: t in marked)
    if set(a["pilot"]) == set(b["pilot"]):
        assert a["main"] == b["main"] and a["label"] == b["label"]


# --- sample files ---
@pytest.mark.parametrize("passed", [True, False])
def test_sample_files_and_aggregate_record(eligible, paths, passed):
    review(eligible, paths, passed); decide(eligible, paths, passed)
    reviewed = load_exclusions(paths.exclusions)
    record = sample(eligible, paths)
    rows = read_manifest(paths)
    assert len(rows) == 420 and not {r["sha256"] for r in rows} & reviewed and record["excluded_reviewed"] == 50
    assert record["sanitizer_decision"] == ("signed_off" if passed else "not_signed_off")
    text = paths.sample_record.read_text()
    assert MARK not in text and "ID1" not in text and not any(r["sha256"] in text for r in rows)
    assert stat.S_IMODE(paths.sample_dir.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in paths.sample_dir.iterdir())
    pilot_file = (paths.sample_dir / "pilot_items.txt").read_text()
    assert pilot_file.count("=== PILOT ") == 20 and "password" not in pilot_file and "ID" not in pilot_file.split("=== PILOT 1 ===")[1]
    with pytest.raises(rb.BatchError, match="already exists"):
        sample(eligible, paths)


def test_sampling_requires_decision_unchanged_code_and_intact_exclusions(eligible, paths):
    review(eligible, paths, True)
    with pytest.raises(rb.BatchError, match="not been recorded"):
        sample(eligible, paths)
    decide(eligible, paths, True)
    with pytest.raises(rb.BatchError, match="changed after"):
        sample(eligible, paths, fingerprint_fn=changed_fp)
    header, *rows = paths.exclusions.read_text().splitlines()
    paths.exclusions.write_text("\n".join([header] + rows[:-1]) + "\n")
    with pytest.raises(rb.BatchError):
        sample(eligible, paths)
    assert not paths.sample_dir.exists() and not paths.sample_record.exists()


def test_sanitizer_failure_writes_no_sample(eligible, paths):
    review(eligible, paths, True); decide(eligible, paths, True)
    calls = []
    def flaky(raw, nlp, protected):
        calls.append(1)
        if len(calls) == 100:
            raise EligibilityError("sanitization failed")
        return raw
    with pytest.raises(EligibilityError):
        sample(eligible, paths, sanitize_fn=flaky)
    assert not paths.sample_dir.exists() and not paths.sample_record.exists()


def test_sample_command_output_has_no_text_ids_or_hashes(eligible, paths, monkeypatch, capsys):
    import part_b.sanitizer
    review(eligible, paths, True); decide(eligible, paths, True)
    monkeypatch.setattr(ms, "load_eligible", lambda z: eligible)
    monkeypatch.setattr(part_b.sanitizer, "load_nlp", lambda: None)
    real = ms.create_sample
    monkeypatch.setattr(ms, "create_sample", lambda e, n, p, d: real(e, n, p, d, sanitize_fn=fake_sanitize, fingerprint_fn=fake_fp))
    assert ms.main(["sample", "unused.zip"]) == 0
    out = capsys.readouterr().out
    assert MARK not in out and "ID1" not in out and not any(r["sha256"] in out for r in read_manifest(paths))
    monkeypatch.setattr(ms, "load_eligible", lambda z: (_ for _ in ()).throw(KeyError(MARK)))
    assert ms.main(["sample", "unused.zip"]) == 1 and MARK not in capsys.readouterr().out


# --- freeze and labeling pack ---
@pytest.fixture
def root(tmp_path, paths):
    r = tmp_path / "repo"; (r / "part_b").mkdir(parents=True)
    for f in fz.FROZEN_FILES:
        (r / f).write_text("synthetic " + f)
    return r


def test_freeze_is_versioned_never_overwritten_and_detects_changes(root):
    with pytest.raises(rb.BatchError, match="nothing"):
        fz.verify_freeze(root)
    fz.freeze(1, DAY, root); fz.verify_freeze(root)
    for bad in (1, 3):
        with pytest.raises(rb.BatchError, match="consecutive"):
            fz.freeze(bad, DAY, root)
    (root / fz.FROZEN_FILES[0]).write_text("edited")
    with pytest.raises(rb.BatchError, match="changed or missing"):
        fz.verify_freeze(root)
    old = (root / "part_b" / "m3_freeze_v1.json").read_text()
    fz.freeze(2, DAY, root)
    assert fz.verify_freeze(root)["version"] == 2 and (root / "part_b" / "m3_freeze_v1.json").read_text() == old


def test_freeze_needs_every_file(root):
    (root / fz.FROZEN_FILES[-1]).unlink()
    with pytest.raises(rb.BatchError, match="missing"):
        fz.freeze(1, DAY, root)


def test_label_pack_is_blind_ordered_and_guarded(eligible, paths, root):
    review(eligible, paths, True); decide(eligible, paths, True); sample(eligible, paths)
    def pack(fp=fake_fp):
        return fz.make_label_pack(eligible, None, paths, root=root, sanitize_fn=fake_sanitize, fingerprint_fn=fp)
    with pytest.raises(rb.BatchError, match="nothing has been frozen"):
        pack()
    fz.freeze(1, DAY, root)
    with pytest.raises(rb.BatchError, match="changed since sampling"):
        pack(changed_fp)
    assert pack() == {"freeze_version": 1, "items": 60}
    sheet = (paths.labeling_dir / "labels.csv").read_text().splitlines()
    assert sheet[0] == fz.LABEL_HEADER and sheet[1:] == [f"{n},,,," for n in range(1, 61)]
    body = (paths.labeling_dir / "items.txt").read_text()
    ordered = sorted((r for r in read_manifest(paths) if r["label_position"]), key=lambda r: int(r["label_position"]))
    shown = [part.split("\n")[1].removeprefix("clean ") for part in body.split("=== ITEM ")[1:]]
    assert [narrative_hash(t) for t in shown] == [r["sha256"] for r in ordered]
    assert not any(r["complaint_id"] + "\n" in body or r["sha256"] in body for r in ordered) and "flagged" not in body
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in paths.labeling_dir.iterdir())
    with pytest.raises(rb.BatchError, match="already exist"):
        pack()


def test_label_pack_rejects_a_changed_manifest(eligible, paths, root):
    review(eligible, paths, True); decide(eligible, paths, True); sample(eligible, paths); fz.freeze(1, DAY, root)
    m = paths.sample_dir / "manifest.csv"; m.write_text(m.read_text() + "\n")
    with pytest.raises(rb.BatchError, match="manifest"):
        fz.make_label_pack(eligible, None, paths, root=root, sanitize_fn=fake_sanitize, fingerprint_fn=fake_fp)
