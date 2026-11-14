
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / "backend" / ".env")

MAP_KEY = os.getenv("FIRMS_MAP_KEY")

if not MAP_KEY:
    raise RuntimeError("FIRMS_MAP_KEY not found in backend/.env")

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# Same bounding box used for the NRT test
AREA = "72.6,15.6,80.9,22.1"

SOURCES = ["MODIS_SP", "VIIRS_SNPP_SP"]

START_DATE = "2025-01-01"
DAY_RANGE = 5

OUTPUT_DIR = PROJECT_ROOT / "data" / "historical" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def download_sample(source: str):
    url = (
        f"{BASE_URL}/{MAP_KEY}/{source}/"
        f"{AREA}/{DAY_RANGE}/{START_DATE}"
    )

    print(f"\nRequesting {source}...")

    response = requests.get(url, timeout=60)
    response.raise_for_status()

    output_file = OUTPUT_DIR / f"{source.lower()}_test.csv"
    output_file.write_text(response.text, encoding="utf-8")

    lines = response.text.strip().splitlines()

    print(f"Status: {response.status_code}")
    print(f"Saved: {output_file}")
    print(f"Rows returned (excluding header): {max(0, len(lines) - 1)}")
    print(f"Header: {lines[0] if lines else 'EMPTY RESPONSE'}")


if __name__ == "__main__":
    for source in SOURCES:
        try:
            download_sample(source)
        except requests.RequestException as exc:
            print(f"Request failed for {source}: {exc}")
