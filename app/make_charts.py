"""Draw the two README charts from the saved result files. No model is run.   python -m app.make_charts"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app import engine

OURS, OTHER, INK = "#3b5b7a", "#c4c4c4", "#333333"
OUT = engine.ROOT / "docs" / "images"


def panel(ax, title: str, labels: list, values: list, top: int) -> None:
    """One small bar chart: the first bar is ours (blue), the rest are comparisons (grey)."""
    bars = ax.barh(labels, values, color=[OURS] + [OTHER] * (len(values) - 1), height=0.6)
    ax.bar_label(bars, padding=4, color=INK)
    ax.set_title(title, loc="left", fontsize=11, color=INK)
    ax.set_xlim(0, top * 1.15)
    ax.invert_yaxis()
    ax.set_xticks([])
    ax.tick_params(length=0, labelcolor=INK)
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(OTHER)


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(w_pad=3)
    fig.savefig(OUT / name, dpi=150, facecolor="white")
    plt.close(fig)


def fraud_chart() -> None:
    test = engine.read_json("m2_test_results.json")
    options = [("Suggested", "logreg", "B"), ("Same model,\nother rule", "logreg", "A"), ("Stronger model,\nsame rule", "xgboost", "B")]
    rows = [test["models"][model]["rules"][f"rule_{rule}_c=5.0"] for _, model, rule in options]
    names = [name for name, _, _ in options]
    fig, (left, right) = plt.subplots(1, 2, figsize=(9, 2.6))
    panel(left, f"Frauds caught, out of {test['n_fraud']} (higher is better)", names, [r["tp"] for r in rows], test["n_fraud"])
    panel(right, "False alarms (lower is better)", names, [r["fp"] for r in rows], max(r["fp"] for r in rows))
    save(fig, "fraud_results.png")


def complaint_chart() -> None:
    c = engine.complaint_summary()
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 2.2))
    panel(axes[0], f"Right team, of {c['category_n']}", ["Model", "Simple guess"], [c["category_right"], c["category_guess"]], c["category_n"])
    panel(axes[1], f"Right urgency, of {c['category_n']}", ["Model", "Simple guess"], [c["urgency_right"], c["urgency_guess"]], c["category_n"])
    panel(axes[2], f"Needing a person, of {c['labeled']}", ["System sent", "Really needed"], [c["labeled_sent"], c["labeled_needed"]], c["labeled"])
    save(fig, "complaint_results.png")


if __name__ == "__main__":
    fraud_chart()
    complaint_chart()
    print(f"wrote charts to {OUT.relative_to(engine.ROOT)}")
