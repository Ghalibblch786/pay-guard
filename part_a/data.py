"""Part A data loading and time-ordered splitting."""
import pandas as pd

from config import DATA_RAW

CSV = DATA_RAW / "creditcard.csv"
FEATURES = ["Time"] + [f"V{i}" for i in range(1, 29)] + ["Amount"]
TARGET = "Class"


def load(drop_duplicates: bool = True) -> pd.DataFrame:
    """Load the CSV in original (time) order. Exact duplicate rows are dropped by default.

    Decision (see README/SPECS): exact duplicates share the same Time, so they cannot straddle
    splits; they are dropped because they would double-count the same event in training and
    inflate evaluation counts. Pass False to keep them.
    """
    df = pd.read_csv(CSV)
    if drop_duplicates:
        df = df.drop_duplicates(keep="first")
    # stable sort: ties on Time keep original file order
    return df.sort_values("Time", kind="stable").reset_index(drop=True)


def split_cuts(df: pd.DataFrame, train_frac: float = 0.70, val_frac: float = 0.15):
    """Time values where validation and test begin. Uses only the Time column."""
    n = len(df)
    return df["Time"].iloc[int(n * train_frac)], df["Time"].iloc[int(n * (train_frac + val_frac))]


def time_chunks(df: pd.DataFrame, n: int) -> list[pd.DataFrame]:
    """Cut a time-sorted frame into n consecutive chunks at Time VALUES (ties never straddle chunks)."""
    cuts = [df["Time"].iloc[len(df) * i // n] for i in range(1, n)]
    if len(set(cuts)) < len(cuts):
        raise ValueError("Duplicate cut values: too many timestamp ties")
    edges = [-float("inf")] + cuts + [float("inf")]
    return [df[(df["Time"] >= a) & (df["Time"] < b)] for a, b in zip(edges[:-1], edges[1:])]


def time_split(df: pd.DataFrame, train_frac: float = 0.70, val_frac: float = 0.15):
    """Split by Time VALUE (not row index) into train / val / test.

    Cut points are the Time values found at the 70% and 85% row positions. A row goes to the
    later split if its Time equals the cut value, so rows sharing a timestamp never straddle
    two splits. Split sizes are therefore approximate (ties make them slightly uneven).
    """
    t_val, t_test = split_cuts(df, train_frac, val_frac)
    train = df[df["Time"] < t_val]
    val = df[(df["Time"] >= t_val) & (df["Time"] < t_test)]
    test = df[df["Time"] >= t_test]
    if min(len(train), len(val), len(test)) == 0:
        raise ValueError("Empty split: too many timestamp ties for these fractions")
    return train, val, test
