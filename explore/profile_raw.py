"""Profile the raw file before cleaning it: what is in it, and what looks wrong.

Part 1 prints the profile. Part 2 turns each finding into a check, so if SAMA changes the data
(new weeks, a new city, a corrected date), running this file again shows exactly what is different.
Every cleaning rule in pipeline/clean.py comes from a finding here.

Run: python explore/profile_raw.py
"""
from pathlib import Path

import pandas as pd

RAW_FILE = Path(__file__).resolve().parent.parent / "data" / "raw" / "pos_transactions.csv"
KEY = ["starting_date", "number_value_change_transactions", "sectors", "city"]  # what makes a row unique
MEASURES = {"Number of Transactions (In Thousand)": "transactions",
            "Value of Transactions (In Thousand SAR)": "value",
            "Number of Transactions Change %": "transactions_change",
            "Value of Transactions Change %": "value_change"}

df = pd.read_csv(RAW_FILE)

# ---------------- Part 1: the profile ----------------

# 1. Size and types
print(df.shape)
print(df.dtypes, "\n")

# 2. What is inside each text column
for col in ["number_value_change_transactions", "sectors", "city"]:
    print(df[col].value_counts(), "\n")

# 3. Missing values per column
print(df.isna().sum(), "\n")

# 4. Dates: first, last, weekdays, and the gap between one week and the next
dates = pd.to_datetime(df["starting_date"])
weeks = pd.Series(dates.unique()).sort_values()
print(weeks.min(), "to", weeks.max(), "|", len(weeks), "weeks")
print(weeks.dt.day_name().value_counts())
print(weeks.diff().dt.days.value_counts())
odd_weeks = weeks[weeks.dt.day_name() != "Sunday"]
print("Not a Sunday:", odd_weeks.dt.strftime("%Y-%m-%d (%A)").tolist(), "\n")

# 5. Three levels hide in two columns: "Total" in city = a national sector row,
#    "Total" in sectors = a city row, "Total" in both = the national total
level = (pd.Series("national", index=df.index)
         .mask(df["sectors"] != "Total", "sector")
         .mask(df["city"] != "Total", "city"))
series = df["city"].where(level == "city", df["sectors"]).where(level != "national", "National")

# One row per week per series, one column per measure. pivot (not pivot_table) stops with an
# error on duplicate rows instead of quietly averaging them.
wide = (df.assign(level=level, series=series, measure=df["number_value_change_transactions"].map(MEASURES))
          .pivot(index=["starting_date", "level", "series"], columns="measure", values="value")
          .reset_index()
          .sort_values(["series", "starting_date"]))
print(wide.groupby("level")["series"].nunique(), "\n")

# 6. The triple-count trap: the same money appears three times (by sector, by city, and as the total)
last = wide[wide["starting_date"] == wide["starting_date"].max()]
national_value = last.loc[last["level"] == "national", "value"].iloc[0]
print(f"Week of {last['starting_date'].iloc[0]}: national value {national_value:,.0f} thousand SAR, "
      f"sum of all rows {last['value'].sum():,.0f} ({last['value'].sum() / national_value:.1f} times)\n")

# 7. The Saturday week in context: does it look like a normal week, just with a wrong date?
national = wide[wide["level"] == "national"].set_index("starting_date")
print(national.loc["2020-06-07":"2020-07-05", ["transactions", "value", "transactions_change", "value_change"]], "\n")

# ---------------- Part 2: the findings as checks ----------------
failures = []


def check(ok, finding):
    """Print PASS or FAIL for one finding, and remember the failures."""
    print(("PASS  " if ok else "FAIL  ") + finding)
    if not ok:
        failures.append(finding)


n_series = wide.groupby("level")["series"].nunique().to_dict()
check(n_series == {"city": 11, "national": 1, "sector": 17},
      f"29 series: 17 sectors, 11 cities and 1 national total (found {n_series})")
check(not df.duplicated(KEY).any(), "no duplicate rows (same week, measure, sector and city)")
check(wide.groupby("series").size().eq(len(weeks)).all(), f"every series has all {len(weeks)} weeks")
check(odd_weeks.dt.strftime("%Y-%m-%d").tolist() == ["2020-06-20"],
      "every week starts on a Sunday except 2020-06-20, a Saturday (clean.py moves it to 2020-06-21)")

first_week = wide["starting_date"] == wide["starting_date"].min()
changes = ["transactions_change", "value_change"]
check(wide.loc[first_week, changes].isna().all().all() and wide.loc[~first_week].notna().all().all(),
      "the only blanks are the Change % of the first week (there is no earlier week to compare with)")
check((wide[["transactions", "value"]] >= 0).all().all(), "no negative numbers")

# Each published number is rounded to the nearest thousand, so a sum of k parts can be off by up to k x 0.5
for lvl, parts in [("sector", 17), ("city", 11)]:
    total = wide[wide["level"] == lvl].groupby("starting_date")[["transactions", "value"]].sum()
    gap = (total - national[["transactions", "value"]]).abs().max().max()
    check(gap <= parts * 0.5,
          f"the {parts} {lvl} rows add up to the national total every week (largest gap {gap:.0f} thousand: rounding)")

for col in ["transactions", "value"]:
    recomputed = (wide[col] / wide.groupby("series")[col].shift() - 1) * 100
    gap = (recomputed - wide[f"{col}_change"]).abs().max()
    check(gap < 1e-6, f"{col} Change % = (this week / last week - 1) x 100, from the published numbers")

if failures:
    raise SystemExit(f"\n{len(failures)} check(s) failed: the raw data is no longer what we profiled.")
print("\nAll checks passed.")
