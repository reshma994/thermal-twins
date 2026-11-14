
from pathlib import Path

import h3
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]

INPUT = (
    ROOT / "data/historical/processed/"
    / "historical_observations_normalized.csv"
)

OUTPUT_DIR = ROOT / "data/historical/processed/analytics"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE = 100_000
H3_RESOLUTION = 7

GROUP_COLUMNS = [
    "h3_cell",
    "acquisition_date",
    "sensor",
]


def aggregate_chunk(df):
    df = df.dropna(
        subset=["latitude", "longitude", "acquisition_date"]
    ).copy()

    if df.empty:
        return pd.DataFrame()

    df["h3_cell"] = [
        h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
        for lat, lon in zip(df["latitude"], df["longitude"])
    ]

    df["frp"] = pd.to_numeric(df["frp"], errors="coerce")
    df["brightness_primary"] = pd.to_numeric(
        df["brightness_primary"], errors="coerce"
    )

    grouped = (
        df.groupby(GROUP_COLUMNS, observed=True)
        .agg(
            detection_count=("sensor", "size"),
            frp_sum=("frp", "sum"),
            frp_valid_count=("frp", "count"),
            brightness_sum=("brightness_primary", "sum"),
            brightness_valid_count=("brightness_primary", "count"),
            latitude_sum=("latitude", "sum"),
            longitude_sum=("longitude", "sum"),
        )
        .reset_index()
    )

    return grouped


def main():
    print("HISTORICAL H3 GRID AGGREGATION")
    print(f"H3 resolution: {H3_RESOLUTION}")
    print(f"Chunk size: {CHUNK_SIZE:,}")

    partials = []
    processed = 0

    for chunk in pd.read_csv(INPUT, chunksize=CHUNK_SIZE):
        partial = aggregate_chunk(chunk)

        if not partial.empty:
            partials.append(partial)

        processed += len(chunk)

        print(
            f"Processed {processed:,} observations",
            end="\r",
        )

    print(f"\nTotal observations processed: {processed:,}")

    print("Combining partial aggregates...")

    combined = pd.concat(partials, ignore_index=True)

    daily = (
        combined.groupby(GROUP_COLUMNS, observed=True)
        .agg(
            detection_count=("detection_count", "sum"),
            frp_sum=("frp_sum", "sum"),
            frp_valid_count=("frp_valid_count", "sum"),
            brightness_sum=("brightness_sum", "sum"),
            brightness_valid_count=("brightness_valid_count", "sum"),
            latitude_sum=("latitude_sum", "sum"),
            longitude_sum=("longitude_sum", "sum"),
        )
        .reset_index()
    )

    daily["frp_mean"] = (
        daily["frp_sum"]
        / daily["frp_valid_count"].replace(0, pd.NA)
    )

    daily["brightness_mean"] = (
        daily["brightness_sum"]
        / daily["brightness_valid_count"].replace(0, pd.NA)
    )

    daily["latitude_mean"] = (
        daily["latitude_sum"] / daily["detection_count"]
    )

    daily["longitude_mean"] = (
        daily["longitude_sum"] / daily["detection_count"]
    )

    daily["h3_resolution"] = H3_RESOLUTION

    daily = daily.drop(columns=[
        "frp_valid_count",
        "brightness_valid_count",
        "latitude_sum",
        "longitude_sum",
        "brightness_sum",
    ])

    daily_path = OUTPUT_DIR / "daily_cell_activity.csv"
    daily.to_csv(daily_path, index=False)

    # Sensor comparison for each cell and date.
    comparison = daily.pivot_table(
        index=["h3_cell", "acquisition_date"],
        columns="sensor",
        values="detection_count",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()

    for sensor in ["MODIS", "VIIRS"]:
        if sensor not in comparison.columns:
            comparison[sensor] = 0

    comparison = comparison.rename(columns={
        "MODIS": "modis_detections",
        "VIIRS": "viirs_detections",
    })

    comparison["both_sensors_observed"] = (
        (comparison["modis_detections"] > 0)
        & (comparison["viirs_detections"] > 0)
    )

    comparison_path = OUTPUT_DIR / "sensor_cell_comparison.csv"
    comparison.to_csv(comparison_path, index=False)

    # Monthly sensor-level activity.
    daily["month"] = pd.to_datetime(
        daily["acquisition_date"]
    ).dt.to_period("M").astype(str)

    monthly = (
        daily.groupby(["month", "sensor"], as_index=False)
        .agg(
            detection_count=("detection_count", "sum"),
            frp_sum=("frp_sum", "sum"),
        )
    )

    monthly.to_csv(
        OUTPUT_DIR / "monthly_sensor_activity.csv",
        index=False,
    )

    # Yearly sensor-level activity.
    daily["year"] = pd.to_datetime(
        daily["acquisition_date"]
    ).dt.year

    yearly = (
        daily.groupby(["year", "sensor"], as_index=False)
        .agg(
            detection_count=("detection_count", "sum"),
            frp_sum=("frp_sum", "sum"),
        )
    )

    yearly.to_csv(
        OUTPUT_DIR / "yearly_sensor_activity.csv",
        index=False,
    )

    print("\n========== H3 AGGREGATION SUMMARY ==========")
    print(f"Input observations: {processed:,}")
    print(f"Daily cell-sensor records: {len(daily):,}")
    print(f"Unique H3 cells: {daily['h3_cell'].nunique():,}")
    print(f"Cell-date comparison records: {len(comparison):,}")
    print(
        "Cell-dates with both sensors:",
        int(comparison["both_sensors_observed"].sum()),
    )
    print(f"Monthly records: {len(monthly):,}")
    print(f"Yearly records: {len(yearly):,}")

    print("\nOutput directory:", OUTPUT_DIR)
    print("HISTORICAL GRID AGGREGATION COMPLETE")


if __name__ == "__main__":
    main()
