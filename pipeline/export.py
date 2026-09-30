"""Export the warehouse to Parquet files for Power BI, with one fact table per level.

Stage 5 of the pipeline (export for the dashboard).
Input:  data/warehouse.duckdb
Output: data/powerbi/ dim_date, dim_city, dim_sector, fact_national, fact_city and fact_sector (.parquet)
"""
from pathlib import Path

import duckdb

PROJECT_FOLDER = Path(__file__).resolve().parent.parent
WAREHOUSE = PROJECT_FOLDER / "data" / "warehouse.duckdb"
EXPORT_FOLDER = PROJECT_FOLDER / "data" / "powerbi"

# Power BI has no DuckDB connector, but it reads Parquet. Parquet keeps each column's type (dates stay
# dates, whole numbers stay whole numbers), so Power Query does not have to guess them as it does with CSV.
#
# The warehouse keeps the national total, the sectors and the cities in one fact table with a `level`
# column, and every SQL query filters one level. A report user only clicks, so Power BI gets one fact
# table per level instead: each adds up correctly on its own, so a plain SUM can never count the country
# two or three times. (SAMA publishes no city-by-sector figures, so cities and sectors can't share a row.)
FACTS_BY_LEVEL = """
    SELECT f.date_key, f.series_key, f.transactions_k, f.value_k_sar
    FROM fact_weekly_spending AS f
    JOIN dim_series AS s ON s.series_key = f.series_key
    WHERE s.level = '{level}'
"""
# The dashboard's words for each week, worked out here once, so the report only reads them:
#   week_type      the legend of the weekly charts (an Eid week counts as Eid even if it holds Ramadan days)
#   phase          the words after the biggest week's date ("23 Mar, the last full week of Ramadan")
#   ramadan_phase  the three points of the Ramadan page's line chart, with ramadan_year = the Ramadan they
#                  belong to (the 8 weeks before Ramadan 2025 start on 29 Dec 2024, so the calendar year
#                  would put that week in the wrong Ramadan). Same weeks as sql/analysis/04 and 05; 2020 has
#                  no 8 weeks before its Ramadan (the data starts in May), so it gets none.
#   month_days     the day of the month the week starts, in five groups (salaries are paid around the 27th)
# Every text column has a number column beside it, so Power BI can sort it in this order, not A to Z.
DIM_DATE = """
    WITH ramadans AS (
        SELECT
            year,
            min(week_start)                                     AS first_ramadan_week,
            max(CASE WHEN ramadan_days = 7 THEN week_start END) AS last_full_week
        FROM dim_date
        WHERE ramadan_days > 0
        GROUP BY year
    ),
    weeks_before AS (
        -- the 8 weeks (56 days) before the week that holds Ramadan's first day
        SELECT d.date_key, r.year AS ramadan_year
        FROM dim_date AS d
        JOIN ramadans AS r
          ON d.week_start >= r.first_ramadan_week - 56 AND d.week_start < r.first_ramadan_week
        WHERE r.year >= 2021
    )
    SELECT
        d.*,
        CASE WHEN d.eid IS NOT NULL THEN 'Eid'
             WHEN d.ramadan_days = 7 THEN 'Full Ramadan'
             WHEN d.ramadan_days > 0 THEN 'Part Ramadan'
             ELSE 'Normal' END                                   AS week_type,
        CASE WHEN d.eid IS NOT NULL THEN 4
             WHEN d.ramadan_days = 7 THEN 3
             WHEN d.ramadan_days > 0 THEN 2
             ELSE 1 END                                          AS week_type_order,
        CASE WHEN d.week_start = r.last_full_week THEN 'the last full week of Ramadan'
             WHEN d.eid = 'Eid al-Fitr' THEN 'the Eid al-Fitr week'
             WHEN d.eid = 'Eid al-Adha' THEN 'the Eid al-Adha week'
             WHEN d.ramadan_days > 0 THEN 'a Ramadan week' END   AS phase,
        CASE WHEN b.date_key IS NOT NULL THEN '8 weeks before'
             WHEN d.year >= 2021 AND d.week_start = r.last_full_week THEN 'Last full week'
             WHEN d.year >= 2021 AND d.eid = 'Eid al-Fitr' THEN 'Eid week' END AS ramadan_phase,
        CASE WHEN b.date_key IS NOT NULL THEN 1
             WHEN d.year >= 2021 AND d.week_start = r.last_full_week THEN 2
             WHEN d.year >= 2021 AND d.eid = 'Eid al-Fitr' THEN 3 END AS ramadan_phase_order,
        CASE WHEN b.date_key IS NOT NULL THEN b.ramadan_year
             WHEN d.year >= 2021 AND (d.week_start = r.last_full_week OR d.eid = 'Eid al-Fitr')
             THEN d.year END                                     AS ramadan_year,
        CASE WHEN day(d.week_start) <= 7  THEN '1st to 7th'
             WHEN day(d.week_start) <= 14 THEN '8th to 14th'
             WHEN day(d.week_start) <= 20 THEN '15th to 20th'
             WHEN day(d.week_start) <= 27 THEN '21st to 27th'
             ELSE '28th to 31st' END                             AS month_days,
        CASE WHEN day(d.week_start) <= 7  THEN 1
             WHEN day(d.week_start) <= 14 THEN 2
             WHEN day(d.week_start) <= 20 THEN 3
             WHEN day(d.week_start) <= 27 THEN 4
             ELSE 5 END                                          AS month_days_order
    FROM dim_date AS d
    LEFT JOIN ramadans AS r ON r.year = d.year
    LEFT JOIN weeks_before AS b ON b.date_key = d.date_key
"""
# SAMA's sector names are long for a chart axis ("Construction & Building Materials"). `sector` gets a short
# name for the report, and `sector_full` keeps SAMA's name for tooltips and the About page. Short names use "&",
# never "and": the dashboard lists picked sectors as "Clothing & footwear, Jewelry and Hotels", which "and"
# inside a name would make hard to read.
SHORT_SECTOR_NAMES = {
    "Beverage and Food": "Food & beverages",
    "Clothing and Footwear": "Clothing & footwear",
    "Construction & Building Materials": "Construction materials",
    "Electronic & Electric Devices": "Electronics",
    "Gas Stations": "Gas stations",
    "Miscellaneous Goods and Services": "Misc. goods & services",
    "Other": "Other sectors",  # like "Other cities"; a title saying "spending on other" reads wrong
    "Public Utilities": "Public utilities",
    "Recreation and Culture": "Recreation & culture",
    "Restaurants & Café": "Restaurants & cafés",
    "Telecommunication": "Telecom",
}
SECTOR_NAME = "CASE series " + " ".join(
    f"WHEN '{full}' THEN '{short}'" for full, short in SHORT_SECTOR_NAMES.items()) + " ELSE series END"
