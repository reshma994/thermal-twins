# thermal-twins
Sensor-aware MODIS and VIIRS active fire hotspot harmonization and historical burning activity analytics.

## Pipeline (Phase 1)

```bash
cp .env.example .env            # paste your FIRMS MAP_KEY
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m pipeline.fetch availability
.venv/Scripts/python -m pipeline.fetch run --aoi punjab_haryana
.venv/Scripts/python -m pipeline.clean --aoi punjab_haryana
.venv/Scripts/python -m pipeline.grid  --aoi punjab_haryana
```

## Use of SI tools

An AI coding assistant was used to speed up drafting of data-pipeline code and documentation. The team reviewed and tested all of it and is responsible for its content.
