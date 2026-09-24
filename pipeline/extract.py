"""Download the weekly point-of-sale (POS) data from the KAPSARC API and save it unchanged."""
import io
from pathlib import Path

import pandas as pd
import requests

DATASET = "point-of-sale-transactions-by-sector-and-city"
URL = f"https://datasource.kapsarc.org/api/explore/v2.1/catalog/datasets/{DATASET}/exports/csv"
EXPECTED_COLUMNS = ["starting_date", "number_value_change_transactions", "sectors", "city", "value"]

PROJECT_FOLDER = Path(__file__).resolve().parent.parent
RAW_FILE = PROJECT_FOLDER / "data" / "raw" / "pos_transactions.csv"


def download():
    response = requests.get(URL, params={"delimiter": ","}, timeout=120)
    response.raise_for_status()
    return response.content


def check(content):
    df = pd.read_csv(io.BytesIO(content))
    if list(df.columns) != EXPECTED_COLUMNS:
        raise ValueError(f"Unexpected columns: {list(df.columns)}")
    if len(df) == 0:
        raise ValueError("The download has no rows.")
    return df


def main():
    print("Downloading", DATASET, "...")
    content = download()
    df = check(content)

    RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
    RAW_FILE.write_bytes(content)

    print("Saved:", RAW_FILE)
    print("Rows:", len(df), "| Size:", round(len(content) / 1_000_000, 1), "MB")
    print("Weeks:", df["starting_date"].min(), "to", df["starting_date"].max())


if __name__ == "__main__":
    main()