"""PayGuard dashboard: an overview for executives and two workbenches for analysts. Screen code only; logic is in engine.py.

Run from the repository root:   python -m streamlit run app/dashboard.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import altair as alt
import streamlit as st

from app import engine
from part_a.data import TARGET
from part_b.eligibility import sanitize_configured
from part_b.llm_client import DEFAULT_URL, OllamaClient
from part_b.prompts import TAXONOMY
from part_b.run_triage import FINAL_PROMPT
from part_b.sanitizer import load_nlp
from part_b.triage import TriageRecord, triage_one

RAISES, LOWERS = "#3b5b7a", "#bdbdbd"
TEAMS = {c["id"]: c["team"] for c in TAXONOMY["categories"]}


@st.cache_resource(show_spinner="Loading transactions...")
def fraud_data():
    return engine.load_fraud()


@st.cache_resource(show_spinner="Loading the redaction model...")
def redaction_model():
    return load_nlp()


def local_model():
    """The local model client, or None when no local model is running."""
    try:
        client = OllamaClient(url=os.environ.get("PAYGUARD_OLLAMA_URL", DEFAULT_URL))
        client.digest()
        return client
    except Exception:
        return None


# ---------------------------------------------------------------- overview

def overview():
    fraud, complaints = engine.fraud_summary(), engine.complaint_summary()
    st.title("PayGuard: where we stand")
    st.write("Two early prototypes, built on public data. Neither is running in production.")

    st.subheader("Fraud detection: promising, needs PayGuard data")
    a, b, c = st.columns(3)
    a.metric("Frauds caught", f"{fraud['caught']} of {fraud['frauds']}")
    b.metric("Genuine payments wrongly flagged", f"{fraud['false_alarms']} of {fraud['genuine']:,}")
    c.metric("Estimated cost", f"€{fraud['cost']:,.0f}")
    c.caption(f"€{fraud['cost_if_nothing_flagged']:,.0f} if nothing is flagged")
    st.caption("Held-back transactions from European cards in 2013, about six hours. The cost assumes a €5 review, and that a flagged "
               "fraud is stopped. This setting was chosen after seeing these results, so expect somewhat worse on new data.")

    st.subheader("Complaint sorting: the safe flow works, the model is not good enough")
    a, b, c = st.columns(3)
    a.metric("Complaints processed", f"{complaints['processed']}")
    a.caption("None dropped")
    b.metric("Sent to a person", f"{complaints['sent_to_person']} of {complaints['processed']}")
    c.metric("Right team", f"{complaints['category_right']} of {complaints['category_n']}")
    c.caption(f"Always guessing the most common team also gets {complaints['category_guess']}")
    s = complaints["summaries"]
    st.caption(f"Sending everything to a person saves no review work: in a hand-checked sample, only {complaints['labeled_needed']} of "
               f"{complaints['labeled']} needed one. Of {s['rated']} summaries checked, {s['faithful']} was complete, {s['minor_omission']} "
               f"missed a detail and {s['unsupported']} was wrong or misleading. One reviewer, small samples.")

    st.subheader("Recommended next step")
    st.write("**Fraud:** get PayGuard transaction history and test the same method on it, without affecting any payment.\n\n"
             "**Complaints:** compare stronger models on PayGuard complaints. Do not put the current model into use.")


# ---------------------------------------------------------------- fraud workbench

def fraud_workbench():
    st.title("Fraud review")
    try:
        data = fraud_data()
    except FileNotFoundError:
        st.info("Add `data/raw/creditcard.csv` to use this page. The README explains where to download it.")
        return
    model, config, payments = data["model"], data["config"], data["validation"]

    cost = st.selectbox("Assumed cost of one manual review", engine.REVIEW_COSTS, format_func=lambda v: f"€{float(v):.0f}")
    limit = engine.threshold(config, cost)
    flagged = payments["probability"] > limit
    st.write(f"**Rule:** send a payment for review when its estimated chance of fraud is above **{limit:.1%}**. "
             "A cheaper review means a lower bar. A flag asks for a check; it does not block the payment.")
    a, b, c = st.columns(3)
    a.metric("Payments checked", f"{len(payments):,}")
    b.metric("Sent for review", f"{int(flagged.sum())}")
    c.metric("Frauds among them", f"{int((flagged & (payments[TARGET] == 1)).sum())} of {int(payments[TARGET].sum())}")
    st.caption("These are practice payments used while building the prototype, not the final test, so they look a little better "
               "than new data would.")

    view = st.radio("Show", ["Review queue", "Examples of each outcome"], horizontal=True)
    if view == "Review queue":
        ids = payments[flagged].sort_values("probability", ascending=False).index.tolist()
    else:
        examples = engine.example_transactions(payments, limit)
        kind = st.selectbox("Outcome (hand-picked, not a representative sample)", list(examples))
        ids = examples[kind]
    chosen = st.selectbox("Payment", ids, format_func=lambda i: f"#{i}  ·  €{payments.at[i, 'Amount']:,.2f}  ·  "
                                                               f"chance of fraud {payments.at[i, 'probability']:.1%}")
    row = payments.loc[chosen]

    a, b, c = st.columns(3)
    a.metric("Amount", f"€{row['Amount']:,.2f}")
    b.metric("Estimated chance of fraud", f"{row['probability']:.1%}")
    c.metric("Decision", "Review" if row["probability"] > limit else "Let through")

    st.subheader("What moved the estimate")
    _, pushes = engine.explain_transaction(model, config, row)
    top = pushes.head(6).assign(effect=lambda t: ["Raised the risk" if p > 0 else "Lowered the risk" for p in t["push"]])
    bars = alt.Chart(top).mark_bar(cornerRadiusEnd=3, size=18).encode(
        x=alt.X("push:Q", title="Left of the line lowers the risk, right raises it", axis=alt.Axis(labels=False, ticks=False, grid=False)),
        y=alt.Y("field:N", sort=None, title=None, axis=alt.Axis(labelFontSize=13, labelLimit=220)),
        color=alt.Color("effect:N", scale=alt.Scale(domain=["Raised the risk", "Lowered the risk"], range=[RAISES, LOWERS]),
                        legend=alt.Legend(title=None, orient="top")),
        tooltip=[alt.Tooltip("field:N", title="Field"), alt.Tooltip("effect:N", title="Effect")])
    zero = alt.Chart(alt.Data(values=[{"zero": 0}])).mark_rule(color="#8a8a8a").encode(x="zero:Q")
    st.altair_chart((bars + zero).properties(height=alt.Step(32)), width="stretch")
    st.caption("The six strongest influences, compared with a typical payment. \"Hidden signals\" are fields the data publisher "
               "disguised for privacy, so we cannot say what they mean. With PayGuard's own data they would have real names.")

    if st.toggle("Show what actually happened", key=f"truth-{chosen}"):
        st.write("This payment **was fraud**." if row[TARGET] == 1 else "This payment was **genuine**.")


# ---------------------------------------------------------------- complaint workbench

def complaint_workbench():
    st.title("Complaint sorting")
    st.write("Pick an invented complaint or write your own. Do not paste real customer data into this demo.")
    cases = {c["title"]: c["text"] for c in json.loads((engine.ROOT / "app" / "demo_cases.json").read_text())}
    choice = st.selectbox("Complaint", list(cases) + ["Write my own"])
    own = choice == "Write my own"
    text = st.text_area("Complaint text", value="" if own else cases[choice], height=120, disabled=not own, key=f"text-{choice}").strip()

    client = local_model()
    st.caption("A local model is running: results are produced live." if client else
               "No local model is running. Invented examples show saved results; your own text gets the checks but no model answer.")
    if not st.button("Sort this complaint", type="primary", disabled=not text):
        return

    st.subheader("1. Safety checks on the original text")
    sensitive = engine.sensitive_reasons(text)
    if sensitive:
        st.write(f"**Sensitive:** {', '.join(sensitive).lower()}. It goes straight to a person and no model reads it.")
    else:
        st.write("No sensitive content detected.")
    rules = engine.matched_words(text)
    for name, words in rules.items():
        st.write(f"- {engine.RULE_LABELS[name]} (matched: {', '.join(words)})")
    if not rules:
        st.write("No safety rule matched. These rules look for key words, so they can miss things.")

    redacted = None
    if not sensitive:
        st.subheader("2. What the model is allowed to read")
        try:
            redacted = sanitize_configured(text, redaction_model(), set())
        except Exception:                                    # never send text that could not be redacted
            st.warning("Personal details could not be removed, so no model reads this. It would go to a person.")
            return
        st.text(redacted)
        st.caption("Personal details are replaced where recognised. This reduces risk but does not make text anonymous.")

    record, saved = None, False
    if sensitive or client:
        with st.spinner("Working..."):
            record = triage_one(text, client, lambda raw: redacted, FINAL_PROMPT)      # nothing typed here is saved
    elif not own:
        record, saved = TriageRecord(**json.loads((engine.ROOT / "app" / "demo_saved.json").read_text())[choice]), True
    if record is None:
        st.warning("No model answer is available. In this system the complaint would go to a person.")
        return

    st.subheader("3. Result" + (" (saved from an earlier run)" if saved else ""))
    from_model = record.route == "model"
    st.write(f"**Send to:** {TEAMS[record.category.value] + ' team' if from_model else 'a person, to read and route'}")
    a, b = st.columns(2)
    a.metric("Urgency", record.urgency.capitalize() if from_model else "Not assessed")
    b.metric("Needs a person", "Yes" if record.requires_human else "No")
    if from_model:
        st.write(f"**Summary:** {record.summary}")
        st.write(f"**Model's own note:** {record.confidence_note}")

    st.subheader("Why")
    reasons = engine.why_a_person(record) if record.requires_human else ["Neither the model nor a safety rule asked for a person."]
    for reason in reasons:
        st.write(f"- {reason}")
    if from_model:
        st.caption("Safety rules can add \"needs a person\" but never remove it. We cannot see how the model reached its answer; its note "
                   "is its own wording and has not been checked. In testing it often chose the wrong team, so an agent must confirm.")
    if choice == "Attack that gets through" and not record.requires_human:
        st.error("This is a known weakness: a hidden instruction persuaded the model, and no safety rule noticed.")


st.set_page_config(page_title="PayGuard", layout="centered")
PAGES = {"Overview": overview, "Fraud review": fraud_workbench, "Complaint sorting": complaint_workbench}
PAGES[st.sidebar.radio("PayGuard prototype", list(PAGES))]()
