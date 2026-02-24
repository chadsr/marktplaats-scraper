from __future__ import annotations

import json
import logging
from logging import Logger
from time import sleep
from typing import Any, NamedTuple

from bs4 import BeautifulSoup, Tag
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from tqdm import tqdm

from .driver import MPDriver
from .exceptions import (
    ElementNotFoundError,
    ForbiddenError,
    ListingsError,
    ListingsInterruptError,
    MPError,
    UnexpectedCategoryIdError,
)
from .listing import Listing, ListingDetails
from .utils import format_text, get_utc_iso_now

logger: Logger = logging.getLogger(__name__)

MARTKPLAATS_BASE_URL = "https://marktplaats.nl"
REQUEST_OPTS = "#sortBy:SORT_INDEX|sortOrder:DECREASING"

CONTENT_ID = "content"
SELECT_ELEM_ID = "categoryId"
DATA_ELEM_ID = "__NEXT_DATA__"
LISTING_DATA_ELEM_ID = "__CONFIG__"
LISTING_ROOT_ID = "listing-root"
ALL_CATEGORIES_ID = 0

# if a listing ID starts with this, it seems to be a sponsored advertisement post we want to ignore
MARKTPLAATS_ADVERTISEMENT_PREFIX = "a"

TYPE_KEY = "type"
SERVICE_KEY = "service"
VERTICALS_KEY = "verticals"
LOCATION_KEY = "location"
COUNTRYCODE_KEY = "countryAbbreviation"
CITY_KEY = "cityName"
SELLER_INFO_KEY = "sellerInformation"
SELLER_ID_KEY = "sellerId"
LISTED_TIMESTAMP_KEY = "since"
LISTING_KEY = "listing"
AD_TYPE_KEY = "adType"
PRICE_INFO_KEY = "priceInfo"
PRICE_TYPE_KEY = "priceType"
PRICE_CENTS_KEY = "priceCents"
STATS_KEY = "stats"
VIEW_COUNT_KEY = "viewCount"
FAVORITED_KEY = "favoritedCount"


class Category(NamedTuple):
    """Marktplaats category."""

    id: int
    url: str


