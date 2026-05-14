"""
Test ortamı: LLM_PROVIDER=mock, SQLite dosya DB, tablolar test başına sıfırlanır.
Gerçek LLM HTTP'si llm_client.requests.post patch ile engellenir.
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# --- DB URL: import database öncesi set edilmeli ---
_tmpdir = tempfile.mkdtemp(prefix="automl_pytest_")
_DB_PATH = Path(_tmpdir) / "test.sqlite"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_DB_PATH.as_posix()}"


@pytest.fixture(autouse=True)
def _reset_sqlite_schema():
    """Her testte temiz şema (API ve DB kullanan testler izole)."""
    import models  # noqa: F401 — metadata
    import database
    from database import Base

    Base.metadata.drop_all(bind=database.engine)
    Base.metadata.create_all(bind=database.engine)
    yield


@pytest.fixture(autouse=True)
def _forbid_llm_client_http(monkeypatch: pytest.MonkeyPatch):
    """Ollama vb. yoluyla dış HTTP (tests sırasında LLM_PROVIDER mock olsa bile)."""
    import services.llm_client as lc

    def _deny(*_a, **_kw):
        raise AssertionError(
            "services.llm_client.requests.post çağrıldı; testlerde LLM_PROVIDER=mock ve network yasak."
        )

    monkeypatch.setattr(lc.requests, "post", _deny)
    monkeypatch.setattr(lc.requests, "get", _deny)


@pytest.fixture
def client():
    """FastAPI ASGI client (BackgroundTasks aynı thread'de response sonrası çalışır)."""
    import main  # noqa: WPS433 — env sonrası

    from starlette.testclient import TestClient

    with TestClient(main.app) as c:
        yield c


def ecommerce_tx_dataframe(
    *,
    n_customers: int = 120,
    rows_per_customer: int = 8,
    duplicate_rate: float = 0.0,
) -> pd.DataFrame:
    """Churn pipeline için yeterli müşteri + işlem satırı (deterministik)."""
    rows: list[dict] = []
    base = pd.Timestamp("2024-01-01", tz="UTC")
    rng = range(10_000, 10_000 + n_customers)
    inv = 0
    for cid in rng:
        for i in range(rows_per_customer):
            inv += 1
            days = i * 12 + (cid % 9)
            dt = (base + pd.Timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            rows.append(
                {
                    "Customer ID": cid,
                    "InvoiceDate": dt,
                    "Invoice": f"INV-{inv}",
                    "Quantity": 1,
                    "Price": float(5 + (i % 4)),
                }
            )
    df = pd.DataFrame(rows)
    if duplicate_rate > 0 and len(df) > 2:
        n_dup = max(1, int(len(df) * duplicate_rate))
        dup_idx = df.index[:n_dup]
        df = pd.concat([df, df.loc[dup_idx].copy()], ignore_index=True)
    return df


@pytest.fixture
def churn_csv_bytes() -> bytes:
    buf = io.StringIO()
    ecommerce_tx_dataframe().to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")
