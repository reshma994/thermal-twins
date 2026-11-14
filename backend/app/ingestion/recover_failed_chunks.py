
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / "backend" / ".env", override=True)

MAP_KEY = os.getenv("FIRMS_MAP_KEY")
if not MAP_KEY:
    raise RuntimeError("FIRMS_MAP_KEY missing")

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
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

OUTPUT_DIR = ROOT / "data" / "historical" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_COLUMNS = {
    "latitude", "longitude", "brightness",
    "acq_date", "acq_time", "satellite",
    "instrument", "frp",
}


def recover(session, date_string):
    filename = f"modis_sp_{date_string.replace('-', '')}.csv"
    output_file = OUTPUT_DIR / filename

    if output_file.exists() and output_file.stat().st_size > 0:
        print(f"Already exists, skipping: {filename}")
        return True

    url = (
        f"{BASE_URL}/{MAP_KEY}/MODIS_SP/"
        f"{AREA}/5/{date_string}"
    )

    for attempt in range(1, 4):
        try:
            response = session.get(url, timeout=90)

            if not response.ok:
                # Never print the URL; it contains the API key.
                raise RuntimeError(
                    f"HTTP {response.status_code}: "
                    f"{response.text[:300]}"
                )

            lines = response.text.strip().splitlines()
            if not lines:
                raise RuntimeError("Empty response")

            columns = set(lines[0].split(","))
            if not REQUIRED_COLUMNS.issubset(columns):
                raise RuntimeError("Unexpected CSV schema")

            temp_file = output_file.with_suffix(".tmp")
            temp_file.write_text(response.text, encoding="utf-8")
            temp_file.replace(output_file)

            print(
                f"Saved {filename} | "
                f"{len(lines) - 1} detections"
            )
            return True

        except Exception as exc:
            print(
                f"Attempt {attempt}/3 failed for {date_string}: "
                f"{type(exc).__name__}: {exc}"
            )
            if attempt < 3:
                time.sleep(2 ** attempt)

    return False


def main():
    session = requests.Session()
    recovered = 0
    failed = []

    for date_string in FAILED_DATES:
        print(f"\nRecovering {date_string}...")
        if recover(session, date_string):
            recovered += 1
        else:
            failed.append(date_string)

        time.sleep(1)

    session.close()

    print("\n========== RECOVERY SUMMARY ==========")
    print(f"Recovered: {recovered}/{len(FAILED_DATES)}")
    print(f"Still failed: {len(failed)}")

    if failed:
        print("Failed dates:", ", ".join(failed))


if __name__ == "__main__":
    main()
