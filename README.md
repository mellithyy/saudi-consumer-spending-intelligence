# Saudi Consumer Spending Intelligence

Weekly card spending in Saudi Arabia, by city and by sector, from May 2020 to July 2025.

**Status: in progress.** Stage 1 of 7 (data extraction) is done.

## Data
- Source: Saudi Central Bank (SAMA), weekly point-of-sale (POS) transactions, published on the
  [KAPSARC Data Portal](https://datasource.kapsarc.org/explore/assets/point-of-sale-transactions-by-sector-and-city/). Licence: Public Domain.
- 31,262 rows covering 270 weeks (10 May 2020 to 6 July 2025).
- Measures: number of transactions (thousands) and value (thousand SAR), plus the week-on-week change % for each.
- Two levels: 17 sectors at national level, and 11 cities (including Khobar, Dammam, Riyadh and Jeddah) at total level.
  There is no city-by-sector breakdown.

## Plan
1. Extract: download the data from the API, with checks ✅
2. Clean the data and run data-quality checks
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
```
The raw file is saved to `data/raw/pos_transactions.csv`.

## Author
Mohamed Ellithy · [LinkedIn](https://www.linkedin.com/in/mohamed-el-lithy/)
