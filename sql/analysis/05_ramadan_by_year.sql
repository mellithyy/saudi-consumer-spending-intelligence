-- National spending in each Ramadan (2021 to 2025) and in the Eid al-Fitr week, against the 8 weeks before.
-- Same fair comparison as 04_ramadan_effect.sql, one row per year for the national series.
WITH ramadans AS (
    SELECT
        year,
        min(week_start)                                     AS first_ramadan_week,
        max(CASE WHEN ramadan_days = 7 THEN week_start END) AS last_full_week,
        max(week_start)                                     AS last_ramadan_week
    FROM dim_date
    WHERE ramadan_days > 0 AND year >= 2021
    GROUP BY year
),
per_year AS (
    SELECT
        r.year,
        max(CASE WHEN d.eid = 'Eid al-Fitr' THEN d.week_start END)                 AS eid_week,
        max(CASE WHEN d.eid = 'Eid al-Fitr' THEN d.ramadan_days END)               AS ramadan_days_in_eid_week,
        avg(CASE WHEN d.week_start < r.first_ramadan_week THEN f.value_k_sar END)  AS before_avg,
        avg(CASE WHEN d.ramadan_days = 7 THEN f.value_k_sar END)                  AS ramadan_avg,
        max(CASE WHEN d.week_start = r.last_full_week THEN f.value_k_sar END)     AS last_full_week_value,
        max(CASE WHEN d.eid = 'Eid al-Fitr' THEN f.value_k_sar END)               AS eid_week_value
    FROM fact_weekly_spending AS f
    JOIN dim_date   AS d ON d.date_key = f.date_key
    JOIN dim_series AS s ON s.series_key = f.series_key
    -- From 8 weeks (56 days) before Ramadan's first week to the week after its last week (the Eid week)
    JOIN ramadans   AS r ON d.week_start BETWEEN r.first_ramadan_week - 56 AND r.last_ramadan_week + 7
    WHERE s.level = 'national'
    GROUP BY r.year
)
SELECT
    year,
    eid_week,
    ramadan_days_in_eid_week,
    round(before_avg / 1e6, 2)                          AS before_bn_sar,
    round(ramadan_avg / 1e6, 2)                         AS ramadan_week_bn_sar,
    round((ramadan_avg / before_avg - 1) * 100, 1)          AS ramadan_vs_before_pct,
    round((last_full_week_value / before_avg - 1) * 100, 1) AS last_week_before_eid_vs_before_pct,
    round((eid_week_value / before_avg - 1) * 100, 1)       AS eid_week_vs_before_pct
FROM per_year
ORDER BY year;
