"""Turn the raw SAMA file into one clean weekly table, check it, and only then save it.

Stage 2 of the pipeline (clean). Every rule below comes from a finding in explore/profile_raw.py.
Input:  data/raw/pos_transactions.csv  4 rows per week per series, one per measure ("long" format)
Output: data/clean/pos_weekly.csv      1 row per week per series, one column per measure (7,830 rows)
"""
from pathlib import Path

import pandas as pd

PROJECT_FOLDER = Path(__file__).resolve().parent.parent
RAW_FILE = PROJECT_FOLDER / "data" / "raw" / "pos_transactions.csv"
CLEAN_FILE = PROJECT_FOLDER / "data" / "clean" / "pos_weekly.csv"

# Short column names that carry the unit, so nobody has to guess what a number means.
MEASURES = {"Number of Transactions (In Thousand)": "transactions_k",
            "Value of Transactions (In Thousand SAR)": "value_k_sar",
            "Number of Transactions Change %": "transactions_change_pct",
            "Value of Transactions Change %": "value_change_pct"}
CHANGE_OF = {"transactions_k": "transactions_change_pct", "value_k_sar": "value_change_pct"}
COLUMNS = ["week_start", "source_date", "level", "series", *MEASURES.values()]
EXPECTED_SERIES = {"national": 1, "sector": 17, "city": 11}

# SAMA weeks start on Sunday. One week is dated Saturday 2020-06-20, but its numbers are a normal
# week (SAMA compares it with the week of 14 June), so only the label is wrong. A NEW odd date is not
# fixed automatically: check() stops the script, so a person looks at it and decides.
DATE_FIXES = {"2020-06-20": "2020-06-21"}


def clean(raw):
    """Return one row per week per series, with a level column, from the raw long table."""
    df = raw.copy()

    # Three levels hide in two columns ("Total" means "all of them"). The sector rows, the city rows
    # and the national row each add up to the same money, so a level column keeps them apart and
    # stops anyone adding them together (the triple-count trap).
    df["level"] = "national"
    df.loc[df["sectors"] != "Total", "level"] = "sector"
    df.loc[df["city"] != "Total", "level"] = "city"
    df["series"] = df["sectors"]
    df.loc[df["level"] == "city", "series"] = df["city"].str.title().replace({"Other": "Other cities"})
    df.loc[df["level"] == "national", "series"] = "National"

    # Long to wide: the 4 measure rows of a week become 4 columns. pivot (not pivot_table) stops
    # with an error on duplicate rows instead of quietly averaging them.
    df["measure"] = df["number_value_change_transactions"].map(MEASURES)
    wide = df.pivot(index=["starting_date", "level", "series"], columns="measure", values="value").reset_index()
    wide.columns.name = None

    wide["source_date"] = pd.to_datetime(wide["starting_date"])  # kept, so every fix stays visible
    wide["week_start"] = pd.to_datetime(wide["starting_date"].replace(DATE_FIXES))
    # Whole thousands. "Int64" (capital I) allows blanks, so a missing number reaches check()
    # and gets a clear message instead of crashing here.
    wide[["transactions_k", "value_k_sar"]] = wide[["transactions_k", "value_k_sar"]].astype("Int64")
    wide["level"] = pd.Categorical(wide["level"], ["national", "sector", "city"], ordered=True)
    return wide.sort_values(["level", "series", "week_start"])[COLUMNS].reset_index(drop=True)


def check(df):
    """Stop, listing every broken rule, if the clean table is not what we promise to save."""
    if list(df.columns) != COLUMNS:
        raise ValueError(f"Unexpected columns: {list(df.columns)}")
    problems = []

    found = df.groupby("level", observed=True)["series"].nunique().to_dict()
    if found != EXPECTED_SERIES:
        problems.append(f"series per level {found}, expected {EXPECTED_SERIES}")

    weeks = pd.Series(sorted(df["week_start"].unique()))
    if df.duplicated(["week_start", "series"]).any() or len(df) != df["series"].nunique() * len(weeks):
        problems.append("not exactly one row per week per series")
    if (weeks.dt.dayofweek != 6).any():  # Monday = 0 ... Sunday = 6
        problems.append(f"weeks not starting on a Sunday: {weeks[weeks.dt.dayofweek != 6].dt.date.tolist()}")
    if (weeks.diff().dropna() != pd.Timedelta(days=7)).any():
        problems.append("weeks that are not exactly 7 days apart")

    # The first week has no earlier week, so its Change % must be blank (never 0, which would claim "no change").
    changes = list(CHANGE_OF.values())
    first_week = df["week_start"] == weeks.min()
    if df.drop(columns=changes).isna().any().any() or df.loc[~first_week, changes].isna().any().any():
        problems.append("blank values outside the first week's Change %")
    if (df[["transactions_k", "value_k_sar"]] < 0).any().any():
        problems.append("negative numbers")

    # Each published number is rounded to the nearest thousand, so k parts can miss the total by k x 0.5.
    national = df[df["level"] == "national"].set_index("week_start")[list(CHANGE_OF)]
    for level in ["sector", "city"]:
        parts = df[df["level"] == level].groupby("week_start")[list(CHANGE_OF)].sum()
        gap = (parts - national).abs().max().max()
        if gap > EXPECTED_SERIES[level] * 0.5:
            problems.append(f"the {level} rows miss the national total by up to {gap:,.0f} thousand")

    # SAMA's Change % must match our own calculation from its published numbers.
    ordered = df.sort_values(["series", "week_start"])
    for col, change in CHANGE_OF.items():
        recomputed = (ordered[col] / ordered.groupby("series")[col].shift() - 1) * 100
        gap = (recomputed - ordered[change]).abs().max()
        if gap > 1e-6:
            problems.append(f"{change} differs from our own calculation by up to {gap:.4f} points")

    if problems:
        raise ValueError("The clean table breaks these rules:\n- " + "\n- ".join(problems))


def main():
    if not RAW_FILE.exists():
        raise FileNotFoundError(f"{RAW_FILE} not found. Run python pipeline/extract.py first.")
    df = clean(pd.read_csv(RAW_FILE))
    # Check before saving, so a bad table never overwrites a good file.
    check(df)

    CLEAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CLEAN_FILE, index=False)

    print("Saved:", CLEAN_FILE)
    print("Rows:", len(df), "|", df["series"].nunique(), "series x", df["week_start"].nunique(), "weeks")
    print("Weeks:", df["week_start"].min().date(), "to", df["week_start"].max().date())


# Run main() only when this file is run directly (python pipeline/clean.py),
# not when another file imports clean() or check().
if __name__ == "__main__":
    main()
