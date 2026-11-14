
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]

RAW_DIR = ROOT / "data" / "historical" / "raw"
PROCESSED_DIR = ROOT / "data" / "historical" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

DATASETS = {
    "modis_sp": {
        "pattern": re.compile(r"^modis_sp_(\d{8})\.csv$"),
        "output": "modis_sp_historical.csv",
    },
    "viirs_snpp_sp": {
        "pattern": re.compile(r"^viirs_snpp_sp_(\d{8})\.csv$"),
        "output": "viirs_snpp_sp_historical.csv",
    },
}

EXPECTED_START = pd.Timestamp("2012-01-20")
EXPECTED_END = pd.Timestamp("2026-07-31")


def consolidate(sensor, config):
    files = []

    for path in RAW_DIR.glob("*.csv"):
        match = config["pattern"].match(path.name)
        if match:
            files.append((match.group(1), path))

    files.sort(key=lambda item: item[0])

    print(f"\n========== {sensor.upper()} ==========")
    print(f"Chunk files found: {len(files)}")

    if not files:
        raise RuntimeError(f"No chunk files found for {sensor}")

    output_path = PROCESSED_DIR / config["output"]
    manifest = []

    total_rows = 0
    empty_files = 0
    failed_files = 0
    min_date = None
    max_date = None
    expected_columns = None

    if output_path.exists():
        output_path.unlink()

    for index, (chunk_date, path) in enumerate(files, start=1):
        try:
            df = pd.read_csv(path)

            if expected_columns is None:
                expected_columns = list(df.columns)
            elif list(df.columns) != expected_columns:
                raise ValueError("Column schema differs from earlier chunks")

            row_count = len(df)

            if row_count == 0:
                empty_files += 1

            if row_count and "acq_date" in df.columns:
                dates = pd.to_datetime(
                    df["acq_date"],
                    errors="coerce"
                ).dropna()

                if not dates.empty:
                    chunk_min = dates.min()
                    chunk_max = dates.max()

                    min_date = (
                        chunk_min if min_date is None
                        else min(min_date, chunk_min)
                    )
                    max_date = (
                        chunk_max if max_date is None
                        else max(max_date, chunk_max)
                    )

            df.to_csv(
                output_path,
                mode="w" if index == 1 else "a",
                header=(index == 1),
                index=False,
            )

            total_rows += row_count

            manifest.append({
                "file": path.name,
                "chunk_start": chunk_date,
                "rows": row_count,
                "status": "processed",
            })

        except Exception as exc:
            failed_files += 1
            manifest.append({
                "file": path.name,
                "chunk_start": chunk_date,
                "rows": None,
                "status": f"failed: {type(exc).__name__}: {exc}",
            })

        if index % 100 == 0 or index == len(files):
            print(
                f"{index}/{len(files)} chunks | "
                f"Rows: {total_rows:,} | "
                f"Failed: {failed_files}"
            )

    manifest_path = PROCESSED_DIR / f"{sensor}_manifest.csv"
    pd.DataFrame(manifest).to_csv(manifest_path, index=False)

    print("\nConsolidation summary")
    print(f"Files found: {len(files)}")
    print(f"Total detections: {total_rows:,}")
    print(f"Empty chunks: {empty_files}")
    print(f"Failed chunks: {failed_files}")
    print(f"Observed date range: {min_date} to {max_date}")
    print(f"Output: {output_path}")
    print(f"Manifest: {manifest_path}")

    return {
        "sensor": sensor,
        "files": len(files),
        "rows": total_rows,
        "empty": empty_files,
        "failed": failed_files,
        "min_date": min_date,
        "max_date": max_date,
    }


def main():
    print("HISTORICAL DATA CONSOLIDATION")
    print(f"Expected period: {EXPECTED_START.date()} to {EXPECTED_END.date()}")

    results = []

    for sensor, config in DATASETS.items():
        results.append(consolidate(sensor, config))

    print("\n========== FINAL SUMMARY ==========")

    for result in results:
        print(
            f"{result['sensor']}: "
            f"{result['files']} chunks, "
            f"{result['rows']:,} detections, "
            f"{result['failed']} failed"
        )

    if any(result["failed"] for result in results):
        print("\nWARNING: Some chunks failed consolidation.")
    else:
        print("\nBoth historical datasets consolidated successfully.")


if __name__ == "__main__":
    main()

