
import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]

load_dotenv(PROJECT_ROOT / "backend" / ".env")

MAP_KEY = os.getenv("FIRMS_MAP_KEY")

URL = (
    "https://firms.modaps.eosdis.nasa.gov/"
    "api/data_availability/csv"
)


def check_availability():
    if not MAP_KEY:
        raise RuntimeError("FIRMS_MAP_KEY is missing")

    response = requests.get(
        f"{URL}/{MAP_KEY}/all",
        timeout=45,
    )

    response.raise_for_status()

    from io import StringIO

    df = pd.read_csv(StringIO(response.text))

    historical_sources = [
        "MODIS_SP",
        "VIIRS_SNPP_SP",
        "VIIRS_NOAA20_SP",
        "VIIRS_NOAA21_SP",
    ]

    result = df[df["data_id"].isin(historical_sources)].copy()

    print("\n========== NASA HISTORICAL DATA AVAILABILITY ==========")
    print(result.to_string(index=False))

    output_dir = PROJECT_ROOT / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)

    result.to_csv(
        output_dir / "historical_data_availability.csv",
        index=False,
    )

    print("\nSaved: historical_data_availability.csv")


if __name__ == "__main__":
    check_availability()
