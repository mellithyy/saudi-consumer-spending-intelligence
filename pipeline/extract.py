"""Download the weekly point-of-sale (POS) data from the KAPSARC API and save it unchanged.

Stage 1 of the pipeline (extract). The file is saved exactly as the source sent it
(the "raw layer"). Cleaning happens in a later stage, into a different file.
"""
import io
from pathlib import Path

import pandas as pd
import requests

# Source: Saudi Central Bank (SAMA) weekly POS data, published on the KAPSARC Data Portal.
DATASET = "point-of-sale-transactions-by-sector-and-city"
# The export endpoint returns the whole dataset as one CSV file. The /records endpoint gives
# at most 100 rows per request and stops at 10,000 rows, too few for this dataset.
URL = f"https://datasource.kapsarc.org/api/explore/v2.1/catalog/datasets/{DATASET}/exports/csv"
EXPECTED_COLUMNS = ["starting_date", "number_value_change_transactions", "sectors", "city", "value"]

# Paths are built from this file's location (one level up from pipeline/ is the project folder),
# so the script works no matter which folder it is run from.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
RAW_FILE = PROJECT_FOLDER / "data" / "raw" / "pos_transactions.csv"


def download():
    """Return the dataset as CSV bytes. Stops with an HTTPError if the server refuses the request."""
    # The export separates columns with ";" by default, so we ask for "," instead.
    response = requests.get(URL, params={"delimiter": ","}, timeout=120)
    response.raise_for_status()
    return response.content


def check(content):
    """Read the downloaded bytes in memory and stop if they are not the dataset we expect."""
    df = pd.read_csv(io.BytesIO(content))
    if list(df.columns) != EXPECTED_COLUMNS:
        raise ValueError(f"Unexpected columns: {list(df.columns)}")
    if len(df) == 0:
        raise ValueError("The download has no rows.")
    return df


def main():
    print("Downloading", DATASET, "...")
    content = download()
    # Check before saving, so a bad download never overwrites a good file.
    df = check(content)

    RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
    RAW_FILE.write_bytes(content)  # saved byte for byte, with no changes

    print("Saved:", RAW_FILE)
    print("Rows:", len(df), "| Size:", round(len(content) / 1_000_000, 1), "MB")
    print("Weeks:", df["starting_date"].min(), "to", df["starting_date"].max())


# Run main() only when this file is run directly (python pipeline/extract.py),
# not when another file imports download() or check().
if __name__ == "__main__":
    main()
