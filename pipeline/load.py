"""Load the clean table into a DuckDB warehouse (a star schema), check it, and only then keep it.

Stage 3 of the pipeline (load).
Input:  data/clean/pos_weekly.csv, data/reference/islamic_calendar.csv and sql/schema.sql
Output: data/warehouse.duckdb with dim_date, dim_series and fact_weekly_spending
"""
from pathlib import Path

import duckdb

PROJECT_FOLDER = Path(__file__).resolve().parent.parent
CLEAN_FILE = PROJECT_FOLDER / "data" / "clean" / "pos_weekly.csv"
# Typed by hand from the official Umm al-Qura calendar (ummulqura.org.sa, KACST); for 1441-1446 it
# matches the dates the Supreme Court announced after sighting the moon. Checks catch impossible dates,
# not a wrong date that is still possible, so re-check a new row against the official calendar.
CALENDAR_FILE = PROJECT_FOLDER / "data" / "reference" / "islamic_calendar.csv"
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

    # Step 1b. The Ramadan and Eid dates (one row per Hijri year), checked before anything uses them.
    con.execute(f"CREATE TEMP TABLE calendar AS SELECT * FROM read_csv('{CALENDAR_FILE.as_posix()}')")
    check_calendar(con)

    # Step 2. One row per week. The key is the date written as a number: 2025-07-06 -> 20250706.
    # Plus how many of the week's days fall in Ramadan, and which Eid (if any) falls in it.
    con.execute("""
        INSERT INTO dim_date
        WITH
        weeks AS (      -- one row per week, with its last day (the Saturday)
            SELECT DISTINCT week_start, week_start + 6 AS week_end, source_date
            FROM staging
        ),
        ramadan AS (    -- each Ramadan as its first and last day
            SELECT ramadan_start AS first_day, eid_al_fitr - 1 AS last_day
            FROM calendar
        ),
        eid AS (        -- the two Eid columns stacked into one list of days
            SELECT eid_al_fitr AS eid_day, 'Eid al-Fitr' AS eid FROM calendar
            UNION ALL
            SELECT eid_al_adha, 'Eid al-Adha' FROM calendar
        )
        SELECT
            CAST(strftime(w.week_start, '%Y%m%d') AS INTEGER),
            w.week_start,
            w.source_date,
            year(w.week_start),
            quarter(w.week_start),
            month(w.week_start),
            -- The shared days run from the later start to the earlier end. CASE, not coalesce: DuckDB's
            -- greatest() and least() skip a NULL, so a week with no Ramadan would get 7 days, not 0.
            CASE WHEN r.first_day IS NULL THEN 0
                 ELSE least(w.week_end, r.last_day) - greatest(w.week_start, r.first_day) + 1
            END,
            e.eid
        FROM weeks AS w
        -- LEFT JOIN keeps every week; a Ramadan or an Eid is attached only where it falls in the week.
        LEFT JOIN ramadan AS r ON r.first_day <= w.week_end AND r.last_day >= w.week_start
        LEFT JOIN eid     AS e ON e.eid_day BETWEEN w.week_start AND w.week_end
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


def check_calendar(con):
    """Stop if the calendar has a typing mistake, or if the data has grown past it."""
    # A date typed in another format (30/03/2025) makes DuckDB read the whole column as text, with no
    # error. Stop at once: the day counts below only work on real dates.
    not_dates = con.sql("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'calendar' AND column_name <> 'hijri_year' AND data_type <> 'DATE'
    """).fetchall()
    if not_dates:
        raise ValueError(f"Write every calendar date as YYYY-MM-DD. Read as text instead: {not_dates}")

    problems = []
    # Two rules of the Hijri calendar: Ramadan has 29 or 30 days, and 1 Shawwal to 10 Dhu al-Hijjah is
    # Shawwal (29 or 30) + Dhu al-Qadah (29 or 30) + 9 days. A real date typed wrong breaks one of them.
    wrong = con.sql("""
        SELECT hijri_year, eid_al_fitr - ramadan_start, eid_al_adha - eid_al_fitr
        FROM calendar
        WHERE eid_al_fitr - ramadan_start NOT IN (29, 30)
           OR eid_al_adha - eid_al_fitr NOT BETWEEN 67 AND 69
    """).fetchall()
    for year, ramadan_length, fitr_to_adha in wrong:
        problems.append(f"{year}: Ramadan is {ramadan_length} days (29 or 30 expected), "
                        f"Eid al-Fitr to Eid al-Adha is {fitr_to_adha} days (67 to 69 expected)")

    # A missing year gives no error, only weeks with 0 Ramadan days. The data grows at the end, so check
    # the end: a Hijri year is 354 or 355 days, so the next Ramadan starts at least 354 days later.
    next_ramadan, data_end = con.sql("""
        SELECT (SELECT max(ramadan_start) FROM calendar) + 354,
               (SELECT max(week_start) FROM staging) + 6
    """).fetchone()
    if data_end >= next_ramadan:
        problems.append(f"The data runs to {data_end}, past the calendar: add the next Hijri year "
                        f"(its Ramadan starts on or after {next_ramadan})")

    if problems:
        raise ValueError("The calendar file has problems:\n- " + "\n- ".join(problems))


