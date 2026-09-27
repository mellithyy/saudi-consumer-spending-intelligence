-- How much each series changes in Ramadan, against the 8 weeks just before it (Ramadans of 2021 to 2025).
-- Fair comparison: the 8 weeks before hold two month ends (paydays), about the same share as the 3 or 4
-- full Ramadan weeks. The week holding Ramadan's first day is in neither group (it mixes the stocking-up
-- days with Ramadan days). 2020 is left out: the data starts in the middle of that Ramadan.
WITH ramadans AS (
    -- Per year: the first week with a Ramadan day, and the last full Ramadan week (just before Eid).
    SELECT
        year,
        min(week_start)                                     AS first_ramadan_week,
        max(CASE WHEN ramadan_days = 7 THEN week_start END) AS last_full_week
    FROM dim_date
    WHERE ramadan_days > 0 AND year >= 2021
    GROUP BY year
),
per_year AS (
    SELECT
        s.level,
        s.series,
        r.year,
        avg(CASE WHEN d.week_start < r.first_ramadan_week THEN f.value_k_sar END)  AS before_avg,
        avg(CASE WHEN d.ramadan_days = 7 THEN f.value_k_sar END)                  AS ramadan_avg,
        max(CASE WHEN d.week_start = r.last_full_week THEN f.value_k_sar END)     AS last_full_week_value
    FROM fact_weekly_spending AS f
    JOIN dim_date   AS d ON d.date_key = f.date_key
    JOIN dim_series AS s ON s.series_key = f.series_key
    -- From 8 weeks (56 days) before Ramadan's first week to its last full week
    JOIN ramadans   AS r ON d.week_start BETWEEN r.first_ramadan_week - 56 AND r.last_full_week
    GROUP BY s.level, s.series, r.year
),
summary AS (
    SELECT
        level,
        series,
        count(*)                                   AS ramadans,
        avg(ramadan_avg / before_avg - 1)          AS ramadan_change,
        min(ramadan_avg / before_avg - 1)          AS lowest_year,
        max(ramadan_avg / before_avg - 1)          AS highest_year,
        avg(last_full_week_value / before_avg - 1) AS last_week_change
    FROM per_year
    GROUP BY level, series
)
SELECT
    level,
    series,
    ramadans,
    round(ramadan_change * 100, 1)   AS ramadan_vs_before_pct,
    round(lowest_year * 100, 1)      AS lowest_year_pct,
    round(highest_year * 100, 1)     AS highest_year_pct,
    round(last_week_change * 100, 1) AS last_week_before_eid_vs_before_pct,
    RANK() OVER (PARTITION BY level ORDER BY ramadan_change DESC) AS rank_in_level
FROM summary
ORDER BY level, rank_in_level;
