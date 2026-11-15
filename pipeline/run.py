"""Run the full Thermal Twins pipeline for one area.

python -m pipeline.run --aoi india            # everything (API top-up needs FIRMS_MAP_KEY in .env)
python -m pipeline.run --aoi india --from dpt # resume from a stage
"""
from __future__ import annotations

import argparse
import time

from . import bulk, clean, dpt, export, fetch, grid, harmonize
from .config import AOIS, SOURCES

STAGES = ["bulk", "fetch", "clean", "grid", "dpt", "harmonize", "coverage", "export", "hotspots", "figures"]


def run_stage(name: str, aoi: str) -> None:
    if name == "bulk":
        if AOIS[aoi].country:
            bulk.run(aoi, workers=4)
    elif name == "fetch":
        fetch.main(["run", "--aoi", aoi, "--sources", ",".join(SOURCES)])
    elif name == "clean":
        clean.run(aoi)
    elif name == "grid":
        grid.run(aoi)
    elif name == "dpt":
        dpt.run(aoi)
    elif name == "harmonize":
        harmonize.run(aoi)
    elif name == "coverage":
        from . import coverage
        coverage.run(aoi)
    elif name == "export":
        export.run(aoi)
    elif name == "hotspots":
        from . import hotspots
        hotspots.run(aoi)
    elif name == "figures":
        from . import figures
        figures.run(aoi)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--aoi", required=True, choices=list(AOIS))
    p.add_argument("--from", dest="start", default=STAGES[0], choices=STAGES)
    p.add_argument("--to", dest="stop", default=STAGES[-1], choices=STAGES)
    a = p.parse_args()
    for name in STAGES[STAGES.index(a.start): STAGES.index(a.stop) + 1]:
        t0 = time.time()
        print(f"\n=== {name} ===", flush=True)
        run_stage(name, a.aoi)
        print(f"=== {name} done in {time.time() - t0:.0f} s ===", flush=True)


if __name__ == "__main__":
    main()
