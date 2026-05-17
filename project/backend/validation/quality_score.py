from __future__ import annotations

import math
from typing import Any, Literal, cast

from validation.schemas import (
    QualityBreakdown,
    QualityScoreResponse,
    UpliftValidationMetrics,
    ValidationMetrics,
)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _clamp100(x: float) -> float:
    return max(0.0, min(100.0, x))


def compute_uplift_quality_score(
    metrics: UpliftValidationMetrics | ValidationMetrics | dict[str, Any],
) -> QualityScoreResponse:
    if isinstance(metrics, dict):
        m = UpliftValidationMetrics.model_validate(metrics)
    elif isinstance(metrics, UpliftValidationMetrics):
        m = metrics
    else:
        m = UpliftValidationMetrics.model_validate(metrics.model_dump())

    ncr = m.null_customer_id_rate
    identity_quality = _clamp100(100.0 * (1.0 - min(1.0, ncr * 5.0)))

    treatment_quality = _clamp100(100.0 * _clamp01(m.treatment_parse_rate))
    if m.treatment_group_count < 2:
        treatment_quality = min(treatment_quality, 25.0)

    outcome_quality = _clamp100(100.0 * _clamp01(m.outcome_parse_rate))
    rate = m.outcome_rate
    if rate <= 0.0 or rate >= 1.0:
        outcome_quality = min(outcome_quality, 20.0)
    elif rate < 0.01:
        outcome_quality = min(outcome_quality, 55.0)

    t_sz = max(m.treatment_group_size, 1)
    c_sz = max(m.control_group_size, 1)
    balance_ratio = min(t_sz, c_sz) / max(t_sz, c_sz)
    group_balance = _clamp100(100.0 * balance_ratio)
    if min(t_sz, c_sz) < 50:
        group_balance = min(group_balance, 50.0)

    optional_feature_quality = _clamp100(min(100.0, m.optional_features_matched * 25.0))
    if m.event_date_parse_rate > 0:
        optional_feature_quality = _clamp100(
            0.6 * optional_feature_quality + 0.4 * (100.0 * _clamp01(m.event_date_parse_rate))
        )

    weights = {
        "identity_quality": 0.20,
        "treatment_quality": 0.25,
        "outcome_quality": 0.25,
        "group_balance": 0.20,
        "optional_feature_quality": 0.10,
    }
    breakdown = QualityBreakdown(
        identity_quality=round(identity_quality, 2),
        treatment_quality=round(treatment_quality, 2),
        outcome_quality=round(outcome_quality, 2),
        group_balance=round(group_balance, 2),
        optional_feature_quality=round(optional_feature_quality, 2),
    )
    overall = (
        weights["identity_quality"] * breakdown.identity_quality
        + weights["treatment_quality"] * (breakdown.treatment_quality or 0)
        + weights["outcome_quality"] * (breakdown.outcome_quality or 0)
        + weights["group_balance"] * (breakdown.group_balance or 0)
        + weights["optional_feature_quality"] * (breakdown.optional_feature_quality or 0)
    )
    overall = round(_clamp100(overall), 2)
    level = _score_level(overall)
    return QualityScoreResponse(overall_score=overall, level=level, breakdown=breakdown, weights=weights)


def _score_level(overall: float) -> Literal["good", "warning", "poor"]:
    if overall >= 80:
        return cast(Literal["good", "warning", "poor"], "good")
    if overall >= 60:
        return cast(Literal["good", "warning", "poor"], "warning")
    return cast(Literal["good", "warning", "poor"], "poor")


def compute_quality_score(
    metrics: ValidationMetrics | dict[str, Any],
    *,
    template: str = "churn",
) -> QualityScoreResponse:
    if template == "uplift":
        return compute_uplift_quality_score(metrics)
    """
    Ağırlıklar (öneri):
    identity 25%, date 25%, transaction 20%, customer_depth 15%, duplicate 10%, distribution 5%.
    """
    if isinstance(metrics, dict):
        m = ValidationMetrics.model_validate(metrics)
    else:
        m = metrics

    # --- identity_quality (null / boş müşteri kimliği) ---
    ncr = m.null_customer_id_rate
    identity_quality = _clamp100(100.0 * (1.0 - min(1.0, ncr * 5.0)))

    # --- date_quality (parse + tarih aralığı genişliği) ---
    dpr = m.date_parse_rate
    parse_component = 100.0 * _clamp01(dpr)
    hd = m.history_days
    if hd is None or hd <= 0:
        span_component = 40.0
    else:
        span_component = _clamp100(100.0 * math.log1p(hd) / math.log1p(730))
    date_quality = _clamp100(0.55 * parse_component + 0.45 * span_component)

    # --- transaction_quality (negatif miktar, fiyat <= 0, sıfır miktar) ---
    nqr = m.negative_quantity_rate
    zqr = m.zero_quantity_rate
    pnp = m.non_positive_price_rate
    tx_penalty = min(
        1.0,
        nqr * 6.0 + zqr * 1.5 + pnp * 6.0,
    )
    transaction_quality = _clamp100(100.0 * (1.0 - tx_penalty))

    # --- customer_depth (benzersiz müşteri + işlem başına satır) ---
    row_count = max(1, m.row_count)
    ec = max(0, m.estimated_customer_count)
    density = (row_count / ec) if ec > 0 else 0.0
    uniq_ratio = ec / row_count if row_count else 0.0
    depth_from_uniq = _clamp100(min(100.0, uniq_ratio * 400.0))
    depth_from_density = _clamp100(min(100.0, (math.log1p(density) / math.log1p(50)) * 100.0))
    customer_depth = _clamp100(0.5 * depth_from_uniq + 0.5 * depth_from_density)

    # --- duplicate_quality ---
    dup = m.duplicate_rate
    duplicate_quality = _clamp100(100.0 * (1.0 - min(1.0, dup * 8.0)))

    # --- distribution_sanity (hafif: tarih parse düşükse zaten date_quality düşer; burada ceza yok) ---
    distribution_sanity = 85.0
    if hd is not None and hd < 14:
        distribution_sanity = 55.0
    if dpr < 0.85:
        distribution_sanity = min(distribution_sanity, 60.0)
    distribution_sanity = _clamp100(distribution_sanity)

    weights = {
        "identity_quality": 0.25,
        "date_quality": 0.25,
        "transaction_quality": 0.20,
        "customer_depth": 0.15,
        "duplicate_quality": 0.10,
        "distribution_sanity": 0.05,
    }
    breakdown = QualityBreakdown(
        identity_quality=round(identity_quality, 2),
        date_quality=round(date_quality, 2),
        transaction_quality=round(transaction_quality, 2),
        customer_depth=round(customer_depth, 2),
        duplicate_quality=round(duplicate_quality, 2),
        distribution_sanity=round(distribution_sanity, 2),
    )
    overall = (
        weights["identity_quality"] * breakdown.identity_quality
        + weights["date_quality"] * breakdown.date_quality
        + weights["transaction_quality"] * breakdown.transaction_quality
        + weights["customer_depth"] * breakdown.customer_depth
        + weights["duplicate_quality"] * breakdown.duplicate_quality
        + weights["distribution_sanity"] * breakdown.distribution_sanity
    )
    overall = round(_clamp100(overall), 2)

    level = _score_level(overall)

    return QualityScoreResponse(overall_score=overall, level=level, breakdown=breakdown, weights=weights)
