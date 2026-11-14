
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]

DAILY_FILE = (
    ROOT / "data/historical/processed/analytics/"
    / "daily_cell_activity.csv"
)

CALENDAR_FILE = (
    ROOT / "data/historical/processed/analytics/burning_calendar/"
    / "monthly_burning_calendar.csv"
)

OUTPUT = (
    ROOT / "data/historical/processed/analytics/burning_calendar/"
    / "peak_month_investigation.csv"
)


def main():
    daily = pd.read_csv(DAILY_FILE)
    calendar = pd.read_csv(CALENDAR_FILE)

    daily["acquisition_date"] = pd.to_datetime(
        daily["acquisition_date"]
    )

    calendar["month"] = pd.to_datetime(calendar["month"])

    # Rank the highest-activity months independently per sensor.
    print("\n========== TOP 10 MONTHS ==========")

    for sensor in ["MODIS", "VIIRS"]:
        subset = calendar[calendar["sensor"] == sensor]

        top = subset.nlargest(10, "detection_count")[
            ["month", "detection_count", "frp_sum",
             "active_h3_cells", "baseline_median",
             "anomaly_vs_median"]
        ]

        print(f"\n{sensor}")
        print(top.to_string(index=False))

    # Investigate daily activity during March 2021.
    peak_daily = daily[
        daily["acquisition_date"].between(
            "2021-03-01", "2021-03-31"
        )
    ]

    daily_summary = (
        peak_daily.groupby(
            ["acquisition_date", "sensor"],
            as_index=False
        )
        .agg(
            detections=("detection_count", "sum"),
            frp_sum=("frp_sum", "sum"),
            active_cells=("h3_cell", "nunique"),
        )
    )

    print("\n========== MARCH 2021 DAILY ACTIVITY ==========")

    for sensor in ["MODIS", "VIIRS"]:
        subset = daily_summary[
            daily_summary["sensor"] == sensor
        ]

        print(f"\n{sensor}")
        print(f"Days with detections: {len(subset)}")
        print(f"Total detections: {subset['detections'].sum():,}")
        print(f"Peak daily detections: {subset['detections'].max():,}")

    daily_summary.to_csv(OUTPUT, index=False)

    print("\nInvestigation saved:", OUTPUT)


if __name__ == "__main__":
    main()

