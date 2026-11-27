"""Tests for the local labeling tool. SYNTHETIC items in temporary folders only."""
import stat

import pytest

from part_b import label_cli as lc
from part_b.evaluate_triage import read_labels


def make_folder(tmp_path, n=3):
    (tmp_path / "items.txt").write_text("BANNER\n\n" + "\n".join(f"=== ITEM {i} ===\ninvented text {i}\n" for i in range(1, n + 1)))
    (tmp_path / "labels.csv").write_text("\n".join([lc.LABEL_HEADER] + [f"{i},,,," for i in range(1, n + 1)]) + "\n")
    return tmp_path


def drive(folder, answers, upto=3):
    queue, shown = list(answers), []

    def fake_input(prompt):
        if not queue:
            raise EOFError
        return queue.pop(0)
    return lc.run(folder, upto, ask_input=fake_input, show=shown.append), "\n".join(shown)


ONE = ["1", "h", "y", "", ""]
TWO = ["5", "l", "n", "y", ""]


def test_answers_are_saved_in_the_format_the_scorer_reads(tmp_path):
    folder = make_folder(tmp_path)
    done, shown = drive(folder, ONE + TWO, upto=2)
    labels = read_labels(folder / "labels.csv")
    assert done == 2 and [l["category"] for l in labels] == ["unauthorized_or_fraud", "fees_interest_or_billing"]
    assert labels[0]["urgency"] == "high" and labels[0]["requires_human"] and labels[1]["ambiguous"] and not labels[0]["ambiguous"]
    assert stat.S_IMODE((folder / "labels.csv").stat().st_mode) == 0o600
    assert "invented text 3" not in shown                      # stops at the target


def test_quit_keeps_saved_answers_and_resume_starts_at_the_next_record(tmp_path):
    folder = make_folder(tmp_path)
    assert drive(folder, ONE + ["2", "q"])[0] == 1
    done, shown = drive(folder, TWO)
    assert done == 2 and "invented text 2" in shown and "invented text 1" not in shown
    assert read_labels(folder / "labels.csv")[0]["category"] == "unauthorized_or_fraud"


def test_invalid_input_is_asked_again_and_unsaved_answers_are_not_written(tmp_path):
    folder = make_folder(tmp_path)
    before = (folder / "labels.csv").read_text()
    done, shown = drive(folder, ["9", "fraud", "1", "x", "h", "maybe", "y", ""])      # no final confirmation
    assert done == 0 and shown.count("Not a choice") == 4 and (folder / "labels.csv").read_text() == before


def test_redo_and_back_replace_answers_only_after_confirmation(tmp_path):
    folder = make_folder(tmp_path)
    drive(folder, ["1", "h", "y", "", "r"] + TWO + ["b", "7", "m", "n", "", ""])
    labels = read_labels(folder / "labels.csv")
    assert len(labels) == 1 and labels[0]["category"] == "other" and labels[0]["urgency"] == "medium"


def test_screen_shows_choices_and_no_suggestion():
    text = lc.screen(1, 30, "invented complaint", 100)
    assert "invented complaint" in text and all(name in text for name, _ in lc.CATEGORIES)
    assert "suggest" not in text.lower() and "flag" not in text.lower()


@pytest.mark.parametrize("breakage", ["items", "header", "rows"])
def test_unexpected_files_are_refused_and_left_alone(tmp_path, breakage):
    folder = make_folder(tmp_path)
    if breakage == "items":
        (folder / "items.txt").write_text("=== ITEM 2 ===\nx\n")
    elif breakage == "header":
        (folder / "labels.csv").write_text("a,b\n1,\n")
    else:
        (folder / "labels.csv").write_text(lc.LABEL_HEADER + "\n1,,,,\n")
    before = (folder / "labels.csv").read_text()
    with pytest.raises(ValueError):
        drive(folder, ONE)
    assert (folder / "labels.csv").read_text() == before


def test_refuses_to_print_when_not_in_an_interactive_terminal(capsys):
    assert lc.main([]) == 1 and "Refusing" in capsys.readouterr().out