EXPORTS = {
    "dim_date": DIM_DATE,
    "dim_city": "SELECT series_key AS city_key, series AS city FROM dim_series WHERE level = 'city'",
    "dim_sector": f"""SELECT series_key AS sector_key, {SECTOR_NAME} AS sector, series AS sector_full
                      FROM dim_series WHERE level = 'sector'""",
    "fact_national": f"SELECT date_key, transactions_k, value_k_sar FROM ({FACTS_BY_LEVEL.format(level='national')})",
    "fact_city": f"""SELECT date_key, series_key AS city_key, transactions_k, value_k_sar
                     FROM ({FACTS_BY_LEVEL.format(level='city')})""",
    "fact_sector": f"""SELECT date_key, series_key AS sector_key, transactions_k, value_k_sar
                       FROM ({FACTS_BY_LEVEL.format(level='sector')})""",
}


def check(con):
    """Stop if the three fact files together lose or add a row or a riyal."""
    files = ", ".join(f"'{(EXPORT_FOLDER / f'{name}.parquet').as_posix()}'"
                      for name in EXPORTS if name.startswith("fact_"))
    in_files = con.sql(f"SELECT count(*), sum(value_k_sar) FROM read_parquet([{files}])").fetchone()
    in_warehouse = con.sql("SELECT count(*), sum(value_k_sar) FROM fact_weekly_spending").fetchone()
    print(f"  fact files together: {in_files[0]:,} rows, {in_files[1]:,} thousand SAR "
          f"(warehouse: {in_warehouse[0]:,} rows, {in_warehouse[1]:,})")
    if in_files != in_warehouse:
        raise ValueError("The fact files do not add up to the warehouse's fact table")


def check_labels(con):
    """Stop if the new week and sector words are not what the dashboard expects."""
    dates = f"'{(EXPORT_FOLDER / 'dim_date.parquet').as_posix()}'"
    # Every Ramadan from 2021 needs exactly 8 weeks before, 1 last full week and 1 Eid week.
    phases = con.sql(f"""SELECT ramadan_year, count(*) FILTER (ramadan_phase = '8 weeks before'),
                                count(*) FILTER (ramadan_phase = 'Last full week'),
                                count(*) FILTER (ramadan_phase = 'Eid week')
                         FROM {dates} WHERE ramadan_year IS NOT NULL GROUP BY 1 ORDER BY 1""").fetchall()
    print("  Ramadan phases (year, weeks before, last full week, Eid week):", phases)
    if [p[0] for p in phases] != [2021, 2022, 2023, 2024, 2025] or any(p[1:] != (8, 1, 1) for p in phases):
        raise ValueError("The Ramadan phases are not 8 + 1 + 1 weeks for each Ramadan from 2021 to 2025")
    sectors = con.sql(f"SELECT count(DISTINCT sector) FROM '{(EXPORT_FOLDER / 'dim_sector.parquet').as_posix()}'").fetchone()[0]
    if sectors != 17:  # two long names shortened to the same word would merge two sectors in the report
        raise ValueError(f"The short sector names give {sectors} sectors, not 17")


def main():
    if not WAREHOUSE.exists():
        raise FileNotFoundError(f"{WAREHOUSE} not found. Run python pipeline/load.py first.")
    EXPORT_FOLDER.mkdir(parents=True, exist_ok=True)
    # Old exports (such as the single fact file of the first version) would be easy to load by mistake.
    for old_file in EXPORT_FOLDER.glob("*.parquet"):
        old_file.unlink()
    # read_only: exporting can never change the warehouse
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        for name, query in EXPORTS.items():
            file = EXPORT_FOLDER / f"{name}.parquet"
            con.execute(f"COPY ({query}) TO '{file.as_posix()}' (FORMAT parquet)")
            # Read each file back: it must hold every row of its query.
            in_query = con.sql(f"SELECT count(*) FROM ({query})").fetchone()[0]
            in_file = con.sql(f"SELECT count(*) FROM '{file.as_posix()}'").fetchone()[0]
            if in_file != in_query:
                raise ValueError(f"{file.name} has {in_file:,} rows, but its query returns {in_query:,}")
            print(f"  {file.name:22s} {in_file:>6,} rows {file.stat().st_size / 1024:>7.1f} KB")
        check(con)
        check_labels(con)
    print("Saved:", EXPORT_FOLDER)


if __name__ == "__main__":
    main()
