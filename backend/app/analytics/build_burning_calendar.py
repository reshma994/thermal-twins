
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]

INPUT = (
    ROOT / "data/historical/processed/analytics/"
    / "daily_cell_activity.csv"
)

OUTPUT_DIR = (
    ROOT / "data/historical/processed/analytics/"
    / "burning_calendar"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SENSORS = ["MODIS", "VIIRS"]

START_MONTH = "2012-01-01"
END_MONTH = "2026-07-01"

BASELINE_START_YEAR = 2013
BASELINE_END_YEAR = 2025


def build_monthly_series():
    print("Loading daily H3 activity...")

    daily = pd.read_csv(INPUT)

    daily["acquisition_date"] = pd.to_datetime(
        daily["acquisition_date"],
        errors="coerce"
    )

    daily = daily.dropna(subset=["acquisition_date"])

    daily["month"] = (
        daily["acquisition_date"].dt.to_period("M").dt.to_timestamp()
    )

    monthly = (
        daily.groupby(["sensor", "month"], as_index=False)
        .agg(
            detection_count=("detection_count", "sum"),
            frp_sum=("frp_sum", "sum"),
            active_h3_cells=("h3_cell", "nunique"),
        )
    )

    # Create a complete month series for both sensors.
    # Months with no returned detections are explicitly zero-filled.
    all_months = pd.date_range(
        START_MONTH, END_MONTH, freq="MS"
    )

    full_index = pd.MultiIndex.from_product(
        [SENSORS, all_months],
        names=["sensor", "month"]
    )

    monthly = (
        monthly.set_index(["sensor", "month"])
        .reindex(full_index)
        .reset_index()
    )

    for column in [
        "detection_count",
        "frp_sum",
        "active_h3_cells",
    ]:
        monthly[column] = monthly[column].fillna(0)

    monthly["detection_count"] = (
        monthly["detection_count"].astype(int)
    )
    monthly["active_h3_cells"] = (
        monthly["active_h3_cells"].astype(int)
    )

    monthly["year"] = monthly["month"].dt.year
    monthly["calendar_month"] = monthly["month"].dt.month

    return monthly


def build_seasonal_baseline(monthly):
    print("Calculating seasonal baselines...")

    baseline_period = monthly[
        monthly["year"].between(
            BASELINE_START_YEAR,
            BASELINE_END_YEAR
        )
    ].copy()

    baseline = (
        baseline_period.groupby(
            ["sensor", "calendar_month"],
            as_index=False
        )
        .agg(
            baseline_median=(
                "detection_count", "median"
            ),
            baseline_mean=(
                "detection_count", "mean"
            ),
            baseline_q25=(
                "detection_count",
                lambda values: values.quantile(0.25)
            ),
            baseline_q75=(
                "detection_count",
                lambda values: values.quantile(0.75)
            ),
            baseline_years=("year", "nunique"),
        )
    )

    result = monthly.merge(
        baseline,
        on=["sensor", "calendar_month"],
        how="left"
    )

    result["anomaly_vs_median"] = (
        result["detection_count"] - result["baseline_median"]
    )

    result["anomaly_ratio"] = (
        result["detection_count"]
        / result["baseline_median"].replace(0, pd.NA)
    )

    result["above_baseline_q75"] = (
        result["detection_count"] > result["baseline_q75"]
    )

    return result, baseline


def main():
    print("========== BURNING ACTIVITY CALENDAR ==========")
    print(
        f"Baseline period: "
        f"{BASELINE_START_YEAR}-{BASELINE_END_YEAR}"
    )

    monthly = build_monthly_series()

    calendar, baseline = build_seasonal_baseline(monthly)

    # Complete monthly calendar with historical comparison.
    calendar.to_csv(
        OUTPUT_DIR / "monthly_burning_calendar.csv",
        index=False
    )

    # Typical seasonal profile for each sensor.
    baseline.to_csv(
        OUTPUT_DIR / "seasonal_baseline.csv",
        index=False
    )

    # Yearly totals for long-term trends.
    yearly = (
        monthly.groupby(["sensor", "year"], as_index=False)
        .agg(
            detection_count=("detection_count", "sum"),
            frp_sum=("frp_sum", "sum"),
            active_months=(
                "detection_count",
                lambda values: int((values > 0).sum())
            ),
        )
    )

    yearly.to_csv(
        OUTPUT_DIR / "yearly_burning_activity.csv",
        index=False
    )

    # Heatmap-ready table: rows can be grouped by sensor and year.
    heatmap = calendar.pivot_table(
        index=["sensor", "year"],
        columns="calendar_month",
        values="detection_count",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()

    heatmap.to_csv(
        OUTPUT_DIR / "year_month_heatmap.csv",
        index=False
    )

    print("\n========== CALENDAR SUMMARY ==========")
    print(f"Monthly records: {len(calendar)}")
    print(f"Baseline records: {len(baseline)}")
    print(f"Yearly records: {len(yearly)}")

    for sensor in SENSORS:
        subset = calendar[calendar["sensor"] == sensor]

        peak = subset.loc[
            subset["detection_count"].idxmax()
        ]

        print(f"\n{sensor}")
        print(
            f"Peak month: {peak['month'].strftime('%Y-%m')}"
        )
        print(
            f"Peak detections: "
            f"{int(peak['detection_count']):,}"
        )

        seasonal = baseline[
            baseline["sensor"] == sensor
        ]

        typical_peak = seasonal.loc[
            seasonal["baseline_median"].idxmax()
        ]

        print(
            f"Typical peak calendar month: "
            f"{int(typical_peak['calendar_month'])}"
        )
        print(
            f"Typical monthly median detections: "
            f"{typical_peak['baseline_median']:,.1f}"
        )

    print("\nOutput directory:", OUTPUT_DIR)
    print("BURNING CALENDAR GENERATED")


if __name__ == "__main__":
    main()
