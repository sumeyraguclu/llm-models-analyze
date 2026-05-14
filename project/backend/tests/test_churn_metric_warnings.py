"""ChurnPipeline: küçük test seti / sahte yüksek metrik uyarıları."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml.churn import ChurnPipeline


def test_small_test_set_emits_variance_warning():
    n = 35
    rng = np.random.default_rng(0)
    rec = rng.uniform(20.0, 200.0, size=n)
    churn = (rec > 90).astype(np.int64)
    df = pd.DataFrame(
        {
            "recency": rec,
            "monetary": rng.uniform(50.0, 5000.0, size=n),
            "churn": churn,
        }
    )
    pipe = ChurnPipeline(churn_days=90)
    pipe.fit(df)
    m = pipe.metrics(df)
    warns = m.get("metric_warnings") or []
    assert any("küçük" in w.lower() or "n_test" in w for w in warns)


def test_perfect_separation_triggers_skepticism_warning():
    """Deterministik veri: recency eşiği churn ile uyumlu → çok yüksek skor + uyarı."""
    n = 400
    rec = np.linspace(10.0, 250.0, n)
    churn = (rec > 100.0).astype(np.int64)
    df = pd.DataFrame(
        {
            "recency": rec,
            "monetary": np.linspace(100.0, 5000.0, n),
            "churn": churn,
        }
    )
    pipe = ChurnPipeline(churn_days=90)
    pipe.fit(df)
    m = pipe.metrics(df)
    warns = [w for w in (m.get("metric_warnings") or []) if isinstance(w, str)]
    assert m["accuracy"] >= 0.95
    assert any("Perfect metrics" in w or "perfect" in w.lower() for w in warns)