class MpScraper:
    def __init__(
        self,
        headless: bool,
        timeout_seconds: float,
        wait_seconds: float,
        base_url: str = MARTKPLAATS_BASE_URL,
        chromium_path: str | None = None,
        chromedriver_path: str | None = None,
    ) -> None:
        self.__driver: MPDriver = MPDriver(
            chromedriver_path=chromedriver_path,
            chromium_path=chromium_path,
            base_url=base_url,
            headless=headless,
        )

        self.__base_url = base_url
        self.__wait_seconds = wait_seconds
        self.__timeout_seconds = timeout_seconds

    def close(self) -> None:
        """Gracefully close the scraper."""
        self.__driver.quit()

    @staticmethod
    def __get_url_with_options(category_url: str, page_number: int) -> str:
        """Return the formatted Marktplaats URL with options and page number."""

        if category_url[-1] != "/":
            category_url = category_url + "/"

        return f"{category_url}p/{page_number}/{REQUEST_OPTS}"

    def get_parent_categories(self) -> set[Category]:
        parent_categories: set[Category] = set()

        self.__driver.get(self.__base_url)
        soup = self.__driver.get_soup()
        category_li_elems = soup.find_all("li", class_="CategoriesBlock-listItem")

        for category_li_elem in category_li_elems:
            if not isinstance(category_li_elem, Tag):
                raise ElementNotFoundError(
                    tag_name="li", attrs={"class": "CategoriesBlock-listItem"}
                )

            category_a_elem = category_li_elem.find("a", class_="hz-Link--navigation")
            if not isinstance(category_a_elem, Tag):
                raise ElementNotFoundError(tag_name="a", attrs={"class": "hz-Link--navigation"})

            href_val = category_a_elem.attrs.get("href", "")
            href_split = str(href_val).split("/") if not isinstance(href_val, list) else []
            category_id = int(href_split[2])
            category_url = f"{self.__base_url}/l/{href_split[3]}"
            category = Category(id=category_id, url=category_url)
            parent_categories.add(category)

        return parent_categories

    def __get_subcategories(self, parent_category: Category) -> set[Category]:
        """Return any existing sub-category URLs for the given category URL."""
        subcategories: set[Category] = set()

        self.__driver.get(parent_category.url)

        try:
            # Wait for page to load
            content_present = expected_conditions.presence_of_element_located((By.ID, CONTENT_ID))
            _ = WebDriverWait(self.__driver, self.__timeout_seconds).until(content_present)
        except TimeoutException:
            return subcategories

        soup: BeautifulSoup = self.__driver.get_soup()

        next_data_script = soup.find("script", {"id": DATA_ELEM_ID, "type": "application/json"})
        if not (isinstance(next_data_script, Tag) and next_data_script.string):
            raise ElementNotFoundError(tag_name="script", attrs={"id": DATA_ELEM_ID})

        next_data = json.loads(next_data_script.string)

        # Navigate to searchCategoryOptions which contains all subcategories
        page_props = next_data.get("props", {}).get("pageProps")
        search_data = page_props.get("searchRequestAndResponse")
        category_options = search_data.get("searchCategoryOptions")

        if not category_options:
            raise ElementNotFoundError("No searchCategoryOptions found in __NEXT_DATA__")

        # Extract subcategories (skip the first item which is the parent category)
        for cat_option in category_options:
            cat_id = cat_option.get("id")
            cat_key = cat_option.get("key")
            parent_id = cat_option.get("parentId")

            # Skip if this is the parent category itself or missing required fields
            if cat_id == parent_category.id or not cat_id or not cat_key:
                continue

            # Only include subcategories (those with parentId matching parent)
            if parent_id is None or parent_id != parent_category.id:
                continue

            # Build the subcategory URL
            if parent_id:
                # This is a child category - construct URL with parent path
                parent_key = cat_option.get("parentKey", "")
                if parent_key:
                    subcategory_url = f"{MARTKPLAATS_BASE_URL}/l/{parent_key}/{cat_key}/"
                else:
                    subcategory_url = f"{MARTKPLAATS_BASE_URL}/l/{cat_key}/"
            else:
                # This is a top-level category (shouldn't happen but handle it)
                subcategory_url = f"{MARTKPLAATS_BASE_URL}/l/{cat_key}/"

            subcategory = Category(id=cat_id, url=subcategory_url)
            subcategories.add(subcategory)

        return subcategories

    def listings_count(self, category: Category) -> int:
        """Return the listings count for the given category URL."""
        self.__driver.get(category.url)

        try:
            page_content_present = expected_conditions.presence_of_element_located(
                (By.ID, CONTENT_ID)
            )
            _ = WebDriverWait(self.__driver, self.__timeout_seconds).until(page_content_present)
        except TimeoutException:
            pass

        # Get the page source and parse the __NEXT_DATA__ JSON
        soup = self.__driver.get_soup()

        next_data_script = soup.find("script", {"id": DATA_ELEM_ID, "type": "application/json"})
        if not (isinstance(next_data_script, Tag) and next_data_script.string):
            raise ElementNotFoundError(tag_name="script", attrs={"id": DATA_ELEM_ID})

        try:
            next_data = json.loads(next_data_script.string)

            # Navigate to totalResultCount
            page_props = next_data.get("props", {}).get("pageProps", {})
            search_data = page_props.get("searchRequestAndResponse", {})
            total_count = search_data.get("totalResultCount")

            if total_count is None:
                raise ElementNotFoundError(tag_name="totalResultCount", attrs={})

            return int(total_count)

        except (json.JSONDecodeError, KeyError, AttributeError, ValueError) as e:
            raise ElementNotFoundError(tag_name=DATA_ELEM_ID, attrs={"error": str(e)}) from e

    def __get_listing_details(self, listing_url: str) -> ListingDetails:
        """Return the full description, listing type and service attributes."""
        self.__driver.get(listing_url)

        try:
            listing_present = expected_conditions.presence_of_element_located(
                (By.ID, LISTING_ROOT_ID)
            )
            _ = WebDriverWait(self.__driver, self.__timeout_seconds).until(listing_present)
        except TimeoutException:
            # pass since we catch errors next
            pass

        page = self.__driver.get_soup()

        description_div = page.find("div", class_="Description-description")
        if not isinstance(description_div, Tag):
            raise ElementNotFoundError(tag_name="div", attrs={"class": "Description-description"})

        description = description_div.get_text(separator=" ", strip=True)

        types: set[str] = set()
        services: set[str] = set()

        # Parse type/service attributes
        attribute_items = page.find_all("div", class_="Attributes-item")
        for attribute_item in attribute_items:
            if isinstance(attribute_item, Tag):
                attribute_label = attribute_item.find("strong", class_="Attributes-label")
                if isinstance(attribute_label, Tag):
                    attribute_label_text = attribute_label.get_text(strip=True).lower()

                    attribute_value = attribute_item.find("span", class_="Attributes-value")
                    if isinstance(attribute_value, Tag):
                        attribute_text = attribute_value.get_text(strip=True)
                        values: set[str] = set()
                        if ", " in attribute_text:
                            values = set(attribute_text.split(", "))
                        else:
                            values.add(attribute_text)

                        if attribute_label_text == TYPE_KEY:
                            types = types.union(values)
                        elif attribute_label_text == SERVICE_KEY:
                            services = services.union(values)
        # Get stats
        data = self.__driver.execute_script(f"return window.{LISTING_DATA_ELEM_ID}")
        ad_type = data[LISTING_KEY][AD_TYPE_KEY]

        price_info = data[LISTING_KEY][PRICE_INFO_KEY]
        price_type = price_info[PRICE_TYPE_KEY]
        price_cents = int(price_info[PRICE_CENTS_KEY])

        stats = data[LISTING_KEY][STATS_KEY]
        view_count = int(stats[VIEW_COUNT_KEY])
        favorited_count = int(stats[FAVORITED_KEY])
        listed_timestamp = datetime.fromisoformat(stats[LISTED_TIMESTAMP_KEY]).isoformat()

        return ListingDetails(
            ad_type=ad_type,
            description=description,
            types=types,
            services=services,
            price_type=price_type,
            price_cents=price_cents,
            view_count=view_count,
            favorited_count=favorited_count,
            listed_timestamp=listed_timestamp,
        )

    def get_listings(
        self, parent_category: Category, limit: int, existing_item_ids: set[str] | None = None
    ) -> list[Listing]:
        """Return Marktplaats listings for the category up to limit, excluding existing_item_ids."""
        listings: list[Listing] = []
        item_ids: set[str] = existing_item_ids.copy() if existing_item_ids is not None else set()
        parent_category_slug = parent_category.url.split("/")[-1]

        listings_count = self.listings_count(parent_category)
        if limit > listings_count or limit == 0:
            limit = listings_count

        max_listings = limit

        categories: list[Category] = []

        try:
            subcategories = self.__get_subcategories(parent_category=parent_category)
            if len(subcategories) > 0:
                categories = list(subcategories)
            else:
                logger.warning(
                    "No sub-categories found. Using parent category %s (%d)",
                    parent_category_slug,
                    parent_category.id,
                )
                categories = [parent_category]
        except Exception as exc:
            raise ListingsError(listings=listings, msg="Failed to get subcategory URLs") from exc

        with tqdm(
            desc=f'Category "{parent_category_slug}" Progress',
            total=max_listings,
            position=1,
            smoothing=0,
        ) as pbar:
            for category_id, category_url in categories:
                current_page = 1
                while len(listings) < max_listings:
                    try:
                        url_with_opts = self.__get_url_with_options(category_url, current_page)
                        self.__driver.get(url_with_opts)

                        # Attempt to parse the page
                        page = self.__driver.get_soup()

                        # Get the next.js props JSON object
                        page_data_script = page.find("script", id=DATA_ELEM_ID)
                        if not isinstance(page_data_script, Tag):
                            raise ElementNotFoundError(
                                tag_name="script",
                                attrs={"id": DATA_ELEM_ID},
                            )

                        page_data = json.loads(page_data_script.text or "{}")
                        res_listings = page_data["props"]["pageProps"]["searchRequestAndResponse"][
                            "listings"
                        ]

                        if len(res_listings) == 0:
                            logger.info(
                                "Ran out of listings for %s at page %i",
                                category_url,
                                current_page,
                            )
                            break

                        for res_listing in res_listings:
                            if len(listings) == limit:
                                break

                            item_id: str = res_listing["itemId"]
                            if item_id[0] == MARKTPLAATS_ADVERTISEMENT_PREFIX:
                                # skip sponsored advertisement listings
                                continue

                            # skip if we already have this item_id
                            if item_id in item_ids:
                                # if limit is max listings, decrease max fetch-able count
                                if limit == listings_count:
                                    max_listings -= 1
                                    pbar.total = max_listings

                                continue

                            # Get category ID
                            child_category_id: int = int(res_listing["categoryId"])
                            if child_category_id != category_id:
                                raise UnexpectedCategoryIdError(child_category_id, category_id)

                            # Get basic info
                            title: str = format_text(str(res_listing["title"]))
                            vip_url = res_listing["vipUrl"]
                            listing_url = f"{MARTKPLAATS_BASE_URL}{vip_url}"

                            # Get image URLs
                            image_urls: list[str] = []
                            if "pictures" in res_listing:
                                for image_path in res_listing["pictures"]:
                                    image_url_el = image_path["extraExtraLargeUrl"]
                                    image_urls.append(image_url_el)

                            # Get listing details from listing page
                            listing_details: ListingDetails | None = None
                            try:
                                got_details = False
                                while not got_details:
                                    try:
                                        listing_details = self.__get_listing_details(listing_url)

                                        got_details = True
                                    except ForbiddenError:
                                        # wait
                                        logger.warning(
                                            "Got rate-limited. Retrying for listing %s in %d seconds...",
                                            item_id,
                                            self.__wait_seconds,
                                        )
                                        sleep(self.__wait_seconds)
                                        continue
                            except MPError as exc:
                                logger.error(
                                    "Error fetching listing %s details Exception: %s",
                                    listing_url,
                                    str(exc),
                                )

                            except ElementNotFoundError as exc:
                                logger.error(
                                    "Unexpected element in listing %s Exception: %s",
                                    listing_url,
                                    str(exc),
                                )

                            except KeyboardInterrupt as exc:
                                raise exc

                            if listing_details is None:
                                # Failed to get listing details, so skip this listing
                                max_listings -= 1
                                pbar.total = max_listings
                                continue

                            # Get location info
                            country_code = ""
                            city_name = ""
                            if LOCATION_KEY in res_listing:
                                loc = res_listing[LOCATION_KEY]
                                country_code = loc[COUNTRYCODE_KEY]

                                if CITY_KEY in loc:
                                    city_name = loc[CITY_KEY]

                            # Get category name hierarchy ("verticals")
                            verticals = []
                            if VERTICALS_KEY in res_listing:
                                verticals = res_listing[VERTICALS_KEY]

                            # get seller ID
                            seller_id = ""
                            if SELLER_INFO_KEY in res_listing:
                                seller_id = res_listing[SELLER_INFO_KEY][SELLER_ID_KEY]

                            crawled_timestamp = get_utc_iso_now()

                            listing = Listing(
                                item_id=item_id,
                                parent_category_id=parent_category.id,
                                child_category_id=child_category_id,
                                category_verticals=tuple(verticals),
                                ad_type=listing_details.ad_type,
                                title=title,
                                description=format_text(listing_details.description),
                                types=tuple(listing_details.types),
                                services=tuple(listing_details.services),
                                price_type=listing_details.price_type,
                                price_cents=listing_details.price_cents,
                                image_urls=tuple(image_urls),
                                listing_url=listing_url,
                                country_code=country_code,
                                city_name=city_name,
                                seller_id=seller_id,
                                listed_timestamp=listing_details.listed_timestamp,
                                crawled_timestamp=crawled_timestamp,
                                view_count=listing_details.view_count,
                                favorited_count=listing_details.favorited_count,
                            )

                            listings.append(listing)
                            item_ids.add(listing.item_id)
                            pbar.update()

                        current_page += 1

                    except ForbiddenError:
                        logger.warning(
                            "Probably rate-limited. waiting %d seconds...",
                            self.__timeout_seconds,
                        )
                        sleep(self.__timeout_seconds)
                        continue
                    except MPError as exc:
                        logger.error(
                            "Error crawling URL: %s Exception: %s",
                            category_url,
                            str(exc),
                        )
                        continue
                    except ElementNotFoundError as exc:
                        logger.error(
                            "Unexpected element for category URL: %s Exception: %s",
                            category_url,
                            str(exc),
                        )
                        continue
                    except TimeoutException as exc:
                        logger.warning("%s", str(exc))
                        continue
                    except WebDriverException as exc:
                        logger.error("%s", str(exc))
                        if exc.msg and "ERR_INTERNET_DISCONNECTED" in exc.msg:
                            sleep(self.__timeout_seconds)
                            continue
                        raise exc
                    except KeyboardInterrupt as exc:
                        raise ListingsInterruptError(listings=listings) from exc
                    except Exception as exc:
                        logger.exception(exc)
                        raise ListingsError(
                            listings=listings, msg=f"Error getting listings: {exc}"
                        ) from exc

        return listings
