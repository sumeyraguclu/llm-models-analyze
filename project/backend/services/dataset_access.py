"""Dataset okuma + agent uçları için ortak önkoşullar."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Dataset, User
from services.ownership import require_owned_dataset


def require_dataset_with_profile(db: Session, user: User, dataset_id: int) -> Dataset:
    """Sahiplik + profil oluşturulmuş dataset; aksi halde 403/404/400."""
    dataset = require_owned_dataset(db, user, dataset_id)
    if not dataset.column_profile:
        raise HTTPException(status_code=400, detail="Önce profile endpointi çalıştırılmalı.")
    return dataset
