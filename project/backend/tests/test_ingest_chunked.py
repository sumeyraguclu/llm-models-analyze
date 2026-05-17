"""Chunked CSV ingest: satır sayısı, DB yazımı, metadata."""

from __future__ import annotations

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import database
from routers.ingest import count_table_rows


def _csv_bytes(rows: list[dict]) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def test_ingest_small_csv_chunked_metadata(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INGEST_READ_CHUNKSIZE", "10000")
    rows = [{"a": i, "b": i * 2} for i in range(12)]
    ing = client.post("/ingest/csv", files={"csv_file": ("small.csv", _csv_bytes(rows), "text/csv")})
    assert ing.status_code == 200
    body = ing.json()
    assert body["row_count"] == 12
    assert body["column_count"] == 2
    meta = body["ingest_metadata"]
    assert meta is not None
    assert meta["total_rows"] == 12
    assert meta["ingest_read_chunksize"] == 10000
    assert meta["read_chunks_processed"] >= 1
    assert count_table_rows(body["table_name"]) == 12


def test_ingest_multi_chunk_row_count_and_db_rows(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INGEST_READ_CHUNKSIZE", "5000")
    monkeypatch.setenv("INGEST_TO_SQL_CHUNKSIZE", "2000")
    n = 12_500
    rows = [{"id": i, "val": i % 17} for i in range(n)]
    bio = io.BytesIO(_csv_bytes(rows))
    ing = client.post("/ingest/csv", files={"csv_file": ("big.csv", bio.getvalue(), "text/csv")})
    assert ing.status_code == 200
    body = ing.json()
    assert body["row_count"] == n
    meta = body["ingest_metadata"]
    assert meta["chunked"] is True
    assert meta["read_chunks_processed"] == 3  # 5000 + 5000 + 2500
    assert meta["total_rows"] == n
    assert meta["profile_sample_rows_kept"] == 10_000
    assert count_table_rows(body["table_name"]) == n


def test_ingest_profile_sample_cap_env(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INGEST_READ_CHUNKSIZE", "100")
    monkeypatch.setenv("INGEST_PROFILE_SAMPLE_ROWS", "50")
    rows = [{"x": i} for i in range(300)]
    ing = client.post("/ingest/csv", files={"csv_file": ("s.csv", _csv_bytes(rows), "text/csv")})
    assert ing.status_code == 200
    assert ing.json()["ingest_metadata"]["profile_sample_rows_kept"] == 50


def test_count_table_rows_helper_matches_sql(client: TestClient, churn_csv_bytes: bytes):
    ing = client.post("/ingest/csv", files={"csv_file": ("c.csv", churn_csv_bytes, "text/csv")})
    table_name = ing.json()["table_name"]
    with database.engine.connect() as conn:
        direct = int(conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one())
    assert count_table_rows(table_name) == direct
