-- The star schema: two dimensions and one fact table.
-- The keys are rules the database enforces: no duplicate keys, and no fact row
-- that points to a week or a series that does not exist.

CREATE TABLE dim_date (
    date_key     INTEGER PRIMARY KEY,   -- the week as a number, e.g. 20250706
    week_start   DATE    NOT NULL,      -- the Sunday the week starts
    source_date  DATE    NOT NULL,      -- the date as SAMA published it (differs once: 2020-06-20)
    year         INTEGER NOT NULL,
    quarter      INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    week_of_year INTEGER NOT NULL,      -- 1 for the year's first Sunday, up to 53; compares the same weeks across years
    ramadan_days INTEGER NOT NULL,      -- how many of the week's 7 days are in Ramadan (0 to 7)
    eid          VARCHAR                -- 'Eid al-Fitr', 'Eid al-Adha', or empty (NULL) for other weeks
);

CREATE TABLE dim_series (
    series_key   INTEGER PRIMARY KEY,   -- 1 = National, then the sectors, then the cities
    series       VARCHAR NOT NULL,      -- e.g. Khobar, Hotels
    level        VARCHAR NOT NULL       -- national, sector or city
);

CREATE TABLE fact_weekly_spending (
    date_key        INTEGER NOT NULL REFERENCES dim_date (date_key),
    series_key      INTEGER NOT NULL REFERENCES dim_series (series_key),
    transactions_k  BIGINT  NOT NULL,   -- thousands of transactions
    value_k_sar     BIGINT  NOT NULL,   -- thousand SAR
    PRIMARY KEY (date_key, series_key)  -- the grain: one row per week per series
);
