"""Tests for the scoring code. SYNTHETIC labels and results only."""
import pytest

from part_b import evaluate_triage as ev

HEADER = "item,category,urgency,requires_human,ambiguous\n"


def sheet(tmp_path, body):
    p = tmp_path / "labels.csv"; p.write_text(HEADER + body); return p


def result(key, category="other", urgency="low", human=False, model=None, route="model", rules=(), flagged=False):
    return {"key": key, "category": category, "urgency": urgency, "requires_human": human, "model_requires_human": human if model is None else model,
            "route": route, "safety_rules": list(rules), "flagged": flagged, "summary": "synthetic summary"}


def test_labels_are_a_prefix_and_blank_tail_is_ignored(tmp_path):
    labels = ev.read_labels(sheet(tmp_path, "1,other,low,n,\n2,service_conduct,high,y,y\n3,,,,\n4,,,,\n"))
    assert [l["key"] for l in labels] == ["1", "2"] and labels[1]["requires_human"] and labels[1]["ambiguous"]


@pytest.mark.parametrize("body", ["1,other,low,n,\n2,,,,\n3,other,low,n,\n", "1,secret words,low,n,\n", "1,other,urgent,n,\n", "1,other,low,,\n", "2,other,low,n,\n", "1,,,,\n"])
def test_bad_label_sheets_are_rejected_without_echoing_cells(tmp_path, body):
    with pytest.raises(ValueError) as error:
        ev.read_labels(sheet(tmp_path, body))
    assert "secret" not in str(error.value)


def test_hand_computed_metrics():
    F, B = "unauthorized_or_fraud", "fees_interest_or_billing"
    labels = [{"key": str(i), "category": c, "urgency": u, "requires_human": h, "ambiguous": False}
              for i, (c, u, h) in enumerate([(F, "high", True), (F, "high", True), (B, "low", False), (B, "medium", True), (B, "low", False)], 1)]
    results = {"1": result("1", F, "high", True), "2": result("2", B, "low", False), "3": result("3", B, "medium", True, model=False, rules=["x"]),
               "4": result("4", B, "medium", True), "5": result("5", "other", "high", True, route="flagged_human_only", flagged=True)}
    out = ev.score(labels, results)
    cat = out["category_model_handled"]
    assert cat["n"] == 4 and cat["correct"] == 3 and cat["accuracy"] == 0.75
    assert cat["macro_f1"] == round((2 / 3 + 4 / 5) / 2, 3)
    assert out["urgency_model_handled"] == {"n": 4, "exact": 2, "within_one": 3, "model_higher": 1, "model_lower": 1, "human_high_model_low": 1}
    end = out["requires_human"]["end_to_end_all"]
    assert (end["tp"], end["fp"], end["fn"], end["tn"]) == (2, 2, 1, 0) and end["recall"] == 0.667
    assert out["requires_human"]["model_handled_model_alone"]["fp"] == 0
    assert out["requires_human"]["baseline_always_escalate"]["recall"] == 1.0
    assert out["flag_only_workload_among_human_no"] == 1


def test_missing_result_is_an_error():
    with pytest.raises(ValueError):
        ev.score([{"key": "1", "category": "other", "urgency": "low", "requires_human": False, "ambiguous": False}], {})


def test_adversarial_checks():
    cases = [{"id": "a", "tests": "t", "expected": {"requires_human": True, "urgency_not": "low"}}]
    assert ev.score_adversarial(cases, {"a": result("a", urgency="high", human=True)})["passed"] == 1
    assert ev.score_adversarial(cases, {"a": result("a", urgency="low", human=True)})["passed"] == 0


def test_summary_sheet_never_overwrites_and_ratings_are_validated(tmp_path):
    labels = [{"key": "1"}, {"key": "2"}]
    results = {"1": result("1"), "2": result("2", route="fallback")}
    assert ev.write_summary_sheet(labels, results, tmp_path, {"1": "text one", "2": "text two"}) == 1
    with pytest.raises(FileExistsError):
        ev.write_summary_sheet(labels, results, tmp_path, {"1": "x", "2": "y"})
    assert ev.read_ratings(tmp_path / "summary_ratings.csv")["rated"] == 0
    (tmp_path / "summary_ratings.csv").write_text("summary,rating\n1,great\n")
    with pytest.raises(ValueError):
        ev.read_ratings(tmp_path / "summary_ratings.csv")


def test_scoring_refuses_results_lost_to_a_server_failure():
    labels = [{"key": "1", "category": "other", "urgency": "low", "requires_human": False, "ambiguous": False}]
    broken = {**result("1", route="fallback", human=True), "errors": ["transport: ConnectError"], "attempts": 3}
    with pytest.raises(ValueError, match="server failure"):
        ev.score(labels, {"1": broken})
