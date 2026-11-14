
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

FILES = {
    "MODIS": "modis_nrt.csv",
    "VIIRS NOAA-20": "viirs_noaa20_nrt.csv",
    "VIIRS NOAA-21": "viirs_noaa21_nrt.csv",
}


def inspect_file(name, filename):
    path = RAW_DIR / filename

    print("\n" + "=" * 65)
    print(f"DATASET: {name}")
    print("=" * 65)

    if not path.exists():
        print("File not found:", path)
        return

    df = pd.read_csv(path)

    print("\nShape:", df.shape)

    print("\nColumn names:")
    print(df.columns.tolist())

    print("\nData types:")
    print(df.dtypes.to_string())

    print("\nFirst 5 records:")
    print(df.head().to_string(index=False))

    print("\nMissing values:")
    print(df.isna().sum().to_string())

    if "acq_date" in df.columns:
        dates = pd.to_datetime(
            df["acq_date"], errors="coerce"
        )
        print("\nObservation date range:")
        print("Earliest:", dates.min())
        print("Latest:", dates.max())

    if "satellite" in df.columns:
        print("\nSatellite values:")
        print(df["satellite"].value_counts(dropna=False))

    if "confidence" in df.columns:
        print("\nConfidence values:")
        print(df["confidence"].value_counts(dropna=False))

    if "instrument" in df.columns:
        print("\nInstrument values:")
        print(df["instrument"].value_counts(dropna=False))


if __name__ == "__main__":
    for name, filename in FILES.items():
        inspect_file(name, filename)
