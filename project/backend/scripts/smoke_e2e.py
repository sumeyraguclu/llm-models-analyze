import os
import tempfile

import requests


def main():
    base = os.getenv("BASE_URL", "http://127.0.0.1:8002").rstrip("/")

    csv_content = """Customer ID,InvoiceDate,Invoice,Quantity,Price
1,2024-01-10,INV-1,2,10
1,2024-02-15,INV-2,1,20
2,2023-01-01,INV-3,5,5
3,2022-01-01,INV-4,1,100
,2024-03-01,INV-5,1,10
4,2024-03-10,INV-6,-1,10
5,2024-03-11,INV-7,1,0
"""

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        path = f.name

    with open(path, "rb") as fh:
        r = requests.post(f"{base}/ingest/csv", files={"csv_file": ("test.csv", fh, "text/csv")}, timeout=60)
    print("ingest", r.status_code, r.text)
    r.raise_for_status()
    ingest = r.json()
    dataset_id = ingest["dataset_id"]
    table_name = ingest["table_name"]

    r = requests.post(f"{base}/profile/{table_name}", timeout=60)
    print("profile", r.status_code)
    r.raise_for_status()
    profile = r.json()["profile"]
    date_ranges = profile.get("date_ranges") or {}
    print("date_ranges", list(date_ranges.keys()))

    # Force mock provider regardless of server env
    os.environ["LLM_PROVIDER"] = "mock"
    r = requests.post(
        f"{base}/agent/analysis-plan",
        json={"dataset_id": dataset_id, "user_goal": "I want churn prediction"},
        timeout=60,
    )
    print("analysis-plan", r.status_code, r.text)
    r.raise_for_status()
    plan = r.json()["analysis_plan"]
    plan.setdefault("options", {})
    plan["options"]["churn_strategy"] = "quantile"
    plan["options"]["churn_quantile"] = 0.7

    r = requests.post(
        f"{base}/analyze",
        json={"dataset_id": dataset_id, "template": "churn", "analysis_plan": plan},
        timeout=60,
    )
    print("analyze", r.status_code, r.text)
    r.raise_for_status()
    result = r.json()
    model_id = result["model_id"]

    r = requests.post(f"{base}/agent/explain", json={"model_id": model_id}, timeout=60)
    print("explain", r.status_code, r.text)
    r.raise_for_status()

    print("OK", {"dataset_id": dataset_id, "model_id": model_id})


if __name__ == "__main__":
    main()

