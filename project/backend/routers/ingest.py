from __future__ import annotations

import logging
import os
import tempfile
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

import database

from database import get_db
from models import Dataset

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024
_UPLOAD_BLOCK_BYTES = 1024 * 1024

_DEFAULT_READ_CHUNKSIZE = 10_000
_DEFAULT_SQL_CHUNKSIZE = 5_000
_DEFAULT_PROFILE_SAMPLE_ROWS = 10_000

# PostgreSQL bind parameter limit (~65535); method="multi" uses rows * cols params per statement
_PG_MAX_BIND_PARAMS = 60_000


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int = 1_000_000) -> int:
    raw = int(os.getenv(name, str(default)))
    return max(minimum, min(raw, maximum))


def _ingest_read_chunksize() -> int:
    return _env_int("INGEST_READ_CHUNKSIZE", _DEFAULT_READ_CHUNKSIZE)


def _ingest_sql_chunksize() -> int:
    return _env_int("INGEST_TO_SQL_CHUNKSIZE", _DEFAULT_SQL_CHUNKSIZE, minimum=500)


def _ingest_profile_sample_cap() -> int:
    return _env_int("INGEST_PROFILE_SAMPLE_ROWS", _DEFAULT_PROFILE_SAMPLE_ROWS)


class IngestMetadata(BaseModel):
    chunked: bool = True
    ingest_read_chunksize: int
    to_sql_chunksize: int
    total_rows: int
    read_chunks_processed: int
    profile_sample_rows_kept: int = 0


class IngestResponse(BaseModel):
    dataset_id: int
    table_name: str
    row_count: int
    column_count: int
    ingest_metadata: IngestMetadata | None = Field(
        default=None,
        description="Chunked ingest istatistikleri (büyük/küçük CSV).",
    )


async def _persist_upload_to_tempfile(upload: UploadFile) -> tuple[str, int]:
    """HTTP gövdesini diske yazar (Windows'ta büyük CSV için SpooledTemporaryFile'dan daha güvenilir)."""
    fd, path = tempfile.mkstemp(suffix=".csv")
    total = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                block = await upload.read(_UPLOAD_BLOCK_BYTES)
                if not block:
                    break
                total += len(block)
                if total > MAX_FILE_SIZE_BYTES:
                    raise HTTPException(status_code=413, detail="CSV dosyası 100MB sınırını aşıyor.")
                out.write(block)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise

    if total == 0:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail="CSV dosyası boş.")
    return path, total


def _csv_chunk_reader(path: str, read_chunksize: int):
    """UTF-8 (BOM) önce; başarısızsa latin-1 yedek."""
    common = dict(chunksize=read_chunksize, encoding_errors="replace")
    try:
        return pd.read_csv(path, encoding="utf-8-sig", **common)
    except UnicodeDecodeError:
        logger.warning("CSV utf-8-sig okunamadı, latin-1 deneniyor: %s", path)
        return pd.read_csv(path, encoding="latin-1", **common)


