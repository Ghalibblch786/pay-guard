"""Tests for the flag-audit selection and highlighting logic. SYNTHETIC data only."""
import re

import pytest

from part_b.flag_audit import highlight, pick_audit
from part_b.flag_audit_summary import summarize

FLAGGED = ([(i, frozenset({"rare"})) for i in range(2)] + [(10 + i, frozenset({"mid"})) for i in range(10)] + [(100 + i, frozenset({"common"})) for i in range(50)]
           + [(200 + i, frozenset({"common", "rare"})) for i in range(3)])


def test_quotas_respected_and_unique_and_reproducible():
    quotas = {"rare": 3, "mid": 3, "common": 2}
    a = pick_audit(FLAGGED, quotas, seed=1)
    assert a == pick_audit(FLAGGED, quotas, seed=1) and len(a) == len(set(a)) == 8
    assert a != pick_audit(FLAGGED, quotas, seed=2)


def test_rarest_category_gets_coverage_and_shortfalls_are_filled():
    a = pick_audit(FLAGGED, {"rare": 5, "mid": 2, "common": 2}, seed=1)
    rare_items = {k for k, c in FLAGGED if "rare" in c}
    assert len(rare_items & set(a)) == 5          # 'rare' pool has exactly 5 narratives (2 + 3 shared with 'common'): all selected
    assert len(a) == 9


def test_highlight_marks_and_merges_overlaps():
    rx = {"credentials": re.compile(r"password"), "financial": re.compile(r"account number"), "other": re.compile(r"password reset")}
    out = highlight("I shared my password reset and account number today.", rx)
    assert "«password reset»[credentials,other]" in out and "«account number»[financial]" in out
    assert highlight("nothing flagged here", rx) == "nothing flagged here"


def test_summary_counts_and_validation():
    rows = [{"item": "1", "category": "a", "verdict": "y"}, {"item": "2", "category": "a", "verdict": "n"}, {"item": "3", "category": "b", "verdict": "u"}]
    assert summarize(rows) == ({"a": {"y": 1, "n": 1}, "b": {"u": 1}}, {"y": 1, "n": 1, "u": 1})
    with pytest.raises(ValueError):
        summarize([{"item": "1", "category": "a", "verdict": ""}])
