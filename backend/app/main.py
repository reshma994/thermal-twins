from fastapi import FastAPI

app = FastAPI(
    title="Thermal Twins API",
    description="MODIS and VIIRS hotspot harmonization platform",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "project": "Thermal Twins",
        "description": "MODIS + VIIRS Hotspot Harmonization",
        "status": "running",
    }


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "service": "thermal-twins-backend",
    }
