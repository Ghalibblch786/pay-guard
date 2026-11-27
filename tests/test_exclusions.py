"""Tests for reviewed-record exclusions (SPECS D-29). SYNTHETIC data only; nothing here reads data/."""
import hashlib, stat, unicodedata

import pytest

from part_b import export_audit_hashes as ex
from part_b.exclusions import ExclusionError, add_exclusions, keep_mask, load_exclusions, narrative_hash

DAY = "2026-01-01"


def make_audit(chosen=("alpha story one", "beta story two"), others=("gamma story three",)):
    return {"items_text": "SYNTHETIC ITEMS\ncafé\n", "chosen_texts": list(chosen), "eligible_texts": list(chosen) + list(others)}


# --- normalization consistency (D-17) ---
def test_hash_is_d17_sha256():
    expected = hashlib.sha256("Café fee, TWICE.".encode()).hexdigest()
    assert narrative_hash("  Café \t fee,\n\n TWICE.  ") == expected


def test_whitespace_and_unicode_form_do_not_matter_but_case_and_punctuation_do():
    base = "My café account was charged twice."
    assert narrative_hash(base) == narrative_hash(unicodedata.normalize("NFD", base).replace(" ", " \n  "))
    assert narrative_hash(base) != narrative_hash(base.lower())
    assert narrative_hash(base) != narrative_hash(base.rstrip("."))


# --- exclusion behaviour ---
def test_reviewed_records_are_excluded_including_whitespace_variants(tmp_path):
    f = tmp_path / "x" / "h.csv"
    add_exclusions({narrative_hash("reviewed story")}, "flag_audit", DAY, f)
    assert keep_mask(["reviewed   story\n", "fresh story", "Reviewed story"], load_exclusions(f)) == [False, True, True]


def test_appending_is_idempotent_and_keeps_earlier_rows(tmp_path):
    f = tmp_path / "x" / "h.csv"
    a, b = narrative_hash("a"), narrative_hash("b")
    assert add_exclusions({a}, "flag_audit", DAY, f) == 1
    assert add_exclusions({a}, "flag_audit", DAY, f) == 0
    assert add_exclusions({a, b}, "sanitizer_review_1", DAY, f) == 2
    assert load_exclusions(f) == {a, b} and len(f.read_text().splitlines()) == 4


def test_file_and_folder_are_owner_only_and_hold_no_text(tmp_path):
    f = tmp_path / "x" / "h.csv"
    add_exclusions({narrative_hash("secret words")}, "flag_audit", DAY, f)
    assert stat.S_IMODE(f.stat().st_mode) == 0o600 and stat.S_IMODE(f.parent.stat().st_mode) == 0o700
    assert "secret" not in f.read_text() and list(f.parent.iterdir()) == [f]


def test_invalid_input_writes_nothing(tmp_path):
    f = tmp_path / "x" / "h.csv"
    for hashes, source in [({"not-a-hash"}, "flag_audit"), ({narrative_hash("a")}, "Bad Tag"), (set(), "flag_audit")]:
        with pytest.raises(ExclusionError):
            add_exclusions(hashes, source, DAY, f)
    assert not f.exists()


# --- fail closed ---
def test_missing_file_fails_closed(tmp_path):
    with pytest.raises(ExclusionError, match="missing"):
        load_exclusions(tmp_path / "absent.csv")


@pytest.mark.parametrize("content", ["", "sha256,source,date\n", "wrong,header,row\n", "sha256,source,date\nabc,flag_audit,2026-01-01\n",
                                     "sha256,source,date\n" + "a" * 64 + ",flag_audit,yesterday\n", "sha256,source,date\n\n"])
def test_empty_or_malformed_file_fails_closed_and_is_not_overwritten(tmp_path, content):
    f = tmp_path / "h.csv"; f.write_text(content)
    with pytest.raises(ExclusionError):
        load_exclusions(f)
    with pytest.raises(ExclusionError):
        add_exclusions({narrative_hash("a")}, "flag_audit", DAY, f)
    assert f.read_text() == content


# --- export: verify before saving ---
def test_export_saves_only_after_exact_match_and_leaves_items_file_alone(tmp_path):
    audit, items, out = make_audit(), tmp_path / "items.txt", tmp_path / "x" / "h.csv"
    items.write_bytes(audit["items_text"].encode())
    before = (items.read_bytes(), items.stat().st_mtime_ns)
    counts = ex.export(audit, items, out, DAY, n_expected=2)
    assert counts == {"audit_records_verified": 2, "rows_added": 2, "unique_hashes_in_file": 2, "eligible_before": 3, "eligible_excluded": 2, "eligible_after": 1}
    assert (items.read_bytes(), items.stat().st_mtime_ns) == before


@pytest.mark.parametrize("change", [lambda b: b + b"\n", lambda b: b[:-1], lambda b: b.replace(b"S", b"s", 1),
                                    lambda b: unicodedata.normalize("NFD", b.decode()).encode()])
def test_export_any_byte_difference_saves_nothing(tmp_path, change):
    audit, items, out = make_audit(), tmp_path / "items.txt", tmp_path / "x" / "h.csv"
    items.write_bytes(change(audit["items_text"].encode()))
    with pytest.raises(ex.VerificationError, match="byte for byte"):
        ex.export(audit, items, out, DAY, n_expected=2)
    assert not out.parent.exists()


@pytest.mark.parametrize("audit, n", [(make_audit(), 3), (make_audit(chosen=("same text", "same   text")), 2),
                                      (make_audit(others=("alpha  story one",)), 2)])
def test_export_wrong_counts_save_nothing(tmp_path, audit, n):
    items, out = tmp_path / "items.txt", tmp_path / "x" / "h.csv"
    items.write_bytes(audit["items_text"].encode())
    with pytest.raises(ex.VerificationError):
        ex.export(audit, items, out, DAY, n_expected=n)
    assert not out.parent.exists()


def test_export_missing_items_file_saves_nothing(tmp_path):
    with pytest.raises(ex.VerificationError, match="missing"):
        ex.export(make_audit(), tmp_path / "absent.txt", tmp_path / "x" / "h.csv", DAY, n_expected=2)
    assert not (tmp_path / "x").exists()


def test_main_suppresses_library_error_details_and_rejects_other_archives(tmp_path, monkeypatch, capsys):
    z = tmp_path / "fake.zip"; z.write_bytes(b"synthetic")
    assert ex.main(str(z)) == 1 and "not the accepted" in capsys.readouterr().out
    monkeypatch.setattr(ex, "ACCEPTED_ZIP_SHA256", hashlib.sha256(b"synthetic").hexdigest())
    def boom(_): raise KeyError("PRIVATE NARRATIVE WORDS")
    monkeypatch.setattr(ex, "build_audit", boom)
    assert ex.main(str(z)) == 1
    out = capsys.readouterr().out
    assert "KeyError" in out and "PRIVATE" not in out
