
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]

DAILY_FILE = (
    ROOT / "data/historical/processed/analytics/"
    / "daily_cell_activity.csv"
)

OUTPUT_DIR = (
    ROOT / "data/historical/processed/analytics/"
    / "burning_calendar"
)


def main():
    daily = pd.read_csv(DAILY_FILE)

    daily["acquisition_date"] = pd.to_datetime(
        daily["acquisition_date"]
    )

    march = daily[
        daily["acquisition_date"].between(
            "2021-03-01", "2021-03-31"
        )
    ].copy()

    for sensor in ["MODIS", "VIIRS"]:
        subset = march[march["sensor"] == sensor].copy()

        print(f"\n{'=' * 50}")
        print(f"{sensor} — MARCH 2021 SPATIAL INVESTIGATION")
        print(f"{'=' * 50}")

        # Aggregate activity by H3 cell.
        cells = (
            subset.groupby("h3_cell", as_index=False)
            .agg(
                detections=("detection_count", "sum"),
                frp_sum=("frp_sum", "sum"),
                active_days=("acquisition_date", "nunique"),
            )
            .sort_values("detections", ascending=False)
        )

        total = cells["detections"].sum()
        top_10_share = (
            cells.head(10)["detections"].sum() / total * 100
        )

        print(f"Total detections: {total:,}")
        print(f"Unique active H3 cells: {len(cells):,}")
        print(f"Top 10 cells' share: {top_10_share:.2f}%")

        print("\nTOP 20 H3 CELLS")
        print(cells.head(20).to_string(index=False))

        # Daily activity ranking.
        daily_summary = (
            subset.groupby("acquisition_date", as_index=False)
            .agg(
                detections=("detection_count", "sum"),
                frp_sum=("frp_sum", "sum"),
                active_cells=("h3_cell", "nunique"),
            )
            .sort_values("detections", ascending=False)
        )

        print("\nTOP 10 DAYS")
        print(daily_summary.head(10).to_string(index=False))

        cells.to_csv(
            OUTPUT_DIR / f"march_2021_{sensor.lower()}_cells.csv",
            index=False,
        )

        daily_summary.to_csv(
            OUTPUT_DIR / f"march_2021_{sensor.lower()}_daily.csv",
            index=False,
        )

    print("\nSPATIAL INVESTIGATION COMPLETE")


if __name__ == "__main__":
    main()
