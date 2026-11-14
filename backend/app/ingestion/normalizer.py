
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def _read_csv(filename: str) -> pd.DataFrame:
    path = RAW_DIR / filename

    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    return pd.read_csv(path)


def _validate_coordinates(df: pd.DataFrame) -> None:
    invalid = (
        ~df["latitude"].between(-90, 90)
        | ~df["longitude"].between(-180, 180)
    )

    if invalid.any():
        raise ValueError(
            f"Found {invalid.sum()} invalid coordinate records"
        )


def _build_common_fields(
    df: pd.DataFrame,
    sensor: str,
    source_file: str,
    primary_field: str,
    secondary_field: str,
) -> pd.DataFrame:

    required = [
        "latitude", "longitude", "acq_date", "acq_time",
        "satellite", "confidence", "version",
        "scan", "track", "frp", "daynight",
        primary_field, secondary_field,
    ]

    missing = set(required) - set(df.columns)

    if missing:
        raise ValueError(
            f"{sensor}: Missing required columns: {sorted(missing)}"
        )

    # Keep a copy of the original source columns.
    result = df.copy()

    result["sensor"] = sensor
    result["acquisition_date"] = pd.to_datetime(
        result["acq_date"], errors="coerce"
    ).dt.date

    time_values = pd.to_numeric(
        result["acq_time"], errors="coerce"
    )

    valid_time = (
        time_values.notna()
        & time_values.between(0, 2359)
        & (time_values % 100 < 60)
    )

    if not valid_time.all():
        raise ValueError(
            f"{sensor}: Invalid acquisition time values"
        )

    result["acquisition_time"] = (
        time_values.astype(int).astype(str).str.zfill(4)
    )

    # Store the source date/time as a parsed timestamp.
    # Preserve original date and time fields as well.
    result["acquisition_datetime"] = pd.to_datetime(
        result["acq_date"].astype(str)
        + " "
        + result["acquisition_time"],
        format="%Y-%m-%d %H%M",
        errors="coerce",
    )

    result["brightness_primary"] = pd.to_numeric(
        result[primary_field], errors="coerce"
    )

    result["brightness_secondary"] = pd.to_numeric(
        result[secondary_field], errors="coerce"
    )

    result["brightness_primary_source_field"] = primary_field
    result["brightness_secondary_source_field"] = secondary_field

    result["confidence_raw"] = result["confidence"].astype(str)
    result["confidence_type"] = (
        "numeric" if sensor == "MODIS" else "categorical"
    )

    result["product_version"] = result["version"].astype(str)
    result["source_file"] = source_file

    for column in ["latitude", "longitude", "frp", "scan", "track"]:
        result[column] = pd.to_numeric(
            result[column], errors="coerce"
        )

    if result["acquisition_datetime"].isna().any():
        raise ValueError(f"{sensor}: Invalid acquisition dates/times")

    if result[
        ["latitude", "longitude", "frp", "scan", "track"]
    ].isna().any().any():
        raise ValueError(f"{sensor}: Invalid numeric values found")

    _validate_coordinates(result)

    return result


def normalize_modis() -> pd.DataFrame:
    df = _read_csv("modis_nrt.csv")

    return _build_common_fields(
        df=df,
        sensor="MODIS",
        source_file="modis_nrt.csv",
        primary_field="brightness",
        secondary_field="bright_t31",
    )


def normalize_viirs(
    filename: str,
) -> pd.DataFrame:
    df = _read_csv(filename)

    return _build_common_fields(
        df=df,
        sensor="VIIRS",
        source_file=filename,
        primary_field="bright_ti4",
        secondary_field="bright_ti5",
    )


def normalize_all() -> pd.DataFrame:
    modis = normalize_modis()

    viirs_20 = normalize_viirs("viirs_noaa20_nrt.csv")
    viirs_21 = normalize_viirs("viirs_noaa21_nrt.csv")

    combined = pd.concat(
        [modis, viirs_20, viirs_21],
        ignore_index=True,
        sort=False,
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    output_path = PROCESSED_DIR / "normalized_hotspots.csv"

    combined.to_csv(output_path, index=False)

    print("\n========== NORMALIZATION SUMMARY ==========")
    print("Total records:", len(combined))
    print("\nRecords by sensor:")
    print(combined.groupby("sensor").size())

    print("\nRecords by satellite:")
    print(combined.groupby("satellite").size())

    print("\nOutput saved:", output_path)

    return combined


if __name__ == "__main__":
    normalize_all()
