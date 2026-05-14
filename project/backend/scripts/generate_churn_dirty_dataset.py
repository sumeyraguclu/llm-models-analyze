"""
Churn test CSV: transaction grain, Turkish-ish column names, intentional noise.
Run: python scripts/generate_churn_dirty_dataset.py
Output: data/churn_test_dirty.csv
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Reproducible
random.seed(42)

N_CUSTOMERS = 300
N_TRANSACTIONS = 1500
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "churn_test_dirty.csv"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    start = datetime(2023, 6, 1)
    end = datetime(2025, 4, 15)
    span = (end - start).days

    customer_ids = [f"C{900000 + i}" for i in range(N_CUSTOMERS)]

    rows: list[dict] = []
    inv = 10000

    # Uneven customers: power-law-ish weights so recency/frequency vary
    weights = [random.random() ** 2 + 0.15 for _ in customer_ids]
    s = sum(weights)
    weights = [w / s for w in weights]

    # Guarantee each customer appears at least once (300 rows), then fill to N_TRANSACTIONS
    for cust in customer_ids:
        day_off = int(random.random() * span)
        order_dt = start + timedelta(days=day_off, hours=random.randint(8, 21), minutes=random.randint(0, 59))
        inv += 1
        qty = random.choices([1, 1, 2, 2, 3, 5], weights=[3, 4, 3, 2, 2, 1])[0]
        base_price = round(random.uniform(4.99, 249.99), 2)
        rows.append(
            {
                "MusteriKodu": cust,
                "FaturaTarihi": order_dt.strftime("%Y-%m-%d %H:%M"),
                "FaturaNo": f"FT-{inv}",
                "KalemAdedi": qty,
                "BirimFiyatTL": base_price,
                "UrunGrubu": random.choice(["GIDA", "TEKSTIL", "ELEKTRONIK", "KOZMETIK", ""]),
            }
        )

    remaining = N_TRANSACTIONS - len(rows)
    for _ in range(remaining):
        cust = random.choices(customer_ids, weights=weights, k=1)[0]
        day_off = int(random.random() * span)
        order_dt = start + timedelta(days=day_off, hours=random.randint(8, 21), minutes=random.randint(0, 59))
        inv += 1
        qty = random.choices([1, 1, 2, 2, 3, 5], weights=[3, 4, 3, 2, 2, 1])[0]
        base_price = round(random.uniform(4.99, 249.99), 2)
        rows.append(
            {
                "MusteriKodu": cust,
                "FaturaTarihi": order_dt.strftime("%Y-%m-%d %H:%M"),
                "FaturaNo": f"FT-{inv}",
                "KalemAdedi": qty,
                "BirimFiyatTL": base_price,
                "UrunGrubu": random.choice(["GIDA", "TEKSTIL", "ELEKTRONIK", "KOZMETIK", ""]),
            }
        )

    df = pd.DataFrame(rows)
    df["FaturaTarihi"] = df["FaturaTarihi"].astype(object)
    # Allow mixed-type noise in numeric columns
    df["KalemAdedi"] = df["KalemAdedi"].astype(object)
    df["BirimFiyatTL"] = df["BirimFiyatTL"].astype(object)

    # --- Inject dirty rows: kümeler çakışmasın ---
    dup_mask = df.duplicated(subset=["MusteriKodu"], keep=False)
    dup_idxs = set(df.index[dup_mask].tolist())

    pool = random.sample(range(len(df)), k=700)  # geniş havuz; çakışmayı önlemek için

    na_idxs: list[int] = []
    for i in pool:
        if i in dup_idxs and len(na_idxs) < 35:
            na_idxs.append(i)
    if len(na_idxs) < 35:
        rest_na = [i for i in dup_idxs if i not in na_idxs]
        random.shuffle(rest_na)
        na_idxs.extend(rest_na[: 35 - len(na_idxs)])

    used = set(na_idxs)
    pick = [i for i in pool if i not in used]

    date_idxs = pick[0:35]
    qty_idxs = pick[35:75]
    price_idxs = pick[75:110]
    ws_qty_idxs = pick[110:130]
    outlier_price_idxs = pick[130:145]

    for i in na_idxs:
        df.loc[i, "MusteriKodu"] = pd.NA

    for i in date_idxs:
        df.loc[i, "FaturaTarihi"] = random.choice(["", "N/A", "31/13/2025", "2025-02-30", "tarih_yok"])

    for i in qty_idxs:
        df.loc[i, "KalemAdedi"] = random.choice([-1, -3, -10])

    for i in price_idxs:
        df.loc[i, "BirimFiyatTL"] = random.choice([0, -0.01, -5.0])

    for i in ws_qty_idxs:
        raw = df.loc[i, "KalemAdedi"]
        try:
            base_n = int(raw) if pd.notna(raw) else 1
        except (TypeError, ValueError):
            base_n = 1
        df.loc[i, "KalemAdedi"] = f"  {base_n}  "

    for i in outlier_price_idxs:
        df.loc[i, "BirimFiyatTL"] = 9999999.0

    # Shuffle
    df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)

    df.to_csv(OUTPUT, index=False, encoding="utf-8")
    m = pd.Series(df["MusteriKodu"])
    valid_mask = m.notna() & m.astype(str).str.strip().ne("") & m.astype(str).str.strip().ne("<NA>")
    good_customers = m[valid_mask].nunique()
    print(f"Wrote {OUTPUT}")
    print(f"Rows: {len(df)}, distinct MusteriKodu (valid): {good_customers}")


if __name__ == "__main__":
    main()
