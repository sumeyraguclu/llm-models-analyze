"""AnalysisPlanSchema: template, cleaning_steps, feature_plan sınırları."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.analysis_plan import AnalysisPlanSchema


def test_invalid_template():
    with pytest.raises(ValidationError):
        AnalysisPlanSchema(
            template="unknown_tmpl",
            column_map={"customer_id": "c"},
            cleaning_steps=["drop_rows_missing_customer_id"],
            feature_plan=["build_customer_rfm_features"],
        )


def test_unknown_cleaning_in_schema():
    with pytest.raises(ValidationError, match="Bilinmeyen cleaning"):
        AnalysisPlanSchema(
            template="churn",
            column_map={"customer_id": "c"},
            cleaning_steps=["fake_step"],
            feature_plan=["build_customer_rfm_features"],
        )


def test_feature_plan_max_one_step():
    with pytest.raises(ValidationError, match="en fazla 1"):
        AnalysisPlanSchema(
            template="churn",
            column_map={"customer_id": "c"},
            cleaning_steps=["drop_rows_missing_customer_id"],
            feature_plan=["build_customer_rfm_features", "build_customer_rfm_features"],
        )


def test_churn_gets_default_options():
    p = AnalysisPlanSchema(
        template="churn",
        column_map={"customer_id": "c"},
        cleaning_steps=["drop_rows_missing_customer_id"],
        feature_plan=["build_customer_rfm_features"],
    )
    assert p.options is not None
    assert p.options.churn_strategy in ("fixed_days", "quantile")
