from __future__ import annotations

import pandas as pd


def _require_mapped_column(df: pd.DataFrame, column_map: dict, standard_key: str) -> str:
    if standard_key not in column_map:
        raise ValueError(f"column_map içinde '{standard_key}' tanımı yok.")
    col = column_map[standard_key]
    if col not in df.columns:
        raise ValueError(f"column_map['{standard_key}']='{col}' DataFrame kolonlarında yok.")
    return col


def drop_rows_missing_customer_id(df: pd.DataFrame, column_map: dict) -> pd.DataFrame:
    col = _require_mapped_column(df, column_map, "customer_id")
    return df.dropna(subset=[col])


def parse_order_date(df: pd.DataFrame, column_map: dict) -> pd.DataFrame:
    col = _require_mapped_column(df, column_map, "order_date")
    df = df.copy()
    df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def remove_negative_quantity(df: pd.DataFrame, column_map: dict) -> pd.DataFrame:
    col = _require_mapped_column(df, column_map, "quantity")
    df = df.copy()
    qty = pd.to_numeric(df[col], errors="coerce")
    return df.loc[qty.isna() | (qty >= 0)]


def remove_non_positive_price(df: pd.DataFrame, column_map: dict) -> pd.DataFrame:
    col = _require_mapped_column(df, column_map, "unit_price")
    df = df.copy()
    price = pd.to_numeric(df[col], errors="coerce")
    return df.loc[price.isna() | (price > 0)]


CLEANING_REGISTRY = {
    "drop_rows_missing_customer_id": drop_rows_missing_customer_id,
    "parse_order_date": parse_order_date,
    "remove_negative_quantity": remove_negative_quantity,
    "remove_non_positive_price": remove_non_positive_price,
}

