"""Profil endpoint: örnek satır + COUNT(*), metadata, küçük tablo davranışı."""

from __future__ import annotations

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient


def _csv_bytes(rows: list[dict]) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def test_profile_small_dataset_no_sampling_flag(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PROFILE_SAMPLE_ROWS", "10000")
    rows = [{"a": i, "b": i * 2} for i in range(8)]
    ing = client.post("/ingest/csv", files={"csv_file": ("s.csv", _csv_bytes(rows), "text/csv")})
    assert ing.status_code == 200
    table_name = ing.json()["table_name"]
    pf = client.post(f"/profile/{table_name}")
    assert pf.status_code == 200
    profile = pf.json()["profile"]
    assert profile["row_count"] == 8
    meta = profile["profiling_metadata"]
    assert meta["profile_sample_used"] is False
    assert meta["profile_rows_loaded"] == 8
    assert meta["row_count_is_full"] is True
    assert meta["warning"] is None
    assert len(profile["sample_rows"]) <= 5


def test_profile_large_row_count_uses_limit_and_count_star(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PROFILE_SAMPLE_ROWS", "4")
    rows = [{"x": i, "y": f"v{i}"} for i in range(20)]
    ing = client.post("/ingest/csv", files={"csv_file": ("b.csv", _csv_bytes(rows), "text/csv")})
    assert ing.status_code == 200
    table_name = ing.json()["table_name"]
    pf = client.post(f"/profile/{table_name}")
    assert pf.status_code == 200
    profile = pf.json()["profile"]
    assert profile["row_count"] == 20
    meta = profile["profiling_metadata"]
    assert meta["profile_sample_used"] is True
    assert meta["profile_rows_loaded"] == 4
    assert meta["row_count_is_full"] is True
    assert meta["warning"] is not None
    assert "örnek" in meta["warning"].lower() or "count(*)" in meta["warning"].lower()


def test_profile_invalid_table_name_rejected(client: TestClient):
    r = client.post("/profile/drop_table_users")
    assert r.status_code == 400


def test_ingest_to_sql_accepts_chunked_write(client: TestClient):
    """to_sql chunksize+method=multi kırılmasın (makul satır sayısı)."""
    rows = [{"i": i, "j": i % 7} for i in range(120)]
    bio = io.BytesIO(_csv_bytes(rows))
    ing = client.post("/ingest/csv", files={"csv_file": ("chunk.csv", bio.getvalue(), "text/csv")})
    assert ing.status_code == 200
    assert ing.json()["row_count"] == 120