def check(con):
    """Step 5. Stop, listing every broken rule, if the warehouse does not match its sources."""
    problems = []
    # Each pair: the same number counted in the warehouse and in its source (the clean file or the calendar).
    same = {
        # A JOIN silently drops rows it cannot match, so the fact must keep every clean row.
        "fact rows": ("SELECT count(*) FROM fact_weekly_spending", "SELECT count(*) FROM staging"),
        "weeks": ("SELECT count(*) FROM dim_date", "SELECT count(DISTINCT week_start) FROM staging"),
        "series": ("SELECT count(*) FROM dim_series", "SELECT count(DISTINCT series) FROM staging"),
        # Reconciliation: not one riyal or transaction lost or added on the way.
        "total value": ("SELECT sum(value_k_sar) FROM fact_weekly_spending", "SELECT sum(value_k_sar) FROM staging"),
        "total transactions": ("SELECT sum(transactions_k) FROM fact_weekly_spending",
                               "SELECT sum(transactions_k) FROM staging"),
        # The calendar counted a second way: list every Ramadan day, keep the days the data covers.
        # A week-by-week count that is off by a day (or gives 7 instead of 0) makes a different total.
        "Ramadan days": ("SELECT sum(ramadan_days) FROM dim_date", """
            SELECT count(*)
            FROM (SELECT unnest(generate_series(ramadan_start, eid_al_fitr - 1, INTERVAL 1 DAY)) AS day
                  FROM calendar)
            WHERE day BETWEEN (SELECT min(week_start) FROM staging) AND (SELECT max(week_start) + 6 FROM staging)
        """),
        # count(eid) skips the empty (NULL) weeks, so it counts only the weeks with an Eid.
        "Eid weeks": ("SELECT count(eid) FROM dim_date", """
            SELECT count(*)
            FROM (SELECT eid_al_fitr AS day FROM calendar UNION ALL SELECT eid_al_adha FROM calendar)
            WHERE day BETWEEN (SELECT min(week_start) FROM staging) AND (SELECT max(week_start) + 6 FROM staging)
        """),
    }
    for name, (warehouse_sql, source_sql) in same.items():
        in_warehouse = con.sql(warehouse_sql).fetchone()[0]
        in_source = con.sql(source_sql).fetchone()[0]
        print(f"  {name:20s} warehouse {in_warehouse:>15,}   source {in_source:>15,}")
        if in_warehouse != in_source:
            problems.append(f"{name}: {in_warehouse:,} in the warehouse, {in_source:,} in the source")
    if problems:
        raise ValueError("The warehouse does not match its sources:\n- " + "\n- ".join(problems))


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