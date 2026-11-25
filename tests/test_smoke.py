"""M0 smoke test: core dependencies import and the XGBoost native library loads."""
import numpy as np


def test_imports():
    import pandas, sklearn, pydantic, yaml, matplotlib  # noqa: F401
    from google import genai  # noqa: F401


def test_xgboost_trains():
    import xgboost as xgb

    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 4))
    y = (X[:, 0] > 0).astype(int)
    model = xgb.XGBClassifier(n_estimators=5).fit(X, y)
    assert model.predict(X).shape == (200,)
