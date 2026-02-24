from __future__ import annotations

from typing import TYPE_CHECKING

from bs4 import BeautifulSoup as Soup
from bs4 import Tag
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from .exceptions import ElementNotFoundError, ForbiddenError, MPError

if TYPE_CHECKING:
    from selenium.webdriver.remote.webelement import WebElement

MODAL_ID = "notice"
BTN_COOKIES_ACCEPT_ARIA_LABEL = "[aria-label=Accepteren]"

ACCEPT_COOKIES_TIMEOUT_SECONDS = 30
MARKTPLAATS_403_URL = "https://www.marktplaats.nl/403/"


class MPDriver(WebDriver):
    def __init__(
        self,
        base_url: str,
        chromedriver_path: str | None = None,
        chromium_path: str | None = None,
        headless: bool = False,
    ) -> None:
        chrome_options = ChromeOptions()
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-setuid-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        if headless:
            chrome_options.add_argument("--headless")

        chrome_service: ChromeService | None = None
        if chromedriver_path:
            chrome_service = ChromeService(executable_path=chromedriver_path)
            super().__init__(options=chrome_options, service=chrome_service)
        else:
            super().__init__(options=chrome_options)

    def __get_forbidden_iframe(self) -> WebElement | None:
        """Return the forbidden iframe, or None if it does not exist."""
        try:
            iframe_elems = self.find_elements(by=By.TAG_NAME, value="iframe")
            for iframe in iframe_elems:
                src_url = iframe.get_attribute("src")
                if src_url == MARKTPLAATS_403_URL:
                    return iframe
        except StaleElementReferenceException:
            self.refresh()
        except WebDriverException:
            pass

        return None

    @staticmethod
    def __get_mp_err_text(soup: Soup) -> str | None:
        """Return the error text from the given Marktplaats page, or None."""
        err_msgs = soup.find_all("p", class_="mp-Alert--error")
        if len(err_msgs) > 0:
            err_msg = err_msgs[0]

            if not isinstance(err_msg, Tag):
                raise ElementNotFoundError(tag_name="p", attrs={"class": "mp-Alert--error"})

            return err_msg.get_text(strip=True)

        err_pages = soup.find_all("div", class_="hz-ErrorPage-message")
        if len(err_pages) > 0:
            err_page = err_pages[0]

            if not isinstance(err_page, Tag):
                raise ElementNotFoundError(tag_name="div", attrs={"class": "hz-ErrorPage-message"})

            err_div = err_page.find("div", class_="u-textStyleTitle3")

            if not isinstance(err_div, Tag):
                raise ElementNotFoundError(tag_name="div", attrs={"class": "u-textStyleTitle3"})

            return err_div.get_text(strip=True)

        return None

    def get_soup(self) -> Soup:
        """Return a BeautifulSoup object of the page, raising Marktplaats specific errors found."""
        src = self.page_source

        forbidden_iframe = self.__get_forbidden_iframe()
        if forbidden_iframe:
            self.switch_to.frame(forbidden_iframe)
            src = self.page_source
            soup = Soup(src, "lxml")
            self.switch_to.default_content()

            forbidden_err_text = self.__get_mp_err_text(soup)
            if forbidden_err_text:
                raise ForbiddenError(msg=forbidden_err_text)

        soup = Soup(src, "lxml")
        err_text = self.__get_mp_err_text(soup)
        if err_text:
            raise MPError(msg=err_text)

        return soup
