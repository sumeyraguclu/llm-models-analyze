"""
Online Retail II CSV — müşteri bazlı demo örnekleme.

Tüm transaction history korunur (satır bazlı random sample değil).
Churn / customer feature engineering için transaction grain aynı kalır.

Run (repo kökünden veya backend'den):
  python project/backend/scripts/sample_online_retail_by_customer.py
  python scripts/sample_online_retail_by_customer.py   # cwd=backend

Output varsayılan: project/datasets/demo/online_retail_II_demo.csv
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "online_retail_II.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "demo" / "online_retail_II_demo.csv"
DEFAULT_CUSTOMER_COL = "Customer ID"
CHUNKSIZE = 100_000
MIB = 1024 * 1024


def _pass_customer_row_counts(
    input_path: Path,
    customer_col: str,
    chunksize: int,
) -> tuple[Counter, int]:
    counts: Counter = Counter()
    total_rows = 0
    for chunk in pd.read_csv(input_path, chunksize=chunksize, low_memory=False):
        total_rows += len(chunk)
        if customer_col not in chunk.columns:
            raise ValueError(
                f"Column {customer_col!r} not found. Columns: {list(chunk.columns)}"
            )
        series = chunk[customer_col]
        valid = series.notna()
        for cid, n in series[valid].value_counts().items():
            counts[cid] += int(n)
    return counts, total_rows


def _select_customers(
    counts: Counter,
    source_bytes: int,
    total_rows: int,
    min_bytes: int,
    max_bytes: int,
    random_state: int,
) -> tuple[list, int, float]:
    if not counts:
        raise ValueError("No valid customer IDs found for sampling.")

    bytes_per_row = source_bytes / max(total_rows, 1)
    customer_ids = np.array(list(counts.keys()), dtype=object)
    row_counts = np.array([counts[c] for c in customer_ids], dtype=np.int64)

    rng = np.random.RandomState(random_state)
    order = rng.permutation(len(customer_ids))
    shuffled_ids = customer_ids[order]
    shuffled_rows = row_counts[order]

    cumulative = np.cumsum(shuffled_rows)
    estimated_bytes = cumulative * bytes_per_row

    in_range = np.where((estimated_bytes >= min_bytes) & (estimated_bytes <= max_bytes))[0]
    if len(in_range):
        # Hedef bandın ortasına en yakın kesim
        target = (min_bytes + max_bytes) / 2
        idx = int(in_range[np.argmin(np.abs(estimated_bytes[in_range] - target))])
    else:
        # Bandın altında kalıyorsa mümkün olduğunca max'a yaklaş; üstündeyse min'e yaklaş
        below = np.where(estimated_bytes < min_bytes)[0]
        above = np.where(estimated_bytes > max_bytes)[0]
        if len(below) and (not len(above) or estimated_bytes[below[-1]] >= min_bytes * 0.5):
            idx = int(below[-1])
        elif len(above):
            idx = int(above[0])
        else:
            idx = len(shuffled_ids) - 1

    selected = shuffled_ids[: idx + 1].tolist()
    est_rows = int(cumulative[idx])
    est_size = est_rows * bytes_per_row
    return selected, est_rows, est_size


def _write_filtered_csv(
    input_path: Path,
    output_path: Path,
    customer_col: str,
    selected: set,
    chunksize: int,
) -> tuple[int, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written_rows = 0
    first_chunk = True

    for chunk in pd.read_csv(input_path, chunksize=chunksize, low_memory=False):
        mask = chunk[customer_col].isin(selected)
        out = chunk.loc[mask]
        if out.empty:
            continue
        out.to_csv(
            output_path,
            mode="w" if first_chunk else "a",
            header=first_chunk,
            index=False,
        )
        first_chunk = False
        written_rows += len(out)

    if first_chunk:
        raise RuntimeError("No rows written — check customer column and selection.")

    return written_rows, len(selected)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Customer-based sample of Online Retail II CSV (full history per customer)."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Source CSV (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output CSV (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--customer-column",
        default=DEFAULT_CUSTOMER_COL,
        help=f"Customer ID column name (default: {DEFAULT_CUSTOMER_COL!r})",
    )
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--min-mb",
        type=float,
        default=5.0,
        help="Target minimum output size in MB (default: 5)",
    )
    parser.add_argument(
        "--max-mb",
        type=float,
        default=20.0,
        help="Target maximum output size in MB (default: 20)",
    )
    parser.add_argument("--chunksize", type=int, default=CHUNKSIZE)
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_path = args.output.resolve()
    if not input_path.is_file():
        raise SystemExit(f"Input not found: {input_path}")

    min_bytes = int(args.min_mb * MIB)
    max_bytes = int(args.max_mb * MIB)
    source_bytes = input_path.stat().st_size

    print(f"Pass 1: counting rows per customer ({input_path.name})...")
    counts, total_rows = _pass_customer_row_counts(
        input_path, args.customer_column, args.chunksize
    )
    print(f"  Total rows: {total_rows:,}  |  Customers (non-null): {len(counts):,}")

    selected_list, est_rows, est_size = _select_customers(
        counts,
        source_bytes,
        total_rows,
        min_bytes,
        max_bytes,
        args.random_state,
    )
    selected_set = set(selected_list)
    print(
        f"Selected {len(selected_set):,} customers "
        f"(~{est_rows:,} rows, ~{est_size / MIB:.1f} MB estimated)"
    )

    if output_path.exists():
        output_path.unlink()

    print(f"Pass 2: writing {output_path}...")
    written_rows, n_customers = _write_filtered_csv(
        input_path,
        output_path,
        args.customer_column,
        selected_set,
        args.chunksize,
    )

    out_bytes = output_path.stat().st_size
    print(f"Done: {written_rows:,} rows, {n_customers:,} customers")
    print(f"Output: {output_path} ({out_bytes / MIB:.2f} MB)")


if __name__ == "__main__":
    main()
