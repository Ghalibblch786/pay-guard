"""Tests for the manual leak review (SPECS Step 3). SYNTHETIC data in temporary folders only; nothing here reads data/."""
import csv, hashlib, io, json, stat, zipfile
from types import SimpleNamespace

import pytest

from part_b import make_review_batch as mk, review_batches as rb, summarize_review as sm
from part_b.eligibility import Eligible, EligibilityError, fingerprint, load_eligible, sanitize_configured
from part_b.exclusions import ExclusionError, add_exclusions, load_by_source, load_exclusions, narrative_hash
from part_b.run_sanitizer_aggregate import N

DAY = "2026-01-01"
MARK = "ZEBRAWORD"          # appears in every synthetic narrative, so leaks into output are detectable
AUDITED = [f"{MARK} audited story {i}" for i in range(20)]
FLAGGED = [f"{MARK} story {i}: I shared my password." for i in range(15)]
CLEAN = [f"{MARK} ordinary fee story {i}" for i in range(120)]
NLP = SimpleNamespace(meta={"name": "stub", "version": "0"})


def fake_fp(protected, nlp, code="v1"):
    return {"part_b/sanitizer.py": code, "part_b/sensitive_flags.py": "f1", "part_b/eligibility.py": "e1", "model": "stub-0"}


def fp_with(**changes):
    return lambda protected, nlp: {**fake_fp(protected, nlp), **changes}


def fake_sanitize(raw, nlp, protected):
    return "clean " + raw


@pytest.fixture(autouse=True)
def paths(tmp_path, monkeypatch):
    """autouse: even main() can only reach temporary folders."""
    p = rb.Paths(exclusions=tmp_path / "ex" / "h.csv", review_dir=tmp_path / "review", tracked=tmp_path / "log.json", guide=tmp_path / "guide.md",
                 signoff=tmp_path / "signoff.json", sample_dir=tmp_path / "sample", sample_record=tmp_path / "record.json", labeling_dir=tmp_path / "labeling")
    p.tracked.write_text('{"batches": []}'); p.guide.write_text("synthetic definitions")
    add_exclusions({narrative_hash(t) for t in AUDITED}, "flag_audit", DAY, p.exclusions)
    monkeypatch.setattr(rb, "DEFAULT_PATHS", p)
    return p


@pytest.fixture
def eligible():
    texts = AUDITED + FLAGGED + CLEAN
    return Eligible(texts, ["Credit card"] * len(texts), {"acme"}, "z" * 64, [str(i) for i in range(len(texts))])


def make(eligible, paths, **kw):
    kw.setdefault("sanitize_fn", fake_sanitize); kw.setdefault("fingerprint_fn", fake_fp)
    return mk.create_batch(eligible, NLP, paths, DAY, **kw)


