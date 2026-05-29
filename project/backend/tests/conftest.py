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
os.environ["SECRET_KEY"] = "pytest-secret-key-not-for-production"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"


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


class _AuthenticatedClient:
    """TestClient wrapper — varsayılan Authorization: Bearer."""

    def __init__(self, inner, headers: dict[str, str]):
        self._inner = inner
        self._headers = headers

    def _merge_headers(self, kwargs: dict) -> dict:
        extra = kwargs.pop("headers", None) or {}
        return {**self._headers, **extra}

    def get(self, url: str, **kwargs):
        return self._inner.get(url, headers=self._merge_headers(kwargs), **kwargs)

    def post(self, url: str, **kwargs):
        return self._inner.post(url, headers=self._merge_headers(kwargs), **kwargs)

    def put(self, url: str, **kwargs):
        return self._inner.put(url, headers=self._merge_headers(kwargs), **kwargs)

    def patch(self, url: str, **kwargs):
        return self._inner.patch(url, headers=self._merge_headers(kwargs), **kwargs)

    def delete(self, url: str, **kwargs):
        return self._inner.delete(url, headers=self._merge_headers(kwargs), **kwargs)


@pytest.fixture
def raw_client():
    """Kimlik doğrulamasız ASGI client (auth testleri)."""
    import main  # noqa: WPS433 — env sonrası

    from starlette.testclient import TestClient

    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def auth_headers(raw_client):
    """Kayıt olup access token döner."""
    from uuid import uuid4

    email = f"user_{uuid4().hex}@test.local"
    r = raw_client.post(
        "/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Test User"},
    )
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(raw_client, auth_headers):
    """Korumalı endpoint testleri için otomatik Bearer header."""
    return _AuthenticatedClient(raw_client, auth_headers)


@pytest.fixture
def current_user_id(raw_client, auth_headers) -> int:
    r = raw_client.get("/auth/me", headers=auth_headers)
    assert r.status_code == 200
    return int(r.json()["id"])


def make_db_user(db, *, email: str | None = None):
    """Doğrudan SessionLocal kullanan unit testler için User oluşturur."""
    from uuid import uuid4

    from models import User
    from services.security import hash_password

    user = User(
        email=email or f"db_{uuid4().hex}@test.local",
        password_hash=hash_password("testpass123"),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def register_second_user(raw_client) -> dict[str, str]:
    from uuid import uuid4

    email = f"other_{uuid4().hex}@test.local"
    r = raw_client.post(
        "/auth/register",
        json={"email": email, "password": "otherpass123"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


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
