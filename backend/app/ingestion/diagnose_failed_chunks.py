
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / "backend" / ".env")

KEY = os.getenv("FIRMS_MAP_KEY")
if not KEY:
    raise RuntimeError("FIRMS_MAP_KEY missing")

BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
AREA = "72.6,15.6,80.9,22.1"

FAILED_DATES = [
    "2018-11-24",
    "2018-11-29",
    "2018-12-04",
    "2018-12-09",
    "2018-12-14",
    "2018-12-19",
    "2025-12-07",
]

session = requests.Session()

for date in FAILED_DATES:
    print(f"\nChecking MODIS_SP: {date}")

    for days in [5, 1]:
        url = f"{BASE}/{KEY}/MODIS_SP/{AREA}/{days}/{date}"

        try:
            response = session.get(url, timeout=60)

            print(f"  Range: {days} day(s)")
            print(f"  HTTP status: {response.status_code}")

            if response.ok:
                lines = response.text.strip().splitlines()
                print(
                    f"  Rows: {max(0, len(lines) - 1)}"
                    if lines else "  Empty response"
                )
            else:
                # Print the response body, never the request URL.
                print(f"  API message: {response.text[:500]}")

        except requests.RequestException as exc:
            print(f"  Request error: {type(exc).__name__}: {exc}")

session.close()
