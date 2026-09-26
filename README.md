# Saudi Consumer Spending Intelligence

Weekly card spending in Saudi Arabia, by city and by sector, from May 2020 to July 2025.

**Status: in progress.** Stages 1 and 2 of 7 (extraction, cleaning and data-quality checks) are done.

## Data
- Source: Saudi Central Bank (SAMA), weekly point-of-sale (POS) transactions, published on the
  [KAPSARC Data Portal](https://datasource.kapsarc.org/explore/assets/point-of-sale-transactions-by-sector-and-city/). Licence: Public Domain.
- 31,262 rows covering 270 weeks (10 May 2020 to 6 July 2025).
- Measures: number of transactions (thousands) and value (thousand SAR), plus the week-on-week change % for each.
- Three levels in one table: the national total, 17 sectors (national only) and 11 cities (all sectors combined),
  including Khobar, Dammam, Riyadh and Jeddah. There is no city-by-sector breakdown.

## Data quality
[`explore/profile_raw.py`](explore/profile_raw.py) profiles the raw file and turns each finding into a check.
[`pipeline/clean.py`](pipeline/clean.py) applies the fixes below and checks the result before saving it.

| What the profile found | What the clean table does |
|---|---|
| The national total, the 17 sectors and the 11 cities are stored together, and each group adds up to the same money, so adding every row triples the total | A `level` column (national, sector, city). Totals are only taken within one level |
| One week is dated Saturday 20 June 2020; every other week starts on a Sunday | Moved to Sunday 21 June. SAMA's date is kept in `source_date` |
| The first week (10 May 2020) has no Change % | Left blank, not 0 |
| Sectors and cities add up to the national total within 4 thousand, because each number is published rounded to the nearest thousand | Checked every week, allowing 0.5 thousand per part |
| SAMA's Change % equals (this week / last week - 1) x 100 | Checked on every row |

Output: `data/clean/pos_weekly.csv`, one row per week per series (29 series x 270 weeks = 7,830 rows).
The script checks the table before saving and stops with a list of problems if any rule fails.

## Plan
1. Extract: download the data from the API, with checks ✅
2. Clean the data and run data-quality checks ✅
3. Load it into a SQL warehouse (star schema)
4. Analyse seasonality (Ramadan, Eid, Riyadh Season), city trends and sector growth
5. Build a Power BI dashboard and an Excel management report
6. Forecast the next quarter
7. Automate the refresh and publish

## Run it (Windows)
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python pipeline/extract.py
.venv\Scripts\python pipeline/clean.py
```
The raw file is saved to `data/raw/pos_transactions.csv` and the clean table to `data/clean/pos_weekly.csv`.
`.venv\Scripts\python explore/profile_raw.py` prints the data profile and re-checks every finding on the raw file.

## Author
Mohamed Ellithy · [LinkedIn](https://www.linkedin.com/in/mohamed-el-lithy/)
