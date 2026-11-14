
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = ROOT / "data" / "historical" / "processed"
OUTPUT_DIR = DATA_DIR / "audit"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = "2012-01-20"
END_DATE = "2026-07-31"

DATASETS = {
    "MODIS": DATA_DIR / "modis_sp_historical.csv",
    "VIIRS_SNPP": DATA_DIR / "viirs_snpp_sp_historical.csv",
}


def audit_dataset(sensor, path):
    print(f"\n========== {sensor} ==========")

    daily_counts = {}
    total_rows = 0
    invalid_dates = 0
    exact_duplicates = 0
    columns = None

    for chunk in pd.read_csv(path, chunksize=100_000):
        total_rows += len(chunk)

        if columns is None:
            columns = list(chunk.columns)

        dates = pd.to_datetime(
            chunk["acq_date"],
            errors="coerce"
        )

        invalid_dates += int(dates.isna().sum())

        valid_dates = dates.dropna().dt.strftime("%Y-%m-%d")
        counts = valid_dates.value_counts()

        for day, count in counts.items():
            daily_counts[day] = (
                daily_counts.get(day, 0) + int(count)
            )

        exact_duplicates += int(
            chunk.duplicated().sum()
        )

    calendar = pd.date_range(
        START_DATE, END_DATE, freq="D"
    )

    daily = pd.DataFrame({
        "date": calendar.strftime("%Y-%m-%d")
    })

    daily["detection_count"] = (
        daily["date"].map(daily_counts).fillna(0).astype(int)
    )

    daily["has_observations"] = (
        daily["detection_count"] > 0
    )

    missing_dates = daily.loc[
        ~daily["has_observations"], "date"
    ].tolist()

    daily["month"] = pd.to_datetime(daily["date"]).dt.to_period("M").astype(str)
    daily["year"] = pd.to_datetime(daily["date"]).dt.year

    monthly = (
        daily.groupby("month", as_index=False)
        ["detection_count"].sum()
    )

    yearly = (
        daily.groupby("year", as_index=False)
        ["detection_count"].sum()
    )

    daily.to_csv(
        OUTPUT_DIR / f"{sensor.lower()}_daily_coverage.csv",
        index=False
    )

    monthly.to_csv(
        OUTPUT_DIR / f"{sensor.lower()}_monthly_counts.csv",
        index=False
    )

    yearly.to_csv(
        OUTPUT_DIR / f"{sensor.lower()}_yearly_counts.csv",
        index=False
    )

    pd.DataFrame({
        "date": missing_dates
    }).to_csv(
        OUTPUT_DIR / f"{sensor.lower()}_zero_detection_dates.csv",
        index=False
    )

    observed_dates = sorted(daily_counts)

    print(f"Total rows: {total_rows:,}")
    print(f"Columns: {columns}")
    print(f"First observed date: {observed_dates[0] if observed_dates else 'None'}")
    print(f"Last observed date: {observed_dates[-1] if observed_dates else 'None'}")
    print(f"Dates with detections: {len(observed_dates):,}")
    print(f"Zero-detection dates: {len(missing_dates):,}")
    print(f"Invalid acquisition dates: {invalid_dates:,}")
    print(f"Exact duplicate rows within chunks: {exact_duplicates:,}")
    print(f"Monthly summaries: {len(monthly)}")
    print(f"Yearly summaries: {len(yearly)}")

    return daily


def main():
    print("HISTORICAL DATA COVERAGE AUDIT")

    results = {}

    for sensor, path in DATASETS.items():
        if not path.exists():
            raise FileNotFoundError(path)

        results[sensor] = audit_dataset(sensor, path)

    comparison = results["MODIS"].merge(
        results["VIIRS_SNPP"],
        on="date",
        how="outer",
        suffixes=("_modis", "_viirs")
    )

    comparison["both_observed"] = (
        comparison["has_observations_modis"]
        & comparison["has_observations_viirs"]
    )

    comparison.to_csv(
        OUTPUT_DIR / "sensor_daily_comparison.csv",
        index=False
    )

    print("\n========== SENSOR COVERAGE COMPARISON ==========")
    print(
        "Days with both sensors:",
        int(comparison["both_observed"].sum())
    )
    print(
        "Days with MODIS only:",
        int((
            comparison["has_observations_modis"]
            & ~comparison["has_observations_viirs"]
        ).sum())
    )
    print(
        "Days with VIIRS only:",
        int((
            ~comparison["has_observations_modis"]
            & comparison["has_observations_viirs"]
        ).sum())
    )

    print("\nAudit files saved to:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
