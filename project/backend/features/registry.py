from __future__ import annotations

import numpy as np
import pandas as pd


def _reference_date_for_recency(order_dates: pd.Series) -> pd.Timestamp:
    """
    Recency için 'bugün': güncel veride gerçek tarih; tarihsel snapshot'ta
    veri setindeki son sipariş günü (Online Retail 2009–2011 vb.).
    """
    today = pd.Timestamp.today().normalize()
    parsed = pd.to_datetime(order_dates, errors="coerce")
    max_ts = parsed.max()
    if pd.isna(max_ts):
        return today
    max_ts = pd.Timestamp(max_ts).normalize()
    if (today - max_ts).days >= 365:
        return max_ts
    return today


def _churn_labels(
    recency_numeric: pd.Series,
    *,
    churn_strategy: str,
    churn_threshold_days: int,
    churn_quantile: float,
) -> tuple[pd.Series, float, str]:
    if churn_strategy == "fixed_days":
        threshold_used = float(churn_threshold_days)
        churn = recency_numeric > threshold_used
        return churn, threshold_used, churn_strategy

    if churn_strategy == "quantile":
        if not (0.0 < churn_quantile < 1.0):
            raise ValueError("churn_quantile 0 ile 1 arasında olmalı (örn. 0.70).")
        # Sık tekrarlayan recency değerlerinde strict > tek sınıf üretebilir; yüzdelik rank kullan.
        churn = recency_numeric.rank(method="first", pct=True) >= churn_quantile
        threshold_used = float(recency_numeric.quantile(churn_quantile))
        if pd.isna(threshold_used):
            raise ValueError("churn_quantile için yeterli recency verisi yok.")
        return churn, threshold_used, churn_strategy

    raise ValueError("Geçersiz churn_strategy. Geçerliler: fixed_days | quantile")


def _require_mapped_column(df: pd.DataFrame, column_map: dict, standard_key: str) -> str:
    if standard_key not in column_map:
        raise ValueError(f"column_map içinde '{standard_key}' tanımı yok.")
    col = column_map[standard_key]
    if col not in df.columns:
        raise ValueError(f"column_map['{standard_key}']='{col}' DataFrame kolonlarında yok.")
    return col


def build_customer_rfm_features(df: pd.DataFrame, column_map: dict, options: dict | None = None) -> pd.DataFrame:
    """
    Aggregates transaction-level data into customer-level RFM features:
    - recency_days: days since most recent order
    - frequency: number of unique orders (or rows if order_id missing)
    - monetary: total spend
    """
    customer_col = _require_mapped_column(df, column_map, "customer_id")
    order_date_col = _require_mapped_column(df, column_map, "order_date")

    df = df.copy()
    df[order_date_col] = pd.to_datetime(df[order_date_col], errors="coerce")

    order_id_col = column_map.get("order_id")
    qty_col = column_map.get("quantity")
    unit_price_col = column_map.get("unit_price")

    if qty_col and unit_price_col and qty_col in df.columns and unit_price_col in df.columns:
        df["_revenue"] = pd.to_numeric(df[qty_col], errors="coerce") * pd.to_numeric(
            df[unit_price_col], errors="coerce"
        )
    else:
        df["_revenue"] = np.nan

    reference_date = _reference_date_for_recency(df[order_date_col])

    grouped = df.groupby(customer_col, dropna=False)

    last_order = grouped[order_date_col].max()

    recency_days = (reference_date - last_order).dt.days.rename("recency_days").astype("Int64")

    if order_id_col and order_id_col in df.columns:
        frequency = grouped[order_id_col].nunique(dropna=True).rename("frequency")
    else:
        frequency = grouped.size().rename("frequency")

    monetary = grouped["_revenue"].sum(min_count=1).rename("monetary")

    out = pd.concat(
        [recency_days, frequency, monetary, last_order.rename("last_order_date")],
        axis=1,
    ).reset_index()
    out = out.rename(columns={customer_col: "customer_id"})

    # Standardize names expected by downstream churn pipeline
    # recency: days since last order
    out["recency"] = out["recency_days"].astype("Int64")
    out["frequency"] = pd.to_numeric(out["frequency"], errors="coerce")
    out["monetary"] = pd.to_numeric(out["monetary"], errors="coerce")

    # Convenience aliases
    out["order_count"] = out["frequency"]
    out["total_spent"] = out["monetary"]
    out["avg_order_value"] = out["monetary"] / out["frequency"].replace({0: np.nan})

    # --- Churn label strategy (agent decides, backend executes safely) ---
    opts = options or {}
    churn_strategy = str(opts.get("churn_strategy", "fixed_days"))
    churn_threshold_days = int(opts.get("churn_threshold_days", 90))
    churn_quantile = float(opts.get("churn_quantile", 0.70))

    recency_numeric = pd.to_numeric(out["recency"], errors="coerce")

    # Son sipariş tarihi olmayan müşteriler (NaT) → recency NA; int churn üretilemez
    valid_mask = recency_numeric.notna()
    if not bool(valid_mask.any()):
        raise ValueError(
            "Geçerli recency değeri olan müşteri yok. "
            "Tarih kolonunun parse edildiğinden ve cleaning_steps içinde parse_order_date "
            "(ve gerekirse diğer temizlik adımları) olduğundan emin olun."
        )
    out = out.loc[valid_mask].copy()
    recency_numeric = recency_numeric.loc[valid_mask]

    churn, threshold_used, strategy_used = _churn_labels(
        recency_numeric,
        churn_strategy=churn_strategy,
        churn_threshold_days=churn_threshold_days,
        churn_quantile=churn_quantile,
    )

    if churn.nunique(dropna=False) < 2 and churn_strategy != "quantile":
        churn, threshold_used, strategy_used = _churn_labels(
            recency_numeric,
            churn_strategy="quantile",
            churn_threshold_days=churn_threshold_days,
            churn_quantile=churn_quantile,
        )

    out["churn"] = churn.fillna(False).astype(np.int64)
    out["churn_threshold_used"] = threshold_used
    out["churn_strategy_used"] = strategy_used

    if out["churn"].nunique(dropna=False) < 2:
        raise ValueError(
            "Invalid churn label: only one class found. Try quantile strategy or different threshold."
        )

    return out


FEATURE_REGISTRY = {
    "build_customer_rfm_features": build_customer_rfm_features,
}

