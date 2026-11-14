
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]

INPUTS = {
    "MODIS": ROOT / "data/historical/processed/modis_sp_historical.csv",
    "VIIRS": ROOT / "data/historical/processed/viirs_snpp_sp_historical.csv",
}

OUTPUT = (
    ROOT
    / "data/historical/processed/"
    / "historical_observations_normalized.csv"
)

CHUNK_SIZE = 100_000


def normalize_chunk(df, sensor, source_file):
    primary = "brightness" if sensor == "MODIS" else "bright_ti4"
    secondary = "bright_t31" if sensor == "MODIS" else "bright_ti5"

    result = pd.DataFrame()

    result["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    result["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    result["acquisition_date"] = pd.to_datetime(
        df["acq_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")

    # FIRMS acquisition time is HHMM in UTC.
    time_numeric = pd.to_numeric(df["acq_time"], errors="coerce")
    time_string = time_numeric.map(
        lambda value: f"{int(value):04d}" if pd.notna(value) else None
    )

    datetime_string = (
        result["acquisition_date"].fillna("")
        + " "
        + time_string.fillna("")
    )

    result["acquisition_datetime_utc"] = pd.to_datetime(
        datetime_string,
        format="%Y-%m-%d %H%M",
        errors="coerce",
        utc=True,
    )

    result["acquisition_time_utc"] = time_string

    result["sensor"] = sensor
    result["satellite"] = df["satellite"].astype("string")
    result["instrument"] = df["instrument"].astype("string")

    result["brightness_primary"] = pd.to_numeric(
        df[primary], errors="coerce"
    )
    result["brightness_secondary"] = pd.to_numeric(
        df[secondary], errors="coerce"
    )

    result["brightness_primary_source_field"] = primary
    result["brightness_secondary_source_field"] = secondary

    result["frp"] = pd.to_numeric(df["frp"], errors="coerce")

    result["confidence_raw"] = df["confidence"].astype("string")
    result["confidence_numeric"] = pd.to_numeric(
        df["confidence"], errors="coerce"
    )

    result["scan"] = pd.to_numeric(df["scan"], errors="coerce")
    result["track"] = pd.to_numeric(df["track"], errors="coerce")

    result["daynight"] = df["daynight"].astype("string")
    result["product_version"] = df["version"].astype("string")
    result["detection_type"] = df["type"].astype("string")

    result["source_product"] = (
        "MODIS_SP" if sensor == "MODIS" else "VIIRS_SNPP_SP"
    )
    result["source_file"] = source_file

    return result


def main():
    if OUTPUT.exists():
        OUTPUT.unlink()

    total = {"MODIS": 0, "VIIRS": 0}
    invalid_coordinates = 0
    invalid_datetimes = 0

    for sensor, input_path in INPUTS.items():
        print(f"\nNormalizing {sensor}...")
        first_write = not OUTPUT.exists()

        for chunk in pd.read_csv(input_path, chunksize=CHUNK_SIZE):
            normalized = normalize_chunk(
                chunk, sensor, input_path.name
            )

            invalid_coordinates += int(
                (
                    normalized["latitude"].isna()
                    | normalized["longitude"].isna()
                ).sum()
            )

            invalid_datetimes += int(
                normalized["acquisition_datetime_utc"].isna().sum()
            )

            normalized.to_csv(
                OUTPUT,
                mode="w" if first_write else "a",
                header=first_write,
                index=False,
            )

            first_write = False
            total[sensor] += len(normalized)

            print(
                f"{sensor}: {total[sensor]:,} rows processed",
                end="\r",
            )

        print()

    print("\n========== NORMALIZATION SUMMARY ==========")
    print(f"MODIS records: {total['MODIS']:,}")
    print(f"VIIRS records: {total['VIIRS']:,}")
    print(f"Total records: {sum(total.values()):,}")
    print(f"Invalid coordinates: {invalid_coordinates:,}")
    print(f"Invalid UTC datetimes: {invalid_datetimes:,}")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()

