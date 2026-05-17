"""
E-ticaret işlem CSV'leri için deterministik doğrulama (pandas).
LLM kullanılmaz; kolon çözümlemesi `services.column_matching` ile yapılır.
"""

from __future__ import annotations

import warnings
from typing import Any

import pandas as pd

from services.column_matching import ALL_STANDARDS, FieldMatch, match_columns_hybrid
from templates.registry import get_template_spec
from validation.schemas import ValidationMetrics, ValidationReport
from validation.quality_score import compute_quality_score

# Geriye dönük import (CHURN_* sabitleri dışarıdan kullanılıyorsa)
CHURN_RECOMMENDED_UNIQUE_CUSTOMERS = 100
CHURN_RECOMMENDED_TX_ROWS = 500


def _accepted_column(m: FieldMatch) -> str | None:
    if not m.matched_column:
        return None
    if m.method in ("exact", "alias"):
        return m.matched_column
    if m.method == "fuzzy" and m.confidence >= 0.78:
        return m.matched_column
    return None


def _parse_order_dates(series: pd.Series) -> tuple[pd.Series, float]:
    """Profil ile uyumlu çoklu format + düşüşte dateutil."""
    as_str = series.astype(str)
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ]
    best: pd.Series | None = None
    best_valid = 0.0
    for fmt in formats:
        p = pd.to_datetime(as_str, format=fmt, errors="coerce", utc=True)
        v = float(p.notna().mean()) if len(p) else 0.0
        if v > best_valid:
            best_valid = v
            best = p
    if best is not None and best_valid >= 0.5:
        return best, float(best_valid)

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Could not infer format.*",
            category=UserWarning,
        )
        fb = pd.to_datetime(as_str, errors="coerce", utc=True)
    return fb, float(fb.notna().mean()) if len(fb) else 0.0


def _series_non_empty_mask(s: pd.Series) -> pd.Series:
    if s.dtype == object or pd.api.types.is_string_dtype(s):
        t = s.astype(str).str.strip()
        return s.notna() & t.ne("") & t.str.lower().ne("nan") & t.str.lower().ne("none")
    return s.notna()


