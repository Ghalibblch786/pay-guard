"""Part A metrics. PR-AUC (average precision) is the headline metric; accuracy is never reported."""
import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_curve, roc_auc_score

from config import SEED


def pr_auc_with_ci(y, scores, n_boot: int = 1000, seed: int = SEED):
    """PR-AUC plus a 95% percentile bootstrap CI (resampling rows of one fixed split).

    Captures sampling noise from the small number of frauds only; it does not capture
    uncertainty from choosing this particular time split.
    """
    y, scores = np.asarray(y), np.asarray(scores)
    rng = np.random.default_rng(seed)
    point = average_precision_score(y, scores)
    boots = []
    while len(boots) < n_boot:
        idx = rng.integers(0, len(y), len(y))
        if y[idx].sum() == 0:  # resample with no frauds: AP undefined, redraw
            continue
        boots.append(average_precision_score(y[idx], scores[idx]))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return point, lo, hi


def threshold_for_precision(y, scores, min_precision: float = 0.90):
    """Lowest threshold whose precision >= min_precision (i.e. the highest recall that
    satisfies the constraint). Returns None if no threshold reaches it.

    Note: choosing a threshold and reporting recall on the same data is optimistic.
    Use it only on validation, then apply the frozen threshold to test.
    """
    prec, rec, thr = precision_recall_curve(y, scores)
    ok = np.where(prec[:-1] >= min_precision)[0]  # prec has one more entry than thr
    if len(ok) == 0:
        return None
    best = ok[np.argmax(rec[ok])]
    return float(thr[best])


def report_at_threshold(y, scores, threshold: float) -> dict:
    """Confusion matrix, precision and recall at a fixed threshold."""
    pred = (np.asarray(scores) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred).ravel()
    return {
        "threshold": threshold, "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "precision": tp / (tp + fp) if tp + fp else float("nan"),
        "recall": tp / (tp + fn) if tp + fn else float("nan"),
    }


def calibration_summary(y, scores, bins=(0, 0.1, 0.5, 0.9, 1.0001)) -> list[dict]:
    """Mean predicted probability vs observed fraud rate in fixed score bins.

    Bins are fixed (not quantile) because 99.8% of rows are non-fraud: quantile bins would
    be nearly all zeros. A calibrated model has mean_pred ~= observed_rate in every bin.
    """
    y, scores = np.asarray(y), np.asarray(scores)
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (scores >= lo) & (scores < hi)
        if m.sum():
            rows.append({"bin": f"[{lo:.1f},{min(hi, 1):.1f})", "n": int(m.sum()),
                         "mean_pred": float(scores[m].mean()), "observed_rate": float(y[m].mean())})
    return rows


def summarize(y, scores) -> dict:
    point, lo, hi = pr_auc_with_ci(y, scores)
    return {"pr_auc": point, "pr_auc_ci95": [lo, hi], "roc_auc_secondary": roc_auc_score(y, scores),
            "n": int(len(y)), "n_fraud": int(np.sum(y)), "base_rate": float(np.mean(y))}
