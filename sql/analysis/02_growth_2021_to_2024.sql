-- Growth from 2021 to 2024 for every series, ranked inside its level (cities with cities, sectors
-- with sectors; never mixed, because each level adds up to the same national total).
-- Fair comparison: only full years (2020 starts in May, 2025 ends in July), and the AVERAGE week
-- instead of the total, because 2023 has 53 weeks and the other years 52.
WITH yearly AS (
    SELECT
        s.level,
        s.series,
        d.year,
        avg(f.value_k_sar) AS avg_week_k_sar
    FROM fact_weekly_spending AS f
    JOIN dim_date   AS d ON d.date_key = f.date_key
    JOIN dim_series AS s ON s.series_key = f.series_key
    WHERE d.year BETWEEN 2021 AND 2024
    GROUP BY s.level, s.series, d.year
),
first_and_last AS (
    -- Conditional aggregation: CASE keeps one year's row, so each year becomes its own column.
    SELECT
        level,
        series,
        max(CASE WHEN year = 2021 THEN avg_week_k_sar END) AS avg_week_2021,
        max(CASE WHEN year = 2024 THEN avg_week_k_sar END) AS avg_week_2024
    FROM yearly
    GROUP BY level, series
)
SELECT
    level,
    series,
    round(avg_week_2021 / 1e3, 1)                       AS avg_week_2021_m_sar,
    round(avg_week_2024 / 1e3, 1)                       AS avg_week_2024_m_sar,
    round((avg_week_2024 / avg_week_2021 - 1) * 100, 1) AS growth_pct,
    RANK() OVER (PARTITION BY level ORDER BY avg_week_2024 / avg_week_2021 DESC) AS rank_in_level
FROM first_and_last
ORDER BY level, rank_in_level;
