from itertools import combinations
import logging
import warnings

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

import database

from database import get_db
from models import Dataset

router = APIRouter()
logger = logging.getLogger(__name__)


class ProfileResponse(BaseModel):
    dataset_id: int
    table_name: str
    profile: dict


def _as_iso_date(dt: pd.Timestamp | None) -> str | None:
    if dt is None or pd.isna(dt):
        return None
    if isinstance(dt, pd.Timestamp):
        # normalize to date-only ISO string where possible
        if dt.tzinfo is not None:
            dt = dt.tz_convert("UTC")
        return dt.to_pydatetime().date().isoformat()
    return None


def _is_datetime_candidate(series: pd.Series, column_name: str) -> bool:
    """
    Heuristic filter to avoid parsing every object column as datetime.

    Candidate if:
    - dtype is object or string, AND
    - column name has date/time keywords OR sample values frequently contain date/time separators
      like '-', '/', ':'
    """
    try:
        if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
            return False

        name = (column_name or "").lower()
        if any(k in name for k in ["date", "time", "created", "updated"]):
            return True

        sample = series.dropna().astype(str).head(20)
        if sample.empty:
            return False

        # proportion of sample values that look date-like by having separators
        pattern_hits = float(sample.str.contains(r"[-/:]").mean())
        return pattern_hits > 0.5
    except Exception:
        return False


def _infer_date_range(series: pd.Series) -> dict | None:
    """
    Best-effort detection for date-like columns.
    Only considers non-numeric columns (plus true datetime dtype).
    Returns {min, max, valid_pct, null_pct} if confidently date-like.
    """
    non_null = series.dropna()
    if len(series) == 0:
        return None

    null_pct = float(round((int(series.isna().sum()) / len(series)) * 100, 2))

    def safe_parse_datetime(s: pd.Series, *, column_name: str) -> pd.Series:
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
        ]

        best_parsed: pd.Series | None = None
        best_valid = 0.0
        best_fmt: str | None = None

        for fmt in formats:
            parsed = pd.to_datetime(s, format=fmt, errors="coerce", utc=True)
            valid = float(parsed.notna().mean()) if len(parsed) else 0.0
            if valid > best_valid:
                best_valid = valid
                best_parsed = parsed
                best_fmt = fmt

        if best_parsed is not None and best_valid > 0.8:
            logger.info(
                "Datetime parse selected format for '%s': fmt=%s valid_ratio=%.3f",
                column_name,
                best_fmt,
                best_valid,
            )
            return best_parsed

        # Fallback: allow pandas/dateutil parsing, but suppress the format inference warning
        logger.warning(
            "Datetime parse fallback for '%s': best_fmt=%s best_valid_ratio=%.3f (threshold=0.800)",
            column_name,
            best_fmt,
            best_valid,
        )
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Could not infer format, so each element will be parsed individually, falling back to dateutil.*",
                category=UserWarning,
            )
            return pd.to_datetime(s, errors="coerce", utc=True)

    if pd.api.types.is_datetime64_any_dtype(series):
        parsed = safe_parse_datetime(non_null, column_name=str(series.name))
    else:
        if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
            return None
        # parsing ints as timestamps is a common false positive; restrict to string/object-like
        if not (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
            or pd.api.types.is_categorical_dtype(series)
        ):
            return None
        parsed = safe_parse_datetime(non_null.astype(str), column_name=str(series.name))

    if parsed.empty:
        return None

    valid_pct = float(round((parsed.notna().mean()) * 100, 2))
    if valid_pct < 80.0:
        return None

    parsed_valid = parsed.dropna()
    if parsed_valid.empty or parsed_valid.nunique() < 2:
        return None

    # guardrails against numeric-ID misparses: keep dates in a reasonable window
    min_dt = parsed_valid.min()
    max_dt = parsed_valid.max()
    if min_dt.year < 1900 or max_dt.year > 2100:
        return None

    return {
        "min": _as_iso_date(min_dt),
        "max": _as_iso_date(max_dt),
        "valid_pct": valid_pct,
        "null_pct": null_pct,
    }


def _pick_best_date_column(date_ranges: dict[str, dict]) -> str | None:
    """
    Picks the date column with the latest max date.
    """
    best_col = None
    best_max = None
    for col, info in (date_ranges or {}).items():
        if not isinstance(info, dict):
            continue
        max_iso = info.get("max")
        if not isinstance(max_iso, str) or not max_iso:
            continue
        try:
            d = pd.to_datetime(max_iso, errors="raise")
        except Exception:
            continue
        if best_max is None or d > best_max:
            best_max = d
            best_col = col
    return best_col


