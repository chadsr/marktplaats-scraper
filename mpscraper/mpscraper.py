import json
from time import sleep
import re
import logging
from typing import NamedTuple
from tqdm import tqdm
from bs4 import Tag
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By

from .driver import MPDriver
from .utils import get_utc_now, format_text
from .exceptions import (
    ElementNotFound,
    ListingsError,
    ListingsInterrupt,
    MPError,
    ForbiddenError,
    UnexpectedCategoryId,
)
from .listing import Listing, ListingDetails


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
        category_li_elem_name = "li"
        category_li_elem_attrs = {"class": "CategoriesBlock-listItem"}
        category_li_elems = soup.findAll(category_li_elem_name, attrs=category_li_elem_attrs)

        for category_li_elem in category_li_elems:
            if not isinstance(category_li_elem, Tag):
                raise ElementNotFound(tag_name=category_li_elem_name, attrs=category_li_elem_attrs)

            category_a_elem_name = "a"
            category_a_elem_attrs = {"class": "hz-Link--navigation"}
            category_a_elem = category_li_elem.find(
                name=category_a_elem_name, attrs=category_a_elem_attrs
            )
            if not isinstance(category_a_elem, Tag):
                raise ElementNotFound(tag_name=category_a_elem_name, attrs=category_a_elem_attrs)

            href_split = category_a_elem.attrs["href"].split("/")
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
            categories_present = EC.presence_of_element_located((By.ID, str(parent_category.id)))
            WebDriverWait(self.__driver, self.__timeout_seconds).until(categories_present)
        except TimeoutException:
            return subcategories

        soup = self.__driver.get_soup()

        category_id_elems_name = "select"
        category_id_elems_attrs = {"id": SELECT_ELEM_ID}
        category_id_elems = soup.find(name=category_id_elems_name, attrs=category_id_elems_attrs)
        if not isinstance(category_id_elems, Tag):
            raise ElementNotFound(tag_name=category_id_elems_name, attrs=category_id_elems_attrs)

        category_id_list_name = "div"
        category_id_list_attrs = {"id": str(parent_category.id)}
        category_id_list = soup.find(category_id_list_name, attrs=category_id_list_attrs)
        if not isinstance(category_id_list, Tag):
            raise ElementNotFound(tag_name=category_id_list_name, attrs=category_id_list_attrs)

        category_hrefs: dict[str, str] = {}
        subcategory_a_elem_name = "a"
        subcategory_a_elem_attrs = {"class": "category-name"}
        subcategory_a_elems = soup.findAll(subcategory_a_elem_name, attrs=subcategory_a_elem_attrs)
        for subcategory_a_elem in subcategory_a_elems:
            if not isinstance(subcategory_a_elem, Tag):
                raise ElementNotFound(tag_name=subcategory_a_elem)

            if "href" not in subcategory_a_elem.attrs:
                # TODO: Raise error
                continue

            category_name = str(subcategory_a_elem.contents[0])
            category_href = str(subcategory_a_elem.attrs["href"])
            category_hrefs[category_name] = category_href

        subcategory_option_elem_name = "option"
        subcategory_option_elems = category_id_elems.findAll(name=subcategory_option_elem_name)
        for subcategory_option_elem in subcategory_option_elems:
            if not isinstance(subcategory_option_elem, Tag):
                raise ElementNotFound(tag_name=subcategory_option_elem_name)

            subcategory_name = str(subcategory_option_elem.contents[0])

            if "value" not in subcategory_option_elem.attrs:
                continue

            subcategory_value = subcategory_option_elem.attrs["value"]
            if subcategory_value == "":
                continue

            subcategory_id = int(subcategory_value)

            if subcategory_id == parent_category.id or subcategory_id == ALL_CATEGORIES_ID:
                continue

            # get subcategory href
            subcategory_href = category_hrefs[subcategory_name]

            subcategory_url = f"{MARTKPLAATS_BASE_URL}{subcategory_href}"
            subcategory = Category(id=subcategory_id, url=subcategory_url)
            subcategories.add(subcategory)

        return subcategories

    def listings_count(self, category: Category) -> int:
        """Return the listings count for the given category URL."""
        self.__driver.get(category.url)

        page_content_present = EC.presence_of_element_located((By.ID, CONTENT_ID))
        WebDriverWait(self.__driver, self.__timeout_seconds).until(page_content_present)

        soup = self.__driver.get_soup()

        label_altijd_name = "label"
        label_altijd_attrs = {"for": "offeredSince-Altijd"}
        label_altijd = soup.find(name=label_altijd_name, attrs=label_altijd_attrs)
        if isinstance(label_altijd, Tag):
            altijd_counter_name = "span"
            altijd_counter_attrs = {"class": "hz-Text"}
            altijd_counter = label_altijd.find(name=altijd_counter_name, attrs=altijd_counter_attrs)
            if isinstance(altijd_counter, Tag):
                count_text = altijd_counter.get_text(strip=True)
                count_text = re.sub("[.,()]", "", count_text)
                return int(count_text)
            else:
                raise ElementNotFound(tag_name=altijd_counter_name, attrs=altijd_counter_attrs)
        else:
            raise ElementNotFound(tag_name=label_altijd_name, attrs=label_altijd_attrs)

    def __get_listing_details(self, listing_url: str) -> ListingDetails:
        """Return the full description, listing type and service attributes."""
        self.__driver.get(listing_url)

        try:
            listing_present = EC.presence_of_element_located((By.ID, LISTING_ROOT_ID))
            WebDriverWait(self.__driver, self.__timeout_seconds).until(listing_present)
        except TimeoutException:
            # pass since we catch errors next
            pass

        page = self.__driver.get_soup()

        description_div_name = "div"
        description_div_attrs = {
            "class": "Description-description",
            "data-collapsable": "description",
        }
        description_div = page.find(name=description_div_name, attrs=description_div_attrs)
        if not isinstance(description_div, Tag):
            raise ElementNotFound(tag_name=description_div_name, attrs=description_div_attrs)

        description = description_div.get_text(separator=" ", strip=True)

        types: set[str] = set()
        services: set[str] = set()

        # Parse type/service attributes
        attribute_items = page.find_all("div", {"class": "Attributes-item"})
        for attribute_item in attribute_items:
            if isinstance(attribute_item, Tag):
                attribute_label = attribute_item.find("strong", {"class": "Attributes-label"})
                if isinstance(attribute_label, Tag):
                    attribute_label_text = attribute_label.get_text(strip=True).lower()

                    attribute_value = attribute_item.find("span", {"class": "Attributes-value"})
                    if isinstance(attribute_value, Tag):
                        attribute_text = attribute_value.get_text(strip=True)
                        values = set()
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
        listed_timestamp = stats[LISTED_TIMESTAMP_KEY]

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
        """Return a list of Marktplaats listings for the given category, up to limit in quantity, and excluding item_ids from existing_item_ids."""
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
                logging.warning(
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

                        page_select_elem_present = EC.presence_of_element_located(
                            (By.ID, SELECT_ELEM_ID)
                        )
                        WebDriverWait(self.__driver, self.__timeout_seconds).until(
                            page_select_elem_present
                        )

                        # Attempt to parse the page
                        page = self.__driver.get_soup()
                        page_select_elem_name = "select"
                        page_select_elem_attrs = {"id": SELECT_ELEM_ID}
                        page_select_elem = page.find(
                            name=page_select_elem_name, attrs=page_select_elem_attrs
                        )
                        if not isinstance(page_select_elem, Tag):
                            raise ElementNotFound(
                                tag_name=page_select_elem_name,
                                attrs=page_select_elem_attrs,
                            )

                        # Get the selected category option element
                        page_option_selected_name = "option"
                        page_option_selected_attrs = {"selected": ""}
                        page_option_selected = page_select_elem.find(
                            name=page_option_selected_name,
                            attrs=page_option_selected_attrs,
                        )
                        if not isinstance(page_option_selected, Tag):
                            raise ElementNotFound(
                                tag_name=page_option_selected_name,
                                attrs=page_option_selected_attrs,
                            )

                        # Get the next.js props JSON object
                        page_data_script_name = "script"
                        page_data_script_attrs = {"id": DATA_ELEM_ID}
                        page_data_script = page.find(
                            name=page_data_script_name, attrs=page_data_script_attrs
                        )
                        if not isinstance(page_data_script, Tag):
                            raise ElementNotFound(
                                tag_name=page_data_script_name,
                                attrs=page_data_script_attrs,
                            )

                        page_data = json.loads(page_data_script.text)
                        res_listings: list[dict] = page_data["props"]["pageProps"][
                            "searchRequestAndResponse"
                        ]["listings"]

                        if len(res_listings) == 0:
                            logging.info(
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
                                # if limit is set to max listings then decrease the maximum fetch-able listings count
                                if limit == listings_count:
                                    max_listings -= 1
                                    pbar.total = max_listings

                                continue

                            # Get category ID
                            child_category_id: int = int(res_listing["categoryId"])
                            if child_category_id != category_id:
                                raise UnexpectedCategoryId(child_category_id, category_id)

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
                                        logging.warning(
                                            "Got rate-limited. Retrying for listing %s in %d seconds...",
                                            item_id,
                                            self.__wait_seconds,
                                        )
                                        sleep(self.__wait_seconds)
                                        continue
                            except MPError as exc:
                                logging.error(
                                    "Error fetching listing %s details Exception: %s",
                                    listing_url,
                                    str(exc),
                                )

                            except ElementNotFound as exc:
                                logging.error(
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

                            crawled_timestamp = get_utc_now()

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
                        logging.warning(
                            f"Probably rate-limited. waiting {self.__timeout_seconds} seconds..."
                        )
                        sleep(self.__timeout_seconds)
                        continue
                    except MPError as exc:
                        logging.error(
                            "Error crawling URL: %s Exception: %s",
                            category_url,
                            str(exc),
                        )
                        continue
                    except ElementNotFound as exc:
                        logging.error(
                            "Unexpected element for category URL: %s Exception: %s",
                            category_url,
                            str(exc),
                        )
                        continue
                    except TimeoutException as exc:
                        logging.warning("%s", str(exc))
                        continue
                    except WebDriverException as exc:
                        logging.error("%s", str(exc))
                        if exc.msg and "ERR_INTERNET_DISCONNECTED" in exc.msg:
                            sleep(self.__timeout_seconds)
                            continue
                        else:
                            raise exc
                    except KeyboardInterrupt as exc:
                        raise ListingsInterrupt(listings=listings) from exc
                    except Exception as exc:
                        logging.exception(exc)
                        raise ListingsError(
                            listings=listings, msg=f"Error getting listings: {exc}"
                        ) from exc

        return listings
