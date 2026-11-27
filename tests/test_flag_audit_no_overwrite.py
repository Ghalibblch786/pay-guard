"""flag_audit.main() must never overwrite an existing audit. SYNTHETIC data in temporary folders only."""
import stat

import pytest

from part_b import flag_audit

ITEMS, VERDICTS = "flag_audit_items.txt", "flag_audit_verdicts.csv"
FAKE = {"items_text": "SYNTHETIC NARRATIVE café\n", "verdicts_text": "item,category,verdict,note\n1,minors,,\n",
        "chosen_texts": ["x"], "eligible_texts": ["x"], "n_rows": 1, "quotas": {"minors": 1}, "n_flagged": 1}
FILLED = "item,category,verdict,note\n1,minors,y,my note\n"


@pytest.fixture(autouse=True)
def out_dir(tmp_path, monkeypatch):
    """autouse: no test in this file can ever reach the real audit folder."""
    d = tmp_path / "flag_audit"
    monkeypatch.setattr(flag_audit, "OUT_DIR", d)
    monkeypatch.setattr(flag_audit, "build_audit", lambda zp: dict(FAKE))
    return d


def snapshot(d):
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_mode) for p in d.iterdir()}


def test_generation_works_when_no_outputs_exist(out_dir, capsys):
    flag_audit.main("unused.zip")
    assert (out_dir / ITEMS).read_text(encoding="utf-8") == FAKE["items_text"]
    assert (out_dir / VERDICTS).read_text(encoding="utf-8") == FAKE["verdicts_text"]
    assert sorted(p.name for p in out_dir.iterdir()) == [ITEMS, VERDICTS]
    assert stat.S_IMODE(out_dir.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in out_dir.iterdir())
    assert "SYNTHETIC NARRATIVE" not in capsys.readouterr().out


def test_generation_works_in_an_existing_empty_folder(out_dir):
    out_dir.mkdir()
    flag_audit.main("unused.zip")
    assert (out_dir / VERDICTS).read_text() == FAKE["verdicts_text"]


def test_second_run_keeps_completed_verdicts_intact(out_dir):
    flag_audit.main("unused.zip")
    (out_dir / VERDICTS).write_text(FILLED)
    before = snapshot(out_dir)
    with pytest.raises(SystemExit, match="REFUSING"):
        flag_audit.main("unused.zip")
    assert snapshot(out_dir) == before and (out_dir / VERDICTS).read_text() == FILLED


@pytest.mark.parametrize("existing", [[ITEMS], [VERDICTS], [ITEMS, VERDICTS]])
def test_any_existing_output_blocks_before_any_work(out_dir, monkeypatch, existing):
    out_dir.mkdir()
    for name in existing:
        (out_dir / name).write_text("original " + name); (out_dir / name).chmod(0o640)
    before = snapshot(out_dir)
    monkeypatch.setattr(flag_audit, "build_audit", lambda zp: pytest.fail("must refuse before reading the archive"))
    with pytest.raises(SystemExit, match="REFUSING"):
        flag_audit.main("unused.zip")
    assert snapshot(out_dir) == before           # contents, timestamps and permissions; no second file created


@pytest.mark.parametrize("late", [ITEMS, VERDICTS])
def test_file_appearing_during_the_build_is_not_overwritten(out_dir, monkeypatch, late):
    def build_then_file_appears(zp):
        out_dir.mkdir(); (out_dir / late).write_text(FILLED)
        return dict(FAKE)
    monkeypatch.setattr(flag_audit, "build_audit", build_then_file_appears)
    with pytest.raises(SystemExit, match="REFUSING"):
        flag_audit.main("unused.zip")
    assert [p.name for p in out_dir.iterdir()] == [late] and (out_dir / late).read_text() == FILLED


def test_broken_symlink_output_is_refused_and_not_followed(out_dir, tmp_path):
    out_dir.mkdir(); target = tmp_path / "elsewhere.csv"
    (out_dir / VERDICTS).symlink_to(target)
    with pytest.raises(SystemExit, match="REFUSING"):
        flag_audit.main("unused.zip")
    assert not target.exists() and not (out_dir / ITEMS).exists()
