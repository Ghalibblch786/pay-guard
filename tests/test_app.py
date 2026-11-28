"""Dashboard tests: the explanation is exact, test data never reaches the screen, and each page runs."""
import json

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from app import engine
from part_a.data import CSV

needs_csv = pytest.mark.skipif(not CSV.exists(), reason="creditcard.csv not downloaded")


@pytest.fixture(scope="module")
def fraud():
    return engine.load_fraud()


@needs_csv
def test_dashboard_never_holds_test_transactions(fraud):
    assert fraud["validation"]["Time"].max() < fraud["config"]["split"]["test_starts_at_time"]
    assert len(fraud["validation"]) == fraud["config"]["split"]["val_rows"]


@needs_csv
def test_explanation_adds_up_to_the_probability(fraud):
    for _, row in fraud["validation"].sample(20, random_state=42).iterrows():
        start, pushes = engine.explain_transaction(fraud["model"], fraud["config"], row)
        assert 1 / (1 + np.exp(-(start + pushes["push"].sum()))) == pytest.approx(row["probability"], abs=1e-9)


def test_headline_figures_come_from_saved_results():
    fraud, complaints = engine.fraud_summary(), engine.complaint_summary()
    assert fraud["caught"] + fraud["missed"] == fraud["frauds"]
    assert complaints["to_model"] + complaints["sensitive"] == complaints["processed"]


def test_every_rule_has_a_plain_language_label():
    assert set(engine.RULE_LABELS) == set(engine.RULES)
    assert engine.matched_words("My lawyer will call.") == {"legal_threat": ["lawyer"]}


def test_every_demo_case_has_a_saved_answer():
    folder = engine.ROOT / "app"
    titles = [c["title"] for c in json.loads((folder / "demo_cases.json").read_text())]
    assert set(titles) == set(json.loads((folder / "demo_saved.json").read_text()))


@pytest.mark.parametrize("page", ["Overview", "Fraud review", "Complaint sorting"])
def test_page_runs_without_errors(page, monkeypatch):
    monkeypatch.setenv("PAYGUARD_OLLAMA_URL", "http://127.0.0.1:9")      # no model: tests never depend on one
    app = AppTest.from_file(str(engine.ROOT / "app" / "dashboard.py"), default_timeout=120).run()
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception


@pytest.mark.parametrize("case", ["Simple question", "Sensitive: health information", "Attack that gets through"])
def test_complaint_page_shows_a_result_without_a_model(case, monkeypatch):
    monkeypatch.setenv("PAYGUARD_OLLAMA_URL", "http://127.0.0.1:9")
    app = AppTest.from_file(str(engine.ROOT / "app" / "dashboard.py"), default_timeout=180).run()
    app.sidebar.radio[0].set_value("Complaint sorting").run()
    app.selectbox[0].set_value(case).run()
    app.button[0].click().run()
    assert not app.exception
    assert any("Needs a person" == m.label for m in app.metric)


def test_nothing_reaches_the_model_when_redaction_fails(monkeypatch):
    monkeypatch.setenv("PAYGUARD_OLLAMA_URL", "http://127.0.0.1:9")

    def broken(*args, **kwargs):
        raise RuntimeError("redaction failed")
    monkeypatch.setattr("part_b.eligibility.sanitize_configured", broken)
    app = AppTest.from_file(str(engine.ROOT / "app" / "dashboard.py"), default_timeout=180).run()
    app.sidebar.radio[0].set_value("Complaint sorting").run()
    app.selectbox[0].set_value("Simple question").run()
    app.button[0].click().run()
    assert not app.exception and app.warning and not app.metric
