import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

from .exceptions import EmptyDataFrameError


def read_csv(file_path: str) -> pd.DataFrame:
    """Read CSV file into DataFrame from the given path."""
    try:
        return pd.read_csv(file_path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def get_utc_now() -> str:
    """Return the ISO 8601 UTC timestamp string."""
    return datetime.now(tz=timezone.utc).isoformat() + "Z"


def diff_hours(first: datetime, last: datetime) -> float:
    """Return the difference in hours between first-last datetimes."""
    diff = last - first
    days, seconds = diff.days, diff.seconds

    return (days * 24) + (seconds / 3600)


def handle_sigterm_interrupt(*args):
    """Raise KeyboardInterrupt for the given signal."""
    raise KeyboardInterrupt()


def remove_duplicate_listings(df: pd.DataFrame) -> pd.DataFrame:
    """Return the DataFrame with duplicate listings removed."""
    df_no_dupes = df.drop_duplicates(
        subset=["item_id"], keep="last", ignore_index=True, inplace=False
    )

    if df_no_dupes is not None:
        return df_no_dupes
    else:
        raise EmptyDataFrameError()


def save_listings(listings_df: pd.DataFrame, file_path: str):
    """Save the DataFrame of listings to the given file path."""
    path = Path(file_path)

    # make the parent directories if they do not exist
    dir_path = path.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    listings_df.to_csv(file_path, index=False)


def format_text(text: str) -> str:
    """Return the given text with excess whitespace trimmed to singular space."""

    def remove_multi_whitespace(text: str) -> str:
        return " ".join(text.split())

    fmt = remove_multi_whitespace(text)

    return fmt