def fill(paths, k=1, **overrides):
    """All-'n' sheet, with per-item overrides such as i3={'direct_leak': 'y', 'direct_types': 'name'}."""
    columns = mk.VERDICT_HEADER.split(",")
    with (rb.batch_dir(paths, k) / "verdicts.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(columns)
        for n in range(1, 31):
            row = {"item": str(n), "direct_leak": "n", "direct_types": "", "indirect_concern": "n", "visible_sensitive": "n", "visible_sensitive_category": ""}
            row.update(overrides.get(f"i{n}", {}))
            w.writerow([row[c] for c in columns])


def fail_batch(paths, k):
    fill(paths, k, i1={"indirect_concern": "y"})
    assert sm.summarize_batch(k, paths, record=True)["outcome"] == "failed"


def chosen_texts(paths, k):
    body = (rb.batch_dir(paths, k) / "items.txt").read_text()
    return [part.split("\n")[1].removeprefix("clean ") for part in body.split("=== ITEM ")[1:]]


def state(paths):
    return {str(p.relative_to(paths.tracked.parent)): p.read_bytes() for p in paths.tracked.parent.rglob("*") if p.is_file()}


# --- selection ---
def test_selection_is_reproducible_unflagged_and_unreviewed(eligible, paths):
    excluded = load_exclusions(paths.exclusions)
    a, pool = mk.select(eligible.texts, excluded, mk.batch_seed(1))
    assert a == mk.select(eligible.texts, excluded, mk.batch_seed(1))[0] and a != mk.select(eligible.texts, excluded, mk.batch_seed(2))[0]
    assert pool == len(CLEAN) and len(set(a)) == 30 and {eligible.texts[i] for i in a} <= set(CLEAN)


def test_too_few_records_creates_nothing(eligible, paths):
    small = Eligible(AUDITED + FLAGGED + CLEAN[:29], ["Credit card"] * 64, {"acme"}, "z" * 64, [str(i) for i in range(64)])
    before = state(paths)
    with pytest.raises(rb.BatchError, match="not enough"):
        make(small, paths)
    assert state(paths) == before


def test_flagger_error_keeps_record_out_of_the_pool(eligible, paths, monkeypatch):
    monkeypatch.setattr(mk, "is_sensitive_failclosed", lambda t: True)
    with pytest.raises(rb.BatchError, match="not enough"):
        make(eligible, paths)


def test_batches_never_overlap(eligible, paths):
    make(eligible, paths); first = set(chosen_texts(paths, 1)); fail_batch(paths, 1)
    make(eligible, paths, fingerprint_fn=fp_with(**{"part_b/sanitizer.py": "v2"}))
    second = set(chosen_texts(paths, 2))
    assert len(first) == len(second) == 30 and not first & second and not (first | second) & set(AUDITED + FLAGGED)


# --- generation, privacy, write order ---
def test_batch_files_records_and_permissions(eligible, paths):
    counts = make(eligible, paths)
    assert counts == {"batch": 1, "records": 30, "unflagged_unreviewed_pool": 120, "eligible": 155, "records_by_product": {"Credit card": 30}}
    folder = rb.batch_dir(paths, 1)
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700 and stat.S_IMODE(paths.review_dir.stat().st_mode) == 0o700
    for f in [folder / "items.txt", folder / "verdicts.csv", paths.ledger, paths.exclusions]:
        assert stat.S_IMODE(f.stat().st_mode) == 0o600
    hashes = load_by_source(paths.exclusions)["sanitizer_review_01"]
    assert sorted(hashes) == sorted(narrative_hash(t) for t in chosen_texts(paths, 1))     # RAW text hashes, not sanitized
    assert MARK not in (folder / "verdicts.csv").read_text() + paths.ledger.read_text() + paths.tracked.read_text() + paths.exclusions.read_text()
    tracked = paths.tracked.read_text()
    assert not any(h in tracked for h in hashes) and set(json.loads(tracked)["batches"][0]) == set(rb.PUBLIC_FIELDS)
    assert rb.verify(paths)[0][0]["status"] == "ready"


def test_terminal_control_characters_are_removed(eligible, paths):
    make(eligible, paths, sanitize_fn=lambda raw, nlp, protected: "a\x1b[31mred\x07\x00b\rc")
    body = (rb.batch_dir(paths, 1) / "items.txt").read_text()
    assert not any(c in body for c in "\x1b\x07\x00\r") and "red" in body


def test_one_sanitizer_failure_writes_nothing_and_is_not_replaced(eligible, paths):
    calls = []
    def flaky(raw, nlp, protected):
        calls.append(1)
        if len(calls) == 30:
            raise EligibilityError("sanitization failed")
        return raw
    before = state(paths)
    with pytest.raises(EligibilityError):
        make(eligible, paths, sanitize_fn=flaky)
    assert state(paths) == before and len(calls) == 30


class Crash(Exception):
    pass


def boom(*args, **kwargs):
    raise Crash()


@pytest.mark.parametrize("stage", ["exclusions", "review_files", "mark_ready"])
def test_interruption_at_each_stage_blocks_and_never_leaves_unexcluded_text(eligible, paths, monkeypatch, stage):
    if stage == "exclusions":
        monkeypatch.setattr(mk, "add_exclusions", boom)
    elif stage == "review_files":
        monkeypatch.setattr(mk, "_write_new", boom)
    else:
        real_save, calls = rb.save, []
        monkeypatch.setattr(rb, "save", lambda *a: boom() if calls else (calls.append(1), real_save(*a)))
    with pytest.raises(Crash):
        make(eligible, paths)
    monkeypatch.undo(); monkeypatch.setattr(rb, "DEFAULT_PATHS", paths)
    items = rb.batch_dir(paths, 1) / "items.txt"
    if items.exists():                                       # any text on disk must already be excluded
        assert {narrative_hash(t) for t in chosen_texts(paths, 1)} <= load_exclusions(paths.exclusions)
    before = state(paths)
    with pytest.raises((rb.BatchError, ExclusionError)):
        make(eligible, paths, fingerprint_fn=fp_with(**{"part_b/sanitizer.py": "v2"}))
    with pytest.raises((rb.BatchError, ExclusionError)):
        sm.summarize_batch(1, paths, record=True)
    assert state(paths) == before                            # no repair, no regeneration, no deletion


def test_exclusions_are_saved_before_any_review_file(eligible, paths, monkeypatch):
    real = mk._write_new
    def checked(path, content):
        assert len(load_by_source(paths.exclusions)["sanitizer_review_01"]) == 30
        assert json.loads(paths.tracked.read_text())["batches"][0]["status"] == "reserved"
        real(path, content)
    monkeypatch.setattr(mk, "_write_new", checked)
    make(eligible, paths)


def test_existing_output_folder_is_never_overwritten(eligible, paths):
    folder = rb.batch_dir(paths, 1); folder.mkdir(parents=True); (folder / "items.txt").write_text("keep me")
    with pytest.raises(rb.BatchError):
        make(eligible, paths)
    assert (folder / "items.txt").read_text() == "keep me" and len(load_exclusions(paths.exclusions)) == 20


# --- verification of records and exclusions ---
def rewrite_rows(paths, change):
    header, *rows = paths.exclusions.read_text().splitlines()
    paths.exclusions.write_text("\n".join([header] + change(rows)) + "\n")


def batch_rows(rows):
    return [r for r in rows if ",sanitizer_review_01," in r]


@pytest.mark.parametrize("change", [
    lambda rows: [r for r in rows if r != batch_rows(rows)[0]],                                      # partial batch
    lambda rows: [r for r in rows if ",sanitizer_review_01," not in r],                              # whole batch missing
    lambda rows: rows[1:],                                                                           # partial audit
    lambda rows: batch_rows(rows),                                                                   # audit missing
    lambda rows: rows + ["a" * 64 + ",sanitizer_review_01,2026-01-01"],                              # extra record
    lambda rows: rows + ["a" * 64 + ",mystery_source,2026-01-01"],                                   # unknown source
    lambda rows: rows + [batch_rows(rows)[0]],                                                       # duplicate row
    lambda rows: [r for r in rows if r != batch_rows(rows)[0]] + [batch_rows(rows)[1]],              # right row count, repeated hash
    lambda rows: [r for r in rows if r != batch_rows(rows)[0]] + [rows[0].replace(",flag_audit,", ",sanitizer_review_01,")],  # shared across sources
])
def test_incomplete_or_inconsistent_exclusions_block(eligible, paths, change):
    make(eligible, paths); fill(paths)
    rewrite_rows(paths, change)
    with pytest.raises(rb.BatchError):
        rb.verify(paths)
    with pytest.raises(rb.BatchError):
        sm.summarize_batch(1, paths, record=True)


def test_missing_exclusion_file_or_tracked_log_blocks(eligible, paths):
    paths.exclusions.rename(paths.exclusions.with_suffix(".bak"))
    with pytest.raises(ExclusionError, match="missing"):
        make(eligible, paths)
    paths.exclusions.with_suffix(".bak").rename(paths.exclusions); paths.tracked.unlink()
    with pytest.raises(rb.BatchError, match="missing"):
        make(eligible, paths)


def edit_log(path, change):
    data = json.loads(path.read_text()); change(data["batches"]); path.write_text(json.dumps(data))


@pytest.mark.parametrize("which, change", [
    ("tracked", lambda b: b.clear()),
    ("tracked", lambda b: b[0].update(status="passed")),
    ("tracked", lambda b: b[0].update(seed="other")),
    ("tracked", lambda b: b[0].update(extra=1)),
    ("ledger", lambda b: b.clear()),
    ("ledger", lambda b: b[0].pop("fingerprint")),
    ("both", lambda b: b[0].update(batch=2)),
    ("both", lambda b: b[0].update(size=29)),
])
def test_disagreeing_or_invalid_records_block(eligible, paths, which, change):
    make(eligible, paths)
    for name, path in [("tracked", paths.tracked), ("ledger", paths.ledger)]:
        if which in (name, "both"):
            edit_log(path, change)
    with pytest.raises(rb.BatchError):
        rb.verify(paths)


def test_lost_ledger_or_orphan_review_folder_blocks(eligible, paths):
    make(eligible, paths)
    paths.ledger.rename(paths.ledger.with_suffix(".bak"))
    with pytest.raises(rb.BatchError, match="disagree"):
        rb.verify(paths)
    # remove the batch consistently from both records and the exclusions; the leftover folder still gives it away
    paths.tracked.write_text('{"batches": []}')
    rewrite_rows(paths, lambda rows: [r for r in rows if ",flag_audit," in r])
    with pytest.raises(rb.BatchError, match="no record mentions"):
        rb.verify(paths)


# --- batch rules and sign-off ---
@pytest.mark.parametrize("finish, match", [(None, "unfinished"), ("pass", "passed")])
def test_no_new_batch_after_unreviewed_or_passed(eligible, paths, finish, match):
    make(eligible, paths)
    if finish:
        fill(paths); sm.summarize_batch(1, paths, record=True)
    with pytest.raises(rb.BatchError, match=match):
        make(eligible, paths, fingerprint_fn=fp_with(**{"part_b/sanitizer.py": "v2"}))


def test_retest_needs_changed_sanitizer_or_flagger_and_reverting_does_not_count(eligible, paths):
    make(eligible, paths); fail_batch(paths, 1)
    for unchanged in [fake_fp, fp_with(model="other"), fp_with(**{"part_b/eligibility.py": "e2"})]:
        with pytest.raises(rb.BatchError, match="changed sanitizer or flagger"):
            make(eligible, paths, fingerprint_fn=unchanged)
    make(eligible, paths, fingerprint_fn=fp_with(**{"part_b/sensitive_flags.py": "f2"})); fail_batch(paths, 2)
    with pytest.raises(rb.BatchError, match="changed sanitizer or flagger"):
        make(eligible, paths, fingerprint_fn=fake_fp)                      # back to batch 1's code


def test_three_batch_cap(eligible, paths):
    for k in (1, 2, 3):
        make(eligible, paths, fingerprint_fn=fp_with(**{"part_b/sanitizer.py": f"v{k}"})); fail_batch(paths, k)
    before = state(paths)
    with pytest.raises(rb.BatchError, match="cap"):
        make(eligible, paths, fingerprint_fn=fp_with(**{"part_b/sanitizer.py": "v4"}))
    assert state(paths) == before and len(load_exclusions(paths.exclusions)) == 20 + 90     # failed batches stay excluded


def test_signoff_requires_a_pass_and_is_invalidated_by_any_change(eligible, paths):
    with pytest.raises(rb.BatchError, match="no passed"):
        rb.check_signoff([], fake_fp(None, None))
    make(eligible, paths); fill(paths)
    with pytest.raises(rb.BatchError, match="no passed"):
        rb.check_signoff(rb.verify(paths)[0], fake_fp(None, None))
    sm.summarize_batch(1, paths, record=True)
    batches = rb.verify(paths)[0]
    rb.check_signoff(batches, fake_fp(None, None))
    for key in fake_fp(None, None):
        with pytest.raises(rb.BatchError, match="invalid"):
            rb.check_signoff(batches, {**fake_fp(None, None), key: "changed"})


# --- verdicts and pass rule ---
@pytest.mark.parametrize("finding", sm.FINDINGS)
@pytest.mark.parametrize("answer", ["y", "u"])
def test_any_yes_or_unsure_fails_the_batch(eligible, paths, finding, answer):
    make(eligible, paths)
    row = {finding: answer}
    if answer == "y" and finding in sm.DETAIL:
        row[sm.DETAIL[finding][0]] = "name" if finding == "direct_leak" else "minors"
    fill(paths, i17=row)
    result = sm.summarize_batch(1, paths, record=True)
    assert result["outcome"] == "failed" and result["counts"]["items_failing"] == 1 and result["counts"][finding][answer] == 1


def test_all_no_passes_and_preview_changes_nothing(eligible, paths):
    make(eligible, paths); fill(paths)
    before = state(paths)
    assert sm.summarize_batch(1, paths, record=False)["outcome"] == "passed" and state(paths) == before
    assert sm.summarize_batch(1, paths, record=True)["outcome"] == "passed"
    assert json.loads(paths.tracked.read_text())["batches"][0]["status"] == "passed"


def test_recorded_outcome_cannot_be_changed(eligible, paths):
    make(eligible, paths); fail_batch(paths, 1); fill(paths)
    with pytest.raises(rb.BatchError, match="not awaiting review"):
        sm.summarize_batch(1, paths, record=True)
    assert rb.verify(paths)[0][0]["status"] == "failed"


def test_multiple_codes_are_counted(eligible, paths):
    make(eligible, paths)
    fill(paths, i1={"direct_leak": "y", "direct_types": "name; phone;name"}, i2={"visible_sensitive": "u", "visible_sensitive_category": "minors"})
    counts = sm.summarize_batch(1, paths, record=False)["counts"]
    assert counts["direct_types"] == {"name": 1, "phone": 1} and counts["visible_sensitive_category"] == {"minors": 1} and counts["items_failing"] == 2


SECRET = "jane doe 555-0100"


@pytest.mark.parametrize("row", [
    {"direct_leak": ""}, {"indirect_concern": ""}, {"visible_sensitive": ""},
    {"direct_leak": SECRET}, {"indirect_concern": "maybe"},
    {"direct_leak": "y"}, {"direct_leak": "n", "direct_types": "name"}, {"direct_leak": "y", "direct_types": SECRET},
    {"visible_sensitive": "y"}, {"visible_sensitive": "n", "visible_sensitive_category": "minors"}, {"visible_sensitive": "y", "visible_sensitive_category": SECRET},
    {"item": "7"},
])
def test_invalid_verdicts_are_rejected_without_echoing_cells(eligible, paths, capsys, row):
    make(eligible, paths); fill(paths, i5=row)
    before = state(paths)
    assert sm.main(["1", "--record"]) == 1
    out = capsys.readouterr().out
    assert "FAIL: row 5" in out and SECRET not in out and "maybe" not in out and state(paths) == before


@pytest.mark.parametrize("damage", [lambda t: t.replace("item,", "note,", 1), lambda t: "\n".join(t.splitlines()[:-1]) + "\n",
                                    lambda t: t + "31,n,,n,n,\n", lambda t: t.replace("\n3,n,,n,n,", f"\n3,n,,n,n,,{SECRET}"), lambda t: ""])
def test_wrong_sheet_shape_is_rejected(eligible, paths, capsys, damage):
    make(eligible, paths); fill(paths)
    sheet = rb.batch_dir(paths, 1) / "verdicts.csv"; sheet.write_text(damage(sheet.read_text()))
    assert sm.main(["1", "--record"]) == 1 and SECRET not in capsys.readouterr().out
    assert rb.verify(paths)[0][0]["status"] == "ready"


def test_blank_generated_sheet_cannot_be_recorded(eligible, paths):
    make(eligible, paths)
    with pytest.raises(rb.BatchError, match="row 1"):
        sm.summarize_batch(1, paths, record=True)


@pytest.mark.parametrize("target, match", [("items", "review text"), ("guide", "definitions changed"), ("sheet", "verdict sheet is missing")])
def test_changed_text_changed_definitions_or_missing_sheet_block(eligible, paths, target, match):
    make(eligible, paths); fill(paths)
    if target == "sheet":
        (rb.batch_dir(paths, 1) / "verdicts.csv").unlink()
    else:
        f = rb.batch_dir(paths, 1) / "items.txt" if target == "items" else paths.guide
        f.write_text(f.read_text() + " ")
    with pytest.raises(rb.BatchError, match=match):
        sm.summarize_batch(1, paths, record=True)
    assert json.loads(paths.tracked.read_text())["batches"][0]["status"] == "ready"


# --- no text or hashes in output; error suppression ---
def test_command_output_contains_no_text_or_hashes(eligible, paths, monkeypatch, capsys):
    import part_b.sanitizer
    monkeypatch.setattr(mk, "load_eligible", lambda z: eligible)
    monkeypatch.setattr(part_b.sanitizer, "load_nlp", lambda: NLP)
    real = mk.create_batch
    monkeypatch.setattr(mk, "create_batch", lambda e, n, p, d: real(e, n, p, d, sanitize_fn=fake_sanitize, fingerprint_fn=fake_fp))
    assert mk.main("unused.zip") == 0
    fill(paths)
    assert sm.main(["1", "--record"]) == 0
    out = capsys.readouterr().out
    assert MARK not in out and not any(h in out for h in load_exclusions(paths.exclusions)) and "PASSED (recorded, final)" in out


def test_library_errors_are_suppressed(paths, monkeypatch, capsys):
    def leaky(*a):
        raise KeyError(f"{MARK} private")
    monkeypatch.setattr(mk, "load_eligible", leaky)
    assert mk.main("unused.zip") == 1
    monkeypatch.setattr(sm, "summarize_batch", leaky)
    assert sm.main(["1"]) == 1
    out = capsys.readouterr().out
    assert out.count("KeyError") == 2 and MARK not in out


def test_main_checks_exclusions_before_reading_the_archive(paths, monkeypatch, capsys):
    paths.exclusions.unlink()
    monkeypatch.setattr(mk, "load_eligible", lambda z: pytest.fail("must not read the archive"))
    assert mk.main("unused.zip") == 1 and "missing" in capsys.readouterr().out


# --- shared eligibility and sanitizer configuration ---
def synthetic_zip(tmp_path):
    def row(cid, text, company="Acme Widget Bank", product="Credit card", date="01/02/26"):
        return {"Complaint ID": str(cid), "Date received": date, "Product": product, "Company": company, N: text}
    long = " ".join(["word"] * 40)
    rows = [row(i, f"{long} number{i}") for i in range(1, 26)]
    rows += [row(90, f"{long}   number1", date="01/03/26"), row(91, "too short"), row(92, " ".join(["w"] * 1501)), row(93, ""), row(94, long + " x", product="Mortgage")]
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    z = tmp_path / "synthetic.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("c.csv", buf.getvalue())
    return z, hashlib.sha256(z.read_bytes()).hexdigest()


def test_load_eligible_applies_dedup_and_length_rules_and_checks_expectations(tmp_path):
    z, sha = synthetic_zip(tmp_path)
    e = load_eligible(z, sha, {"Credit card": 25}, expected_terms=2)
    assert len(e.texts) == 25 and e.protected == {"acme widget bank", "acme widget"}
    assert sum(text.endswith(" number1") for text in e.texts) == 1 and not any("   " in text for text in e.texts)    # earliest copy kept
    assert MARK not in repr(e) and "word word" not in repr(e)
    for args, match in [(("0" * 64, {"Credit card": 25}, 2), "archive"), ((sha, {"Credit card": 26}, 2), "population"), ((sha, {"Credit card": 25}, 3), "protected")]:
        with pytest.raises(EligibilityError, match=match):
            load_eligible(z, *args)


class StubNLP:
    meta = {"name": "stub", "version": "0"}
    def __call__(self, text):
        return SimpleNamespace(ents=[])


def test_sanitize_configured_requires_the_language_model_and_fails_closed():
    assert "[EMAIL]" in sanitize_configured("write to a@example.com now", StubNLP(), set())
    with pytest.raises(EligibilityError, match="model is missing"):
        sanitize_configured("write to a@example.com now", None, set())
    def broken(text):
        raise ValueError("private words")
    with pytest.raises(EligibilityError, match="^sanitization failed$"):
        sanitize_configured("hello", broken, set())


def test_real_fingerprint_tracks_code_terms_and_model(tmp_path):
    base = fingerprint({"a"}, StubNLP())
    assert set(rb.RETEST_FILES) <= set(base) and base["model"] == "stub-0"
    assert base != fingerprint({"b"}, StubNLP()) and base == fingerprint({"a"}, StubNLP())


def test_sanitize_configured_rejects_output_produced_without_ner(monkeypatch):
    from part_b import eligibility
    monkeypatch.setattr(eligibility, "try_sanitize", lambda *a, **k: SimpleNamespace(text="partly cleaned", ner_used=False))
    with pytest.raises(EligibilityError, match="sanitization failed"):
        sanitize_configured("hello", StubNLP(), set())
