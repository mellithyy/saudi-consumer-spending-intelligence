"""Run the analysis queries on the warehouse, print each result and save it as a CSV.

Stage 4 of the pipeline (analyse).
Input:  data/warehouse.duckdb and sql/analysis/*.sql (run in name order: 01, 02, ...)
Output: reports/analysis/<query name>.csv
"""
from pathlib import Path

import duckdb

PROJECT_FOLDER = Path(__file__).resolve().parent.parent
WAREHOUSE = PROJECT_FOLDER / "data" / "warehouse.duckdb"
QUERY_FOLDER = PROJECT_FOLDER / "sql" / "analysis"
REPORT_FOLDER = PROJECT_FOLDER / "reports" / "analysis"


def check(name, result):
    """Stop if a query returned nothing, or compared two periods of different length."""
    if result.shape[0] == 0:
        raise ValueError(f"{name} returned no rows")
    # A growth figure is only fair if both periods hold the same number of weeks.
    week_columns = [column for column in result.columns if column.startswith("weeks_")]
    if len(week_columns) == 2:
        first, second = week_columns
        unequal = result.filter(f"{first} <> {second}").shape[0]
        if unequal:
            raise ValueError(f"{name}: {unequal} rows compare a different number of weeks")


def main():
    if not WAREHOUSE.exists():
        raise FileNotFoundError(f"{WAREHOUSE} not found. Run python pipeline/load.py first.")
    REPORT_FOLDER.mkdir(parents=True, exist_ok=True)
    # read_only: the analysis can never change the warehouse
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        for query_file in sorted(QUERY_FOLDER.glob("*.sql")):
            result = con.sql(query_file.read_text(encoding="utf-8"))
            check(query_file.stem, result)
            print(f"\n{query_file.stem}")
            print(result)
            result.write_csv(str(REPORT_FOLDER / f"{query_file.stem}.csv"))
    print("Saved:", REPORT_FOLDER)


if __name__ == "__main__":
    main()
