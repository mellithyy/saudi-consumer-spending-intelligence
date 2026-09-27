-- 2025 so far against the same weeks of 2024, ranked inside each level.
-- Fair comparison: weeks 1 to 27 of each year (the data ends with 2025's week 27, the week of 6 July),
-- so both periods hold the same number of weeks, one Ramadan, one Eid al-Fitr and one Eid al-Adha.
WITH numbered AS (
    SELECT
        s.level,
        s.series,
        d.year,
        f.value_k_sar,
        row_number() OVER (PARTITION BY f.series_key, d.year ORDER BY d.week_start) AS week_of_year
    FROM fact_weekly_spending AS f
    JOIN dim_date   AS d ON d.date_key = f.date_key
    JOIN dim_series AS s ON s.series_key = f.series_key
    WHERE d.year IN (2024, 2025)
),
same_weeks AS (
    SELECT
        level,
        series,
        count(CASE WHEN year = 2024 THEN 1 END)         AS weeks_2024,
        count(CASE WHEN year = 2025 THEN 1 END)         AS weeks_2025,
        sum(CASE WHEN year = 2024 THEN value_k_sar END) AS value_2024,
        sum(CASE WHEN year = 2025 THEN value_k_sar END) AS value_2025
    FROM numbered
    WHERE week_of_year <= (SELECT max(week_of_year) FROM numbered WHERE year = 2025)
    GROUP BY level, series
)
SELECT
    level,
    series,
    weeks_2024,
    weeks_2025,
    round(value_2024 / 1e6, 2)                    AS value_2024_bn_sar,
    round(value_2025 / 1e6, 2)                    AS value_2025_bn_sar,
    round((value_2025 / value_2024 - 1) * 100, 1) AS growth_pct,
    RANK() OVER (PARTITION BY level ORDER BY value_2025 / value_2024 DESC) AS rank_in_level
FROM same_weeks
ORDER BY level, rank_in_level;
