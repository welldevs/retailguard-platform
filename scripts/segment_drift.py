"""
segment_drift.py
================
Standalone, reproducible post-processor that regenerates the v2 customer
snapshot (``source/customers_drift.csv``) from the *actual loaded* v1 baseline
(``source/customers.csv``) WITHOUT re-running the simulation.

Re-simulating would change the customer count and the per-customer attributes
(the engine reseeds many sub-generators), which would make v1→v2 diffs noisy.
Reading the on-disk v1 CSV and applying the same pure drift function keeps the
two snapshots identical except for the ~3% of rows that intentionally moved
segment — exactly what the SCD2 / segment-drift demo needs.

The drift logic lives in ``erp.generators.customers.apply_segment_drift`` and is
imported here — single source of truth, shared with the simulator export path.

Usage:
    python scripts/segment_drift.py                       # seed=42, fraction=0.03
    python scripts/segment_drift.py --seed 7 --fraction 0.05
    python scripts/segment_drift.py --input source/customers.csv \\
        --output source/customers_drift.csv

The output preserves the EXACT header and column order of the input via
csv.DictReader / csv.DictWriter.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))  # so `import erp.*` resolves

from erp.generators.customers import apply_segment_drift  # noqa: E402


def _read_customers(path: Path) -> tuple[list[dict], list[str]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            sys.exit(f"Empty / headerless CSV: {path}")
        fieldnames = list(reader.fieldnames)
        rows = [dict(row) for row in reader]
    return rows, fieldnames


def _write_customers(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply deterministic segment drift to source/customers.csv → v2"
    )
    parser.add_argument("--seed", type=int, default=42,
                        help="Seed for deterministic mover selection (default 42)")
    parser.add_argument("--fraction", type=float, default=0.03,
                        help="Target fraction of eligible customers to move (default 0.03)")
    parser.add_argument("--input", type=Path,
                        default=REPO_ROOT / "source" / "customers.csv",
                        help="v1 baseline CSV (default source/customers.csv)")
    parser.add_argument("--output", type=Path,
                        default=REPO_ROOT / "source" / "customers_drift.csv",
                        help="v2 output CSV (default source/customers_drift.csv)")
    args = parser.parse_args()

    if not args.input.exists():
        sys.exit(f"Input not found: {args.input}")

    rows, fieldnames = _read_customers(args.input)
    drifted, num_moved = apply_segment_drift(rows, seed=args.seed, fraction=args.fraction)

    # avg_ticket comes back as a float after a move; render it the same way the
    # rest of the column reads (string) so the CSV stays homogeneous.
    for row in drifted:
        row["avg_ticket"] = str(row["avg_ticket"])

    _write_customers(args.output, drifted, fieldnames)

    print(f"Read {len(rows):,} customers from {args.input}")
    print(f"Moved {num_moved:,} customers (seed={args.seed}, fraction={args.fraction})")
    print(f"Wrote v2 → {args.output}")


if __name__ == "__main__":
    main()
