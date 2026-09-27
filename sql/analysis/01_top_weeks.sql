-- The 3 biggest national weeks of each year, and whether they fall in Ramadan or hold an Eid.
-- RANK() numbers the weeks inside each year (PARTITION BY year), from the biggest down.
WITH ranked AS (
    SELECT
        d.year,
        d.week_start,
        d.ramadan_days,
        d.eid,
        round(f.value_k_sar / 1e6, 2) AS value_bn_sar,
        RANK() OVER (PARTITION BY d.year ORDER BY f.value_k_sar DESC) AS rank_in_year
    FROM fact_weekly_spending AS f
    JOIN dim_date   AS d ON d.date_key = f.date_key
    JOIN dim_series AS s ON s.series_key = f.series_key
    WHERE s.level = 'national'
)
-- Filtered outside the CTE: the rank must see every week of the year first.
SELECT *
FROM ranked
WHERE rank_in_year <= 3
ORDER BY year, rank_in_year;
