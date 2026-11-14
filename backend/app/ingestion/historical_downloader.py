
import os
import time
from pathlib import Path
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / "backend" / ".env")

MAP_KEY = os.getenv("FIRMS_MAP_KEY")

if not MAP_KEY:
    raise RuntimeError("FIRMS_MAP_KEY not found in backend/.env")

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
AREA = "72.6,15.6,80.9,22.1"

START_DATE = date(2012, 1, 20)
END_DATE = date(2026, 7, 31)
CHUNK_DAYS = 5

SOURCES = ["MODIS_SP", "VIIRS_SNPP_SP"]

OUTPUT_DIR = PROJECT_ROOT / "data" / "historical" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EXPECTED_COLUMNS = {
    "MODIS_SP": {
        "latitude", "longitude", "brightness", "acq_date",
        "acq_time", "satellite", "instrument", "frp"
    },
    "VIIRS_SNPP_SP": {
        "latitude", "longitude", "bright_ti4", "acq_date",
        "acq_time", "satellite", "instrument", "frp"
    },
}


def date_chunks():
    current = START_DATE

    while current <= END_DATE:
        days = min(
            CHUNK_DAYS,
            (END_DATE - current).days + 1
        )

        yield current, days
        current += timedelta(days=days)


def download_chunk(session, source, chunk_date, days):
    date_string = chunk_date.strftime("%Y-%m-%d")
    filename = (
        f"{source.lower()}_{chunk_date.strftime('%Y%m%d')}.csv"
    )
    output_file = OUTPUT_DIR / filename

    # Resume support: don't download an existing completed chunk.
    if output_file.exists() and output_file.stat().st_size > 0:
        return "skipped"

    url = (
        f"{BASE_URL}/{MAP_KEY}/{source}/"
        f"{AREA}/{days}/{date_string}"
    )

    for attempt in range(1, 4):
        try:
            response = session.get(url, timeout=90)
            response.raise_for_status()

            lines = response.text.strip().splitlines()

            if not lines:
                raise ValueError("Empty API response")

            columns = set(lines[0].split(","))

            if not EXPECTED_COLUMNS[source].issubset(columns):
                raise ValueError(
                    f"Unexpected CSV header for {source}: {lines[0]}"
                )

            temporary_file = output_file.with_suffix(".tmp")
            temporary_file.write_text(
                response.text,
                encoding="utf-8"
            )
            temporary_file.replace(output_file)

            return "downloaded"

        except Exception as exc:
            if attempt == 3:
                print(
                    f"\nFAILED: {source} {date_string}: "
                    f"{type(exc).__name__}: {exc}"
                )
                return "failed"

            time.sleep(2 ** attempt)

    return "failed"


def main():
    total_chunks = len(list(date_chunks()))

    print("Historical FIRMS download")
    print(f"Period: {START_DATE} to {END_DATE}")
    print(f"Sources: {', '.join(SOURCES)}")
    print(f"Chunks per source: {total_chunks}")
    print("Existing chunks will be skipped.\n")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "ThermalTwins-Hackathon/1.0"
    })

    for source in SOURCES:
        print(f"\n========== {source} ==========")

        downloaded = 0
        skipped = 0
        failed = 0

        for index, (chunk_date, days) in enumerate(
            date_chunks(), start=1
        ):
            result = download_chunk(
                session, source, chunk_date, days
            )

            if result == "downloaded":
                downloaded += 1
            elif result == "skipped":
                skipped += 1
            else:
                failed += 1

            if index % 20 == 0 or index == total_chunks:
                print(
                    f"{index}/{total_chunks} | "
                    f"Downloaded: {downloaded} | "
                    f"Skipped: {skipped} | "
                    f"Failed: {failed}"
                )

            # Be gentle with the API.
            time.sleep(0.2)

        print(f"\n{source} complete.")
        print(f"Downloaded: {downloaded}")
        print(f"Skipped: {skipped}")
        print(f"Failed: {failed}")

    session.close()
    print("\nHistorical download process finished.")


if __name__ == "__main__":
    main()