def _compute_recency_percentiles(df: pd.DataFrame, date_col: str) -> dict | None:
    """
    Computes recency distribution percentiles based on a chosen date column.
    Recency is defined as (today - date_col) in days.
    """
    if date_col not in df.columns:
        return None

    # Use deterministic parsing strategy to avoid slow inference warnings.
    non_null = df[date_col].dropna()
    if non_null.empty:
        return None

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ]

    best = None
    best_valid = 0.0
    best_fmt = None
    as_str = df[date_col].astype(str)
    for fmt in formats:
        p = pd.to_datetime(as_str, format=fmt, errors="coerce", utc=True)
        valid = float(p.notna().mean()) if len(p) else 0.0
        if valid > best_valid:
            best_valid = valid
            best = p
            best_fmt = fmt

    if best is not None and best_valid > 0.8:
        logger.info(
            "Recency datetime parse selected format for '%s': fmt=%s valid_ratio=%.3f",
            date_col,
            best_fmt,
            best_valid,
        )
        parsed = best
    else:
        logger.warning(
            "Recency datetime parse fallback for '%s': best_fmt=%s best_valid_ratio=%.3f (threshold=0.800)",
            date_col,
            best_fmt,
            best_valid,
        )
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Could not infer format, so each element will be parsed individually, falling back to dateutil.*",
                category=UserWarning,
            )
            parsed = pd.to_datetime(as_str, errors="coerce", utc=True)

    today = pd.Timestamp.today(tz="UTC").normalize()
    recency = (today - parsed).dt.days
    recency = pd.to_numeric(recency, errors="coerce").dropna()
    if recency.empty:
        return None

    percentiles = {}
    for p in [0.5, 0.7, 0.8, 0.9, 0.95]:
        try:
            percentiles[f"p{int(p*100)}"] = float(recency.quantile(p))
        except Exception:
            continue

    if not percentiles:
        return None

    return {
        "source_column": date_col,
        "unit": "days",
        "percentiles": percentiles,
        "count": int(recency.shape[0]),
    }


@router.post("/profile/{table_name}", response_model=ProfileResponse)
def build_profile(table_name: str, db: Session = Depends(get_db)):
    try:
        dataset = db.query(Dataset).filter(Dataset.table_name == table_name).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset bulunamadı.")

        query = text(f'SELECT * FROM "{table_name}"')
        df = pd.read_sql_query(query, database.engine)
        if df.empty:
            raise HTTPException(status_code=400, detail="Profil üretilecek veri bulunamadı.")

        columns = []
        date_ranges: dict[str, dict] = {}
        skipped_datetime_candidates: list[str] = []
        attempted_datetime_parse: list[str] = []
        detected_datetime_columns: list[str] = []
        for column_name in df.columns:
            series = df[column_name]
            null_count = int(series.isna().sum())
            null_pct = float(round((null_count / len(df)) * 100, 2))
            column_info = {
                "name": column_name,
                "dtype": str(series.dtype),
                "unique_count": int(series.nunique(dropna=True)),
                "null_count": null_count,
                "null_pct": null_pct,
            }
            if pd.api.types.is_numeric_dtype(series):
                column_info.update(
                    {
                        "mean": None if series.dropna().empty else float(series.mean()),
                        "std": None if series.dropna().empty else float(series.std(ddof=1)),
                        "min": None if series.dropna().empty else float(series.min()),
                        "max": None if series.dropna().empty else float(series.max()),
                    }
                )

            # Only attempt datetime parsing on likely datetime columns (avoid false positives like StockCode).
            inferred = None
            is_candidate = pd.api.types.is_datetime64_any_dtype(series) or _is_datetime_candidate(series, column_name)
            if is_candidate:
                attempted_datetime_parse.append(column_name)
                inferred = _infer_date_range(series)
            else:
                skipped_datetime_candidates.append(column_name)
            if inferred:
                date_ranges[column_name] = inferred
                detected_datetime_columns.append(column_name)
            columns.append(column_info)

        # Logging: keep profile logs clean and actionable
        if attempted_datetime_parse:
            logger.info("Datetime parse attempted columns (%d): %s", len(attempted_datetime_parse), attempted_datetime_parse)
        if detected_datetime_columns:
            logger.info("Datetime detected columns (%d): %s", len(detected_datetime_columns), detected_datetime_columns)
        if skipped_datetime_candidates:
            logger.info("Datetime skipped columns (%d): %s", len(skipped_datetime_candidates), skipped_datetime_candidates)

        numeric_df = df.select_dtypes(include=[np.number])
        correlations = []
        if numeric_df.shape[1] >= 2:
            corr_matrix = numeric_df.corr(numeric_only=True)
            for left_col, right_col in combinations(corr_matrix.columns, 2):
                corr_value = corr_matrix.loc[left_col, right_col]
                if pd.notna(corr_value) and abs(float(corr_value)) > 0.5:
                    correlations.append(
                        {
                            "left": left_col,
                            "right": right_col,
                            "correlation": round(float(corr_value), 4),
                        }
                    )

        anomalies = [col["name"] for col in columns if col["null_pct"] > 30.0]
        sample_rows = df.head(5).replace({np.nan: None}).to_dict(orient="records")

        best_date_col = _pick_best_date_column(date_ranges)
        recency_percentiles = _compute_recency_percentiles(df, best_date_col) if best_date_col else None

        profile_payload = {
            "table_name": table_name,
            "row_count": int(df.shape[0]),
            "column_count": int(df.shape[1]),
            "columns": columns,
            "date_ranges": date_ranges,
            "recency_percentiles": recency_percentiles,
            "correlations": correlations,
            "anomalies": anomalies,
            "sample_rows": sample_rows,
        }

        dataset.column_profile = profile_payload
        db.add(dataset)
        db.commit()
        db.refresh(dataset)

        return ProfileResponse(dataset_id=dataset.id, table_name=table_name, profile=profile_payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Profil hesaplama hatası: {exc}") from exc
