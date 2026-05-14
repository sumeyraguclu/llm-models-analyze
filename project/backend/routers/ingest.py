from io import BytesIO
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

import database

from database import get_db
from models import Dataset

router = APIRouter()
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024


class IngestResponse(BaseModel):
    dataset_id: int
    table_name: str
    row_count: int
    column_count: int


@router.post("/ingest/csv", response_model=IngestResponse)
async def ingest_csv(csv_file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        file_bytes = await csv_file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="CSV dosyası boş.")
        if len(file_bytes) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="CSV dosyası 100MB sınırını aşıyor.")

        df = pd.read_csv(BytesIO(file_bytes))
        if df.empty:
            raise HTTPException(status_code=400, detail="CSV satır içermiyor.")

        table_name = f"data_{uuid4().hex[:8]}"
        df.to_sql(table_name, database.engine, if_exists="replace", index=False)

        column_defs = [{"name": str(col), "dtype": str(dtype)} for col, dtype in df.dtypes.items()]
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
            row_count=int(df.shape[0]),
            column_count=int(df.shape[1]),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CSV ingest hatası: {exc}") from exc
