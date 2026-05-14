from __future__ import annotations

import math
from typing import Any, Literal, cast

from validation.schemas import QualityBreakdown, QualityScoreResponse, ValidationMetrics


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _clamp100(x: float) -> float:
    return max(0.0, min(100.0, x))


def compute_quality_score(metrics: ValidationMetrics | dict[str, Any]) -> QualityScoreResponse:
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

    if overall >= 80:
        level = cast(Literal["good", "warning", "poor"], "good")
    elif overall >= 60:
        level = cast(Literal["good", "warning", "poor"], "warning")
    else:
        level = cast(Literal["good", "warning", "poor"], "poor")

    return QualityScoreResponse(overall_score=overall, level=level, breakdown=breakdown, weights=weights)
