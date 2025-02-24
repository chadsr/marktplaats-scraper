import os
import logging
import signal
import argparse
from typing import NamedTuple
import pandas as pd
from pyvirtualdisplay.display import Display
from tqdm import tqdm
from datetime import datetime

from .utils import (
    diff_hours,
    handle_sigterm_interrupt,
    read_csv,
    remove_duplicate_listings,
    save_listings,
    get_utc_now,
)
from .display import has_display, get_virtual_display
from .exceptions import (
    CategoriesError,
    NotFoundError,
    ListingsError,
    ListingsInterrupt,
)
from .mpscraper import MpScraper
from .listing import Listing

ENV_PREFIX = "MP_"
ENV_LIMIT = f"{ENV_PREFIX}LIMIT"
ENV_HEADLESS = f"{ENV_PREFIX}HEADLESS"
ENV_TIMEOUT_SECONDS = f"{ENV_PREFIX}TIMEOUT_SECONDS"
ENV_RECRAWL_HOURS = f"{ENV_PREFIX}RECRAWL_HOURS"
ENV_USE_PROXIES = f"{ENV_PREFIX}USE_PROXIES"
ENV_WAIT_SECONDS = f"{ENV_PREFIX}WAIT_SECONDS"

DEFAULT_LIMIT = 0
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_WAIT_SECONDS = 10
DEFAULT_DATA_DIR = "./"
DEFAULT_LISTINGS_FILE = "listings.csv"
DEFAULT_HEADLESS = False
DEFAULT_CHROMIUM_PATH = "/usr/bin/chromium"
DEFAULT_RECRAWL_HOURS = 24


class Args(NamedTuple):
    """Command-line arguments."""

    data_dir: str
    limit: int
    headless: bool
    chromium_path: str
    chromedriver_path: str
    timeout_seconds: int
    wait_seconds: int
    recrawl_hours: float


class DisplayNotFound(Exception):
    """DisplayNotFound is raised when a display is not found in the given environment."""

    pass


def get_args() -> Args:
    """Return command-line arguments."""
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"The limit of new listings to scrape. ({ENV_LIMIT})",
    )

    parser.add_argument(
        "--headless",
        type=bool,
        default=DEFAULT_HEADLESS,
        help=f"Run browser in headless mode. ({ENV_HEADLESS})",
    )

    parser.add_argument(
        "--chromium-path",
        type=str,
        default=DEFAULT_CHROMIUM_PATH,
        help="Path to Chromium executable.",
    )

    parser.add_argument(
        "--driver-path",
        type=str,
        help="Path to Chromium ChromeDriver executable.",
    )

    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Seconds before timeout occurs. ({ENV_TIMEOUT_SECONDS})",
    )

    parser.add_argument(
        "--recrawl-hours",
        "-r",
        type=float,
        default=DEFAULT_RECRAWL_HOURS,
        help=f"Recrawl listings that haven't been checked for this many hours or more ({ENV_RECRAWL_HOURS})",
    )

    parser.add_argument(
        "--data-dir",
        "-d",
        type=str,
        default=DEFAULT_DATA_DIR,
        help="Directory to save output data.",
    )

    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=DEFAULT_WAIT_SECONDS,
        help=f"Seconds to wait before re-trying after being rate-limited. ({ENV_WAIT_SECONDS})",
    )

    args = parser.parse_args()
    env_limit = os.getenv(ENV_LIMIT)
    env_headless = os.getenv(ENV_HEADLESS)
    env_timeout_seconds = os.getenv(ENV_TIMEOUT_SECONDS)
    env_recrawl_hours = os.getenv(ENV_RECRAWL_HOURS)
    env_wait_seconds = os.getenv(ENV_WAIT_SECONDS)

    data_dir: str = args.data_dir
    limit: int = int(env_limit) if env_limit else args.limit
    headless: bool = bool(env_headless) if env_headless else args.headless
    chromium_path: str = args.chromium_path
    chromedriver_path: str = args.driver_path
    timeout_seconds: int = int(env_timeout_seconds) if env_timeout_seconds else args.timeout
    recrawl_hours: float = float(env_recrawl_hours) if env_recrawl_hours else args.recrawl_hours
    wait_seconds: int = int(env_wait_seconds) if env_wait_seconds else args.wait_seconds

    return Args(
        data_dir=data_dir,
        limit=limit,
        headless=headless,
        chromium_path=chromium_path,
        chromedriver_path=chromedriver_path,
        timeout_seconds=timeout_seconds,
        wait_seconds=wait_seconds,
        recrawl_hours=recrawl_hours,
    )


