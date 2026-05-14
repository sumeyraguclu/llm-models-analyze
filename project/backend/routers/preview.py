import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

import database

from database import get_db
from models import Dataset

router = APIRouter()


class PreviewResponse(BaseModel):
    table_name: str
    limit: int
    rows: list[dict]


@router.get("/preview/{table_name}", response_model=PreviewResponse)
def preview_table(
    table_name: str,
    limit: int = Query(default=20, ge=1, le=200),
):
    try:
        query = text(f'SELECT * FROM "{table_name}" LIMIT :limit')
        df = pd.read_sql_query(query, database.engine, params={"limit": limit})
        rows = df.where(pd.notna(df), None).to_dict(orient="records")
        return PreviewResponse(table_name=table_name, limit=limit, rows=rows)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Preview hatası: {exc}") from exc


@router.get("/datasets")
def list_datasets(db: Session = Depends(get_db)):
    try:
        datasets = db.query(Dataset).order_by(Dataset.created_at.desc()).all()
        return [
            {
                "id": d.id,
                "file_name": d.file_name,
                "table_name": d.table_name,
                "column_defs": d.column_defs,
                "has_profile": d.column_profile is not None,
                "created_at": d.created_at,
            }
            for d in datasets
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Dataset listeleme hatası: {exc}") from exc


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    try:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset bulunamadı.")
        return {
            "id": dataset.id,
            "file_name": dataset.file_name,
            "table_name": dataset.table_name,
            "column_defs": dataset.column_defs,
            "column_profile": dataset.column_profile,
            "created_at": dataset.created_at,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Dataset detayı hatası: {exc}") from exc
