"""Dataset okuma + agent uçları için ortak önkoşullar."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Dataset


def require_dataset_with_profile(db: Session, dataset_id: int) -> Dataset:
    """Profil oluşturulmuş dataset; aksi halde 404/400."""
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset bulunamadı.")
    if not dataset.column_profile:
        raise HTTPException(status_code=400, detail="Önce profile endpointi çalıştırılmalı.")
    return dataset