def main():
    """Run the scraper."""
    signal.signal(signal.SIGTERM, handle_sigterm_interrupt)

    logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
    args = get_args()
    logging.info(args)

    # if no display is available and we aren't headless, create a virtual display
    display: Display | None = None
    if not has_display() and not args.headless:
        display = get_virtual_display()

        if not display.is_alive():
            raise DisplayNotFound()

    listings_df = pd.DataFrame()
    item_ids: set[str] = set()

    listings_file_path = os.path.join(args.data_dir, DEFAULT_LISTINGS_FILE)
    if os.path.isfile(listings_file_path):
        has_duplicates = False
        listings_df = read_csv(listings_file_path)
        if "item_id" in listings_df.keys():
            for item_id in list(listings_df["item_id"]):
                if item_id not in item_ids:
                    item_ids.add(item_id)
                else:
                    has_duplicates = True

        if has_duplicates:
            logging.info(("Removing duplicate existing listings..."))
            listings_df = remove_duplicate_listings(listings_df)
            save_listings(listings_df=listings_df, file_path=listings_file_path)

        # recrawl listings with >= recrawl_hours since last crawl
        now_datetime = get_utc_now()
        for _, listing in listings_df.iterrows():
            item_id: str = str(listing["item_id"])
            crawled_timestamp: str = str(listing["crawled_timestamp"])
            crawled_datetime = datetime.fromisoformat(crawled_timestamp)
            diff_hours_now = diff_hours(crawled_datetime, now_datetime)
            if diff_hours_now >= args.recrawl_hours:
                item_ids.remove(item_id)

    if not os.path.isfile(args.chromium_path):
        raise NotFoundError(f"Chromium not found at: {args.chromium_path}")

    if args.chromedriver_path and not os.path.isfile(args.chromedriver_path):
        raise NotFoundError(f"ChromeDriver not found at: {args.chromedriver_path} ")

    mp_scraper = MpScraper(
        chromium_path=args.chromium_path,
        chromedriver_path=args.chromedriver_path,
        headless=args.headless,
        timeout_seconds=args.timeout_seconds,
        wait_seconds=args.wait_seconds,
    )

    parent_categories = mp_scraper.get_parent_categories()
    if len(parent_categories) == 0:
        raise CategoriesError("No parent categories found")

    try:
        remaining_limit = args.limit
        total = args.limit if args.limit > 0 else None
        stop = False

        with tqdm(desc="Total Progress", total=total, position=0) as pbar:
            for parent_category in parent_categories:
                listings: list[Listing] = []

                if stop:
                    break

                try:
                    listings = mp_scraper.get_listings(
                        parent_category=parent_category,
                        limit=remaining_limit,
                        existing_item_ids=item_ids,
                    )

                    listings_count = len(listings)
                    remaining_limit = remaining_limit - listings_count
                    pbar.update(listings_count)

                    if remaining_limit < 1:
                        stop = True
                except ListingsInterrupt as exc:
                    logging.info("Stopping gracefully...")
                    listings = exc.listings
                    stop = True
                except ListingsError as exc:
                    listings = exc.listings
                    stop = True
                except KeyboardInterrupt:
                    stop = True

                if len(listings) > 0:
                    # concatenate the category's listings into the main dataframe
                    category_df = pd.DataFrame(listings)
                    listings_df = pd.concat([listings_df, category_df], ignore_index=True)

        mp_scraper.close()
    except Exception as exc:
        mp_scraper.close()
        raise exc

    if len(listings_df.index) > 0:
        logging.info("Saving listings to %s", listings_file_path)

        # remove any duplicates from recrawling
        listings_df = remove_duplicate_listings(listings_df)
        save_listings(listings_df=listings_df, file_path=listings_file_path)
    else:
        logging.warning("Nothing to save.")


if __name__ == "__main__":
    main()
