from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
WEB_DATA = ROOT / "web" / "public" / "data"

FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov"
DAY_RANGE = 5  # API maximum per call

H3_UNIT_RES = 7  # ~5.2 km2: harmonization unit
H3_AGG_RES = 6  # ~36 km2: web aggregation cell


@dataclass(frozen=True)
class AOI:
    key: str
    name: str
    bbox: tuple[float, float, float, float]  # west, south, east, north
    priority: int
    country: str | None = None  # FIRMS country-file name; None = API only
    crop: bool = True  # crop country files to bbox (False keeps the whole country)


AOIS: dict[str, AOI] = {a.key: a for a in [
    AOI("india", "India", (68.0, 6.5, 97.5, 37.5), 0, "India", crop=False),
    AOI("punjab_haryana", "Punjab & Haryana, India", (73.8, 27.6, 77.6, 32.6), 1, "India"),
    AOI("california", "California, USA", (-124.5, 32.5, -114.1, 42.0), 2, "United_States"),
    AOI("rondonia", "Rondônia, Brazil (Amazon arc)", (-66.9, -13.7, -59.7, -7.9), 3, "Brazil"),
    AOI("nsw", "New South Wales, Australia", (141.0, -37.5, 153.7, -28.2), 4, "Australia"),
    AOI("central_kalimantan", "Central Kalimantan, Indonesia", (110.7, -3.6, 115.9, 0.8), 5, "Indonesia"),
    AOI("yakutia_central", "Central Yakutia, Russia", (115.0, 58.0, 140.0, 66.0), 6, "Russian_Federation"),
    AOI("zambia_kafue", "Kafue, Zambia (savanna)", (24.0, -17.0, 29.0, -12.0), 7, "Zambia"),
]}

# FIRMS country yearly CSVs (Standard Processing, complete years only, no MAP_KEY / no quota).
COUNTRY_BASE = "https://firms.modaps.eosdis.nasa.gov/data/country"
COUNTRY_PRODUCTS = {  # product dir -> (SOURCE key, first year, last year)
    "modis": ("MODIS_SP", 2000, 2025),
    "viirs-snpp": ("VIIRS_SNPP_SP", 2012, 2025),
    "viirs-jpss1": ("VIIRS_NOAA20_SP", 2018, 2025),
}
BULK_LAST_YEAR = 2025  # API covers everything after this


@dataclass(frozen=True)
class Source:
    key: str
    family: str  # MODIS | VIIRS
    processing: str  # SP | NRT
    default_start: date
    default_end: date | None = None  # None = today


SOURCES: dict[str, Source] = {s.key: s for s in [
    Source("MODIS_SP", "MODIS", "SP", date(2000, 11, 1)),
    Source("MODIS_NRT", "MODIS", "NRT", date(2000, 11, 1)),
    Source("VIIRS_SNPP_SP", "VIIRS", "SP", date(2012, 1, 20)),
    Source("VIIRS_SNPP_NRT", "VIIRS", "NRT", date(2012, 1, 20), date(2026, 11, 2)),
    Source("VIIRS_NOAA20_SP", "VIIRS", "SP", date(2018, 4, 1)),
    Source("VIIRS_NOAA20_NRT", "VIIRS", "NRT", date(2018, 4, 1)),
    Source("VIIRS_NOAA21_SP", "VIIRS", "SP", date(2023, 3, 1)),
    Source("VIIRS_NOAA21_NRT", "VIIRS", "NRT", date(2023, 3, 1)),
]}

SP_TO_NRT = {"MODIS_SP": "MODIS_NRT", "VIIRS_SNPP_SP": "VIIRS_SNPP_NRT",
             "VIIRS_NOAA20_SP": "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_SP": "VIIRS_NOAA21_NRT"}

# Nominal equator crossing (local solar time, hours) at design orbit; drift handled in analysis.
PLATFORMS = {
    "Terra": {"family": "MODIS", "nominal_lst": 10.5, "start": date(2000, 2, 24)},
    "Aqua": {"family": "MODIS", "nominal_lst": 13.5, "start": date(2002, 7, 4)},
    "SNPP": {"family": "VIIRS", "nominal_lst": 13.5, "start": date(2012, 1, 20), "end": date(2026, 11, 2)},
    "NOAA20": {"family": "VIIRS", "nominal_lst": 13.5, "start": date(2018, 4, 1)},
    "NOAA21": {"family": "VIIRS", "nominal_lst": 13.5, "start": date(2023, 3, 1)},
}


def map_key() -> str:
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("FIRMS_MAP_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("FIRMS_MAP_KEY missing: copy .env.example to .env and paste your key.")
    return key
