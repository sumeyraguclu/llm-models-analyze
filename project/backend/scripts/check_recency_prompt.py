import os
import sys
import tempfile

import requests
from dotenv import load_dotenv


def main():
    # Ensure backend root is importable when running from scripts/
    backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    # Use backend env for DB connection in prompt check
    load_dotenv()

    base = os.getenv("BASE_URL", "http://127.0.0.1:8004").rstrip("/")

    csv_content = """Customer ID,InvoiceDate,Invoice,Quantity,Price
1,2024-01-10,INV-1,2,10
1,2024-02-15,INV-2,1,20
2,2023-01-01,INV-3,5,5
3,2022-01-01,INV-4,1,100
"""

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        path = f.name

    with open(path, "rb") as fh:
        r = requests.post(f"{base}/ingest/csv", files={"csv_file": ("t.csv", fh, "text/csv")}, timeout=60)
    r.raise_for_status()
    ingest = r.json()
    dataset_id = ingest["dataset_id"]
    table_name = ingest["table_name"]
    print("ingest_ok", {"dataset_id": dataset_id, "table_name": table_name})

    r = requests.post(f"{base}/profile/{table_name}", timeout=60)
    r.raise_for_status()
    profile = r.json()["profile"]

    recency_percentiles = profile.get("recency_percentiles")
    print("recency_percentiles", recency_percentiles)
    if not recency_percentiles or not recency_percentiles.get("percentiles"):
        raise SystemExit("recency_percentiles boş geldi")

    # Prompt check (reads dataset record from DB)
    from agent.prompt_builder import build_system_prompt
    from database import SessionLocal
    from models import Dataset

    db = SessionLocal()
    try:
        ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not ds:
            raise SystemExit("Dataset DB'de bulunamadı")
        prompt = build_system_prompt(ds)
    finally:
        db.close()

    lines = [ln.strip() for ln in prompt.splitlines() if ln.strip()]
    wanted = [ln for ln in lines if ln.startswith("DATA_RECENCY:") or ln.startswith("RECENCY_DISTRIBUTION")]
    print("prompt_lines", wanted)
    if not any(ln.startswith("DATA_RECENCY:") for ln in wanted):
        raise SystemExit("Prompt içinde DATA_RECENCY bulunamadı")
    if not any(ln.startswith("RECENCY_DISTRIBUTION") for ln in wanted):
        raise SystemExit("Prompt içinde RECENCY_DISTRIBUTION bulunamadı")

    print("OK")


if __name__ == "__main__":
    main()

