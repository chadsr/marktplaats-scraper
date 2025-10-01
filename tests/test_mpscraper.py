import os
from collections.abc import Iterable
import pytest
from selenium.webdriver.chrome.webdriver import WebDriver
from pyvirtualdisplay.display import Display
from datetime import timedelta

from mpscraper.mpscraper import (
    MARKTPLAATS_ADVERTISEMENT_PREFIX,
    MARTKPLAATS_BASE_URL,
    Category,
    MpScraper,
)
from mpscraper.listing import Listing

from mpscraper.utils import diff_hours, get_utc_now, format_text
from mpscraper.display import has_display, get_virtual_display
from mpscraper.driver import MPDriver

TEST_RUN_HEADLESS = False
CHROMIUM_PATH = os.getenv("CHROMIUM_PATH")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH")

TEST_CATEGORY = Category(id=322, url=f"{MARTKPLAATS_BASE_URL}/l/computers-en-software/")
TEST_WAIT_SECONDS = 30
TEST_DRIVER_TIMEOUT_SECONDS = 30

LIMIT_SMALL = 2
LIMIT_LARGE = 10


@pytest.fixture(scope="session")
def display() -> Display | None:
    if not has_display():
        return get_virtual_display()

    return None


@pytest.fixture(scope="function")
def driver() -> Iterable[WebDriver]:
    chromium_path: str | None = None
    if CHROMIUM_PATH and CHROMIUM_PATH != "":
        chromium_path = CHROMIUM_PATH

    chromedriver_path: str | None = None
    if CHROMEDRIVER_PATH and CHROMEDRIVER_PATH != "":
        chromedriver_path = CHROMEDRIVER_PATH

    driver = MPDriver(
        chromedriver_path=chromedriver_path,
        chromium_path=chromium_path,
        base_url=MARTKPLAATS_BASE_URL,
        headless=TEST_RUN_HEADLESS,
    )

    yield driver
    # after
    driver.quit()


@pytest.fixture(scope="function")
def mp_scraper() -> Iterable[MpScraper]:
    chromium_path: str | None = None
    if CHROMIUM_PATH and CHROMIUM_PATH != "":
        chromium_path = CHROMIUM_PATH

    chromedriver_path: str | None = None
    if CHROMEDRIVER_PATH and CHROMEDRIVER_PATH != "":
        chromedriver_path = CHROMEDRIVER_PATH

    mp_scraper = MpScraper(
        headless=TEST_RUN_HEADLESS,
        timeout_seconds=TEST_DRIVER_TIMEOUT_SECONDS,
        wait_seconds=TEST_WAIT_SECONDS,
        chromium_path=chromium_path,
        chromedriver_path=chromedriver_path,
    )

    yield mp_scraper

    mp_scraper.close()


class TestMpScraper:
    def test_get_listings_limit(self, mp_scraper: MpScraper, display: Display | None):
        """
        Assert that get_listings returns exactly the limit quantity and all are unique
        """
        if display and not display.is_alive():
            _ = display.start()

        limits = [LIMIT_SMALL, LIMIT_LARGE]
        for limit in limits:
            item_ids: set[str] = set()

            listings = mp_scraper.get_listings(parent_category=TEST_CATEGORY, limit=limit)
            assert len(listings) == limit
            for listing in listings:
                assert isinstance(listing, Listing)
                assert listing.item_id[0] != MARKTPLAATS_ADVERTISEMENT_PREFIX
                assert listing.parent_category_id == TEST_CATEGORY.id
                assert listing.item_id not in item_ids
                item_ids.add(listing.item_id)

    def test_get_listings_existing_item_ids(self, mp_scraper: MpScraper, display: Display | None):
        """
        Assert that item_ids passed to existing_item_ids are excluded from the results
        """
        if display and not display.is_alive():
            _ = display.start()

        listings_initial = mp_scraper.get_listings(parent_category=TEST_CATEGORY, limit=LIMIT_SMALL)
        assert len(listings_initial) == LIMIT_SMALL
        item_ids_initial = set([listing.item_id for listing in listings_initial])
        assert len(item_ids_initial) == len(listings_initial)

        listings_excl_initial = mp_scraper.get_listings(
            parent_category=TEST_CATEGORY,
            limit=LIMIT_LARGE,
            existing_item_ids=item_ids_initial,
        )
        for listing in listings_excl_initial:
            assert listing.item_id not in item_ids_initial

    def test_format_text(self):
        text_white_space = "Text    with            too much   spacing"
        text_white_space_exp = "Text with too much spacing"

        table_dict = {
            text_white_space: text_white_space_exp,
        }

        for text, exp_text in table_dict.items():
            text_fmt = format_text(text)
            assert text_fmt == exp_text

    def test_diff_hours(self):
        hours_offsets = [0.5, 1.0, 2.5, 3.99, 4.33, 5.00]
        datetime_now = get_utc_now()

        for hours_offset in hours_offsets:
            datetime_offset = datetime_now - timedelta(hours=hours_offset)
            diff_hours_now = diff_hours(datetime_offset, datetime_now)
            assert diff_hours_now == hours_offset
