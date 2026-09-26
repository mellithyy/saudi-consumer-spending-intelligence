"""Load the clean table into a DuckDB warehouse (a star schema), check it, and only then keep it.

Stage 3 of the pipeline (load).
Input:  data/clean/pos_weekly.csv and sql/schema.sql
Output: data/warehouse.duckdb with dim_date, dim_series and fact_weekly_spending
"""
from pathlib import Path

import duckdb

PROJECT_FOLDER = Path(__file__).resolve().parent.parent
CLEAN_FILE = PROJECT_FOLDER / "data" / "clean" / "pos_weekly.csv"
SCHEMA_FILE = PROJECT_FOLDER / "sql" / "schema.sql"
WAREHOUSE = PROJECT_FOLDER / "data" / "warehouse.duckdb"
# Built under a temporary name first, so a failed run never replaces a good warehouse.
NEW_WAREHOUSE = PROJECT_FOLDER / "data" / "warehouse.new.duckdb"


def build(con):
    """Create the empty tables from schema.sql, then fill them from the clean file."""
    con.execute(SCHEMA_FILE.read_text(encoding="utf-8"))

    # Staging: the clean file as a temporary table (not saved in the warehouse file),
    # so every step below reads it with plain SQL.
    con.execute(f"CREATE TEMP TABLE staging AS SELECT * FROM read_csv('{CLEAN_FILE.as_posix()}')")

    # Step 2. One row per week. The key is the date written as a number: 2025-07-06 -> 20250706.
    con.execute("""
        INSERT INTO dim_date
        SELECT DISTINCT
            CAST(strftime(week_start, '%Y%m%d') AS INTEGER),
            week_start,
            source_date,
            year(week_start),
            quarter(week_start),
            month(week_start)
        FROM staging
    """)

    # Step 3. One row per series, numbered 1, 2, 3 ... in a fixed order: National, then sectors, then cities.
    con.execute("""
        INSERT INTO dim_series
        SELECT
            row_number() OVER (ORDER BY level_order, series),
            series,
            level
        FROM (
            SELECT DISTINCT
                series,
                level,
                CASE level WHEN 'national' THEN 1 WHEN 'sector' THEN 2 ELSE 3 END AS level_order
            FROM staging
        )
    """)

    # Step 4. The facts: swap the week and the series name for their keys, keep only the additive numbers.
    con.execute("""
        INSERT INTO fact_weekly_spending
        SELECT d.date_key, s.series_key, st.transactions_k, st.value_k_sar
        FROM staging AS st
        JOIN dim_date   AS d ON d.week_start = st.week_start
        JOIN dim_series AS s ON s.series = st.series AND s.level = st.level
    """)


def check(con):
    """Step 5. Stop, listing every broken rule, if the warehouse does not match the clean file."""
    problems = []
    # Each pair: the same number counted in the warehouse and in the clean file (staging).
    same = {
        # A JOIN silently drops rows it cannot match, so the fact must keep every clean row.
        "fact rows": ("SELECT count(*) FROM fact_weekly_spending", "SELECT count(*) FROM staging"),
        "weeks": ("SELECT count(*) FROM dim_date", "SELECT count(DISTINCT week_start) FROM staging"),
        "series": ("SELECT count(*) FROM dim_series", "SELECT count(DISTINCT series) FROM staging"),
        # Reconciliation: not one riyal or transaction lost or added on the way.
        "total value": ("SELECT sum(value_k_sar) FROM fact_weekly_spending", "SELECT sum(value_k_sar) FROM staging"),
        "total transactions": ("SELECT sum(transactions_k) FROM fact_weekly_spending",
                               "SELECT sum(transactions_k) FROM staging"),
    }
    for name, (warehouse_sql, clean_sql) in same.items():
        in_warehouse = con.sql(warehouse_sql).fetchone()[0]
        in_clean = con.sql(clean_sql).fetchone()[0]
        print(f"  {name:20s} warehouse {in_warehouse:>15,}   clean file {in_clean:>15,}")
        if in_warehouse != in_clean:
            problems.append(f"{name}: {in_warehouse:,} in the warehouse, {in_clean:,} in the clean file")
    if problems:
        raise ValueError("The warehouse does not match the clean file:\n- " + "\n- ".join(problems))


def main():
    if not CLEAN_FILE.exists():
        raise FileNotFoundError(f"{CLEAN_FILE} not found. Run python pipeline/clean.py first.")
    NEW_WAREHOUSE.unlink(missing_ok=True)  # a leftover from a run that failed
    with duckdb.connect(str(NEW_WAREHOUSE)) as con:
        build(con)
        check(con)  # if a check fails, the script stops here and the old warehouse stays
    NEW_WAREHOUSE.replace(WAREHOUSE)  # only now does the new warehouse replace the old one
    print("Saved:", WAREHOUSE)


if __name__ == "__main__":
    main()