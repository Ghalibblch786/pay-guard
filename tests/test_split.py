"""Leakage guards for the time split (uses the real CSV; skipped if it is not downloaded)."""
import pandas as pd
import pytest

from part_a.data import CSV, time_split

pytestmark = pytest.mark.skipif(not CSV.exists(), reason="creditcard.csv not downloaded")


def synthetic():
    # many timestamp ties on purpose: every timestamp appears 3 times
    return pd.DataFrame({"Time": [t for t in range(100) for _ in range(3)], "Class": 0})


def test_empty_split_raises():
    df = pd.DataFrame({"Time": [0] * 50 + [1] * 50, "Class": 0})
    with pytest.raises(ValueError):
        time_split(df)


def test_time_ordering_and_ties_synthetic():
    df = synthetic().sort_values("Time", kind="stable").reset_index(drop=True)
    tr, va, te = time_split(df)
    assert len(tr) + len(va) + len(te) == len(df)
    assert tr.Time.max() < va.Time.min() and va.Time.max() < te.Time.min()  # strict: no shared timestamp


def test_real_split_no_leakage_and_no_overlap():
    from part_a.data import load

    df = load()
    tr, va, te = time_split(df)
    assert len(tr) + len(va) + len(te) == len(df)
    assert tr.Time.max() < va.Time.min() and va.Time.max() < te.Time.min()
    assert not (set(tr.index) & set(va.index)) and not (set(va.index) & set(te.index))
    assert df.duplicated().sum() == 0