def _safe_sql_chunksize_for_chunk(chunk: pd.DataFrame, sql_chunksize: int) -> int:
    n_cols = max(1, len(chunk.columns))
    max_rows = max(1, _PG_MAX_BIND_PARAMS // n_cols)
    return max(1, min(sql_chunksize, max_rows))


def _write_chunk_to_sql(
    chunk: pd.DataFrame,
    table_name: str,
    *,
    if_exists: str,
    sql_chunksize: int,
) -> None:
    eff = _safe_sql_chunksize_for_chunk(chunk, sql_chunksize)
    base_kw = dict(if_exists=if_exists, index=False, chunksize=eff)
    dialect = database.engine.dialect.name

    if dialect == "postgresql":
        try:
            chunk.to_sql(table_name, database.engine, method="multi", **base_kw)
            return
        except Exception as exc:
            logger.warning(
                "to_sql method=multi başarısız (chunksize=%s, cols=%s), düz insert: %s",
                eff,
                len(chunk.columns),
                exc,
            )

    chunk.to_sql(table_name, database.engine, **base_kw)


def _ingest_csv_chunks_to_table(
    csv_path: str,
    *,
    table_name: str,
    read_chunksize: int,
    sql_chunksize: int,
    profile_sample_cap: int,
) -> tuple[int, int, list[dict], IngestMetadata]:
    total_rows = 0
    column_defs: list[dict] | None = None
    column_count = 0
    read_chunks_processed = 0
    profile_sample_rows_kept = 0
    first_write = True

    reader = _csv_chunk_reader(csv_path, read_chunksize)

    for chunk in reader:
        if len(chunk) == 0:
            continue
        read_chunks_processed += 1
        n = int(len(chunk))
        total_rows += n

        if column_defs is None:
            column_defs = [{"name": str(col), "dtype": str(dtype)} for col, dtype in chunk.dtypes.items()]
            column_count = len(column_defs)

        if profile_sample_rows_kept < profile_sample_cap:
            take = min(profile_sample_cap - profile_sample_rows_kept, n)
            profile_sample_rows_kept += take

        if_exists = "replace" if first_write else "append"
        _write_chunk_to_sql(chunk, table_name, if_exists=if_exists, sql_chunksize=sql_chunksize)
        first_write = False

    if total_rows == 0 or column_defs is None:
        raise HTTPException(status_code=400, detail="CSV satır içermiyor.")

    metadata = IngestMetadata(
        chunked=read_chunks_processed > 1 or total_rows > read_chunksize,
        ingest_read_chunksize=read_chunksize,
        to_sql_chunksize=sql_chunksize,
        total_rows=total_rows,
        read_chunks_processed=read_chunks_processed,
        profile_sample_rows_kept=profile_sample_rows_kept,
    )
    return total_rows, column_count, column_defs, metadata


@router.post("/ingest/csv", response_model=IngestResponse)
async def ingest_csv(csv_file: UploadFile = File(...), db: Session = Depends(get_db)):
    temp_path: str | None = None
    try:
        temp_path, _upload_bytes = await _persist_upload_to_tempfile(csv_file)
        table_name = f"data_{uuid4().hex[:8]}"
        read_chunksize = _ingest_read_chunksize()
        sql_chunksize = _ingest_sql_chunksize()
        profile_sample_cap = _ingest_profile_sample_cap()

        total_rows, column_count, column_defs, ingest_meta = _ingest_csv_chunks_to_table(
            temp_path,
            table_name=table_name,
            read_chunksize=read_chunksize,
            sql_chunksize=sql_chunksize,
            profile_sample_cap=profile_sample_cap,
        )

        dataset = Dataset(
            file_name=csv_file.filename or "uploaded.csv",
            table_name=table_name,
            column_defs=column_defs,
            column_profile=None,
        )
        db.add(dataset)
        db.commit()
        db.refresh(dataset)

        return IngestResponse(
            dataset_id=dataset.id,
            table_name=table_name,
            row_count=total_rows,
            column_count=column_count,
            ingest_metadata=ingest_meta,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("CSV ingest failed")
        err_text = str(exc).lower()
        if "diskfull" in err_text or "project size limit" in err_text or "max_cluster_size" in err_text:
            raise HTTPException(
                status_code=507,
                detail=(
                    "Neon veritabanı depolama kotası dolu (ücretsiz plan genelde 512 MB). "
                    "Neon Console → eski tabloları silin veya `python scripts/cleanup_ingest_tables.py` çalıştırın. "
                    "Büyük CSV tekrar tekrar yüklendiğinde her yükleme yeni bir data_* tablosu oluşturur."
                ),
            ) from exc
        raise HTTPException(status_code=500, detail=f"CSV ingest hatası: {exc}") from exc
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def count_table_rows(table_name: str) -> int:
    """Test / doğrulama: tablodaki satır sayısı."""
    with database.engine.connect() as conn:
        return int(conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one())
