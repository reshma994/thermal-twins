
from pathlib import Path

import h3
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]

INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "normalized_hotspots.csv"
)

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

H3_RESOLUTION = 7


def load_observations() -> pd.DataFrame:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Normalized data not found: {INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE)

    required = [
        "latitude",
        "longitude",
        "sensor",
        "satellite",
        "acquisition_date",
        "acquisition_time",
        "frp",
        "brightness_primary",
    ]

    missing = set(required) - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required fields: {sorted(missing)}"
        )

    return df


def assign_spatial_cells(
    df: pd.DataFrame,
) -> pd.DataFrame:

    result = df.copy()

    result["h3_cell"] = result.apply(
        lambda row: h3.latlng_to_cell(
            float(row["latitude"]),
            float(row["longitude"]),
            H3_RESOLUTION,
        ),
        axis=1,
    )

    result["h3_resolution"] = H3_RESOLUTION

    return result


def aggregate_daily_activity(
    df: pd.DataFrame,
) -> pd.DataFrame:

    group_columns = [
        "h3_cell",
        "acquisition_date",
        "sensor",
        "satellite",
    ]

    daily = (
        df.groupby(group_columns, dropna=False)
        .agg(
            detection_count=("latitude", "size"),
            frp_sum=("frp", "sum"),
            frp_mean=("frp", "mean"),
            frp_max=("frp", "max"),
            brightness_mean=(
                "brightness_primary",
                "mean",
            ),
            latitude_mean=("latitude", "mean"),
            longitude_mean=("longitude", "mean"),
        )
        .reset_index()
    )

    daily["h3_resolution"] = H3_RESOLUTION

    return daily


def create_sensor_comparison(
    daily: pd.DataFrame,
) -> pd.DataFrame:

    comparison = (
        daily.groupby(
            ["h3_cell", "acquisition_date", "sensor"]
        )["detection_count"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )

    # These are separate sensor-specific counts.
    # Their sum is NOT a unique-fire count.
    for sensor in ["MODIS", "VIIRS"]:
        if sensor not in comparison.columns:
            comparison[sensor] = 0

    comparison["both_sensors_observed"] = (
        (comparison["MODIS"] > 0)
        & (comparison["VIIRS"] > 0)
    )

    return comparison


def run_harmonization() -> None:

    print("Loading normalized observations...")
    observations = load_observations()

    print("Assigning H3 spatial cells...")
    spatial = assign_spatial_cells(observations)

    print("Aggregating daily activity...")
    daily = aggregate_daily_activity(spatial)

    print("Creating sensor comparison...")
    comparison = create_sensor_comparison(daily)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    spatial.to_csv(
        OUTPUT_DIR / "spatial_observations.csv",
        index=False,
    )

    daily.to_csv(
        OUTPUT_DIR / "daily_cell_activity.csv",
        index=False,
    )

    comparison.to_csv(
        OUTPUT_DIR / "sensor_comparison.csv",
        index=False,
    )

    print("\n========== HARMONIZATION SUMMARY ==========")

    print("Input observations:", len(observations))
    print("Spatial observations:", len(spatial))
    print("Daily cell records:", len(daily))
    print("Comparison records:", len(comparison))

    print("\nDaily records by sensor:")
    print(daily.groupby("sensor")["detection_count"].sum())

    print(
        "\nCells with observations from both sensors:",
        int(comparison["both_sensors_observed"].sum()),
    )

    print("\nOutput files:")
    print("- spatial_observations.csv")
    print("- daily_cell_activity.csv")
    print("- sensor_comparison.csv")

    print("\nHarmonization stage completed.")


if __name__ == "__main__":
    run_harmonization()
