
import os
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

# Load credentials
load_dotenv(PROJECT_ROOT / "backend" / ".env")

MAP_KEY = os.getenv("FIRMS_MAP_KEY")

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# Approximate Maharashtra bounding box
MAHARASHTRA_BBOX = "72.6,15.6,80.9,22.1"

# Initial test: one recent day
DAY_RANGE = 5

SOURCES = {
    "modis": "MODIS_NRT",
    "viirs_snpp": "VIIRS_SNPP_NRT",
    "viirs_noaa20": "VIIRS_NOAA20_NRT",
    "viirs_noaa21": "VIIRS_NOAA21_NRT",
}


class FIRMSClientError(Exception):
    """Raised when a NASA FIRMS request fails."""


def fetch_hotspots(source: str) -> pd.DataFrame:
    """
    Fetch recent active-fire observations from NASA FIRMS.

    Args:
        source: MODIS_NRT or VIIRS_SNPP_NRT

    Returns:
        DataFrame containing raw NASA FIRMS observations.
    """

    if not MAP_KEY:
        raise FIRMSClientError(
            "FIRMS_MAP_KEY is missing. Check backend/.env"
        )

    if source not in SOURCES.values():
        raise ValueError(f"Unsupported FIRMS source: {source}")

    url = (
        f"{BASE_URL}/{MAP_KEY}/"
        f"{source}/{MAHARASHTRA_BBOX}/{DAY_RANGE}"
    )

    try:
        response = requests.get(url, timeout=45)
        response.raise_for_status()

        content = response.text.strip()

        if not content:
            return pd.DataFrame()

        if "Invalid MAP_KEY" in content:
            raise FIRMSClientError("NASA FIRMS rejected the MAP_KEY.")

        if content.lower().startswith(("error", "invalid")):
            raise FIRMSClientError(
                f"NASA FIRMS returned an error for {source}."
            )

        df = pd.read_csv(StringIO(content))

        return df

    except requests.RequestException as exc:
        # Do not print the request URL because it contains the MAP_KEY.
        raise FIRMSClientError(
            f"Network request failed for {source}: "
            f"{type(exc).__name__}"
        ) from None

    except pd.errors.ParserError:
        raise FIRMSClientError(
            f"Could not parse the CSV response for {source}."
        ) from None


def save_raw_data(df: pd.DataFrame, filename: str) -> Path:
    """Save an untouched copy of the source observations."""

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    output_path = RAW_DATA_DIR / filename
    df.to_csv(output_path, index=False)

    return output_path


def fetch_all_sensors() -> dict[str, pd.DataFrame]:
    """Fetch MODIS and VIIRS independently."""

    results = {}

    for name, source in SOURCES.items():
        print(f"\nFetching {name.upper()} ({source})...")

        df = fetch_hotspots(source)

        print(f"Records received: {len(df)}")
        print(f"Columns: {list(df.columns)}")

        if not df.empty:
            path = save_raw_data(
                df,
                f"{name}_nrt.csv"
            )
            print(f"Saved to: {path}")

        results[name] = df

    return results


if __name__ == "__main__":
    try:
        datasets = fetch_all_sensors()

        print("\n========== FETCH SUMMARY ==========")

        for sensor, df in datasets.items():
            print(f"{sensor.upper()}: {len(df)} records")

        print("\nFIRMS ingestion test completed.")

    except FIRMSClientError as exc:
        print(f"\nFIRMS ERROR: {exc}")