def validate_ecommerce_dataframe(df: pd.DataFrame, *, template: str = "churn") -> ValidationReport:
    if df is None or df.empty:
        return ValidationReport(
            is_valid=False,
            errors=["Veri çerçevesi boş."],
            warnings=[],
            metrics=ValidationMetrics(row_count=0),
            resolved_columns={k: None for k in ALL_STANDARDS},
        )

    row_count = int(len(df))
    col_names = [str(c) for c in df.columns]
    report = match_columns_hybrid(col_names)
    resolved: dict[str, str | None] = {std: _accepted_column(report.fields[std]) for std in ALL_STANDARDS}

    try:
        tmpl = get_template_spec(template)
    except ValueError:
        tmpl = get_template_spec("churn")

    rec_cust = tmpl.validation_recommended_unique_customers()
    rec_rows = tmpl.validation_recommended_tx_rows()
    label = tmpl.validation_region_hint()

    errors: list[str] = []
    warnings: list[str] = []

    cust_col = resolved.get("customer_id")
    date_col = resolved.get("order_date")
    qty_col = resolved.get("quantity")
    price_col = resolved.get("unit_price")
    order_col = resolved.get("order_id")

    for std in ("customer_id", "order_date"):
        m = report.fields.get(std)
        if m and m.method == "fuzzy" and m.matched_column:
            warnings.append(
                f"{std} kolonu fuzzy eşleşme ile seçildi ({m.matched_column}); doğrulama önerilir."
            )

    if not cust_col:
        errors.append("customer_id kolonu güvenilir şekilde eşleştirilemedi (exact/alias/fuzzy).")
    if not date_col:
        errors.append("order_date (sipariş tarihi) kolonu güvenilir şekilde eşleştirilemedi.")

    null_customer_id_rate = 0.0
    estimated_customer_count = 0
    date_parse_rate = 0.0
    history_days: int | None = None
    negative_quantity_rate = 0.0
    zero_quantity_rate = 0.0
    non_positive_price_rate = 0.0
    duplicate_rate = 0.0
    transactions_per_customer: float | None = None

    if not cust_col:
        null_customer_id_rate = 1.0
    if not date_col:
        date_parse_rate = 0.0

    if cust_col and cust_col in df.columns:
        s = df[cust_col]
        valid = _series_non_empty_mask(s)
        null_customer_id_rate = float(1.0 - (valid.sum() / row_count)) if row_count else 1.0
        estimated_customer_count = int(s[valid].nunique())
        if null_customer_id_rate > 0.25:
            errors.append(
                f"Müşteri kimliği çok fazla boş veya geçersiz (oran={null_customer_id_rate:.2%})."
            )
        elif null_customer_id_rate > 0.05:
            warnings.append(
                f"Müşteri kimliği boş oranı yüksek ({null_customer_id_rate:.2%}); temizlik önerilir."
            )
    elif cust_col:
        errors.append(f"Eşlenen customer_id kolonu DataFrame'de yok: {cust_col!r}.")

    if date_col and date_col in df.columns:
        parsed, dpr = _parse_order_dates(df[date_col])
        date_parse_rate = float(dpr)
        pv = parsed.dropna()
        if len(pv) >= 2:
            delta = (pv.max() - pv.min()).days
            history_days = int(max(0, delta))
        if date_parse_rate < 0.60:
            errors.append(
                f"Sipariş tarihi çoğu satırda parse edilemedi (oran={date_parse_rate:.2%})."
            )
        elif date_parse_rate < 0.95:
            warnings.append(
                f"Sipariş tarihi parse oranı düşük ({date_parse_rate:.2%}); tarih formatını kontrol edin."
            )
        if history_days is not None and history_days < 30:
            warnings.append(f"Tarih aralığı dar (yaklaşık {history_days} gün); sezonsallık sınırlı olabilir.")
        elif history_days is not None and history_days < 180:
            warnings.append(
                f"Tarih aralığı {history_days} gün; uzun dönem churn davranışı için daha fazla geçmiş önerilir."
            )
    elif date_col:
        errors.append(f"Eşlenen order_date kolonu DataFrame'de yok: {date_col!r}.")

    if qty_col and qty_col in df.columns:
        q = pd.to_numeric(df[qty_col], errors="coerce")
        denom = int(q.notna().sum())
        if denom > 0:
            negative_quantity_rate = float((q < 0).sum() / denom)
            zero_quantity_rate = float((q == 0).sum() / denom)
        if negative_quantity_rate > 0.0:
            warnings.append(f"Negatif miktar oranı: {negative_quantity_rate:.2%}.")
        if zero_quantity_rate > 0.05:
            warnings.append(f"Sıfır miktar oranı yüksek: {zero_quantity_rate:.2%}.")
    else:
        warnings.append("quantity kolonu eşleştirilemedi; miktar kalitesi hesaplanmadı.")

    if price_col and price_col in df.columns:
        p = pd.to_numeric(df[price_col], errors="coerce")
        denom = int(p.notna().sum())
        if denom > 0:
            non_positive_price_rate = float((p <= 0).sum() / denom)
        if non_positive_price_rate > 0.0:
            warnings.append(f"Sıfır veya negatif birim fiyat oranı: {non_positive_price_rate:.2%}.")
    else:
        warnings.append("unit_price kolonu eşleştirilemedi; fiyat kalitesi hesaplanmadı.")

    # duplicate transaction oranı
    dup_subset: list[str] = []
    if cust_col and cust_col in df.columns:
        dup_subset.append(cust_col)
    if date_col and date_col in df.columns:
        dup_subset.append(date_col)
    if order_col and order_col in df.columns:
        dup_subset.append(order_col)
    if len(dup_subset) >= 2:
        duplicate_rate = float(df.duplicated(subset=dup_subset, keep=False).mean())
        if duplicate_rate > 0.15:
            warnings.append(f"Yinelenen işlem satırı oranı yüksek: {duplicate_rate:.2%}.")
        elif duplicate_rate > 0.02:
            warnings.append(f"Yinelenen işlem satırı oranı: {duplicate_rate:.2%}.")

    if cust_col and cust_col in df.columns and estimated_customer_count > 0:
        transactions_per_customer = round(row_count / estimated_customer_count, 4)

    if estimated_customer_count > 0:
        if estimated_customer_count < rec_cust:
            warnings.append(
                f"Tahmini benzersiz müşteri sayısı {estimated_customer_count}; "
                f"{label} için genelde en az {rec_cust} müşteri önerilir."
            )
        if row_count < rec_rows:
            warnings.append(
                f"İşlem satırı sayısı {row_count}; daha güvenilir modeller için "
                f"~{rec_rows}+ satır önerilir ({label})."
            )

    is_valid = len(errors) == 0

    metrics = ValidationMetrics(
        row_count=row_count,
        estimated_customer_count=estimated_customer_count,
        date_parse_rate=round(date_parse_rate, 4),
        null_customer_id_rate=round(null_customer_id_rate, 4),
        negative_quantity_rate=round(negative_quantity_rate, 4),
        non_positive_price_rate=round(non_positive_price_rate, 4),
        duplicate_rate=round(duplicate_rate, 4),
        history_days=history_days,
        transactions_per_customer=transactions_per_customer,
        zero_quantity_rate=round(zero_quantity_rate, 4),
        churn_data_sufficient=tmpl.compute_training_data_sufficient(
            is_valid=is_valid,
            estimated_customer_count=estimated_customer_count,
            row_count=row_count,
        ),
    )

    return ValidationReport(
        is_valid=is_valid,
        errors=errors,
        warnings=_dedupe_preserve(warnings),
        metrics=metrics,
        resolved_columns=resolved,
    )


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def run_validation_and_quality(df: pd.DataFrame, *, template: str = "churn") -> tuple[dict[str, Any], dict[str, Any]]:
    """API katmanı için: validation dict + quality dict."""
    from validation.dispatch import validate_dataframe

    vr = validate_dataframe(df, template=template)
    q = compute_quality_score(vr.metrics, template=template)
    return vr.model_dump(), q.model_dump()
