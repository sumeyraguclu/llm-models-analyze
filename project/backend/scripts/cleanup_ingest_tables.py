"""
Neon / Postgres'te ingest sırasında oluşan data_* tablolarını temizler.

Her CSV yükleme yeni bir tablo oluşturur (data_<uuid>). Silinmeyen tablolar disk kotasını doldurur.

Kullanım (backend dizininden, .env yüklü):
  python scripts/cleanup_ingest_tables.py --dry-run
  python scripts/cleanup_ingest_tables.py --orphans-only
  python scripts/cleanup_ingest_tables.py --all

--orphans-only: datasets tablosunda kaydı olmayan data_* tablolarını siler (önerilen).
--all: Tüm data_* tablolarını siler (datasets kayıtları kalır; tablolar gider).
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import inspect, text

# backend/ kökünden çalıştırıldığında
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

load_dotenv(os.path.join(_ROOT, ".env"))

import database  # noqa: E402
from models import Dataset  # noqa: E402


def _list_data_tables() -> list[str]:
    insp = inspect(database.engine)
    return sorted(t for t in insp.get_table_names() if t.startswith("data_"))


def _registered_table_names() -> set[str]:
    with database.SessionLocal() as db:
        rows = db.query(Dataset.table_name).all()
    return {r[0] for r in rows}


def _table_size_estimate(conn, table: str) -> str:
    try:
        n = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
        return f"{int(n):,} satır"
    except Exception:
        return "?"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest data_* tablolarını temizle")
    parser.add_argument("--dry-run", action="store_true", help="Silmeden listele")
    parser.add_argument("--orphans-only", action="store_true", help="Kayıtsız tabloları sil")
    parser.add_argument("--all", action="store_true", help="Tüm data_* tablolarını sil")
    args = parser.parse_args()

    if not args.orphans_only and not args.all:
        parser.error("--orphans-only veya --all seçin (önce --dry-run önerilir)")

    data_tables = _list_data_tables()
    registered = _registered_table_names()

    if args.all:
        targets = data_tables
    else:
        targets = [t for t in data_tables if t not in registered]

    print(f"Toplam data_* tablosu: {len(data_tables)}, silinecek: {len(targets)}")
    if not targets:
        print("Temizlenecek tablo yok.")
        return

    with database.engine.connect() as conn:
        for t in targets:
            tag = "orphan" if t not in registered else "registered"
            size = _table_size_estimate(conn, t)
            print(f"  [{tag}] {t} ({size})")

    if args.dry_run:
        print("Dry-run: tablo silinmedi.")
        return

    with database.engine.begin() as conn:
        for t in targets:
            conn.execute(text(f'DROP TABLE IF EXISTS "{t}" CASCADE'))
            print(f"Dropped: {t}")

    print("Bitti. Neon Console > Storage kullanimini kontrol edin.")


if __name__ == "__main__":
    main()
