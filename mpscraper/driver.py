from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver import ChromeOptions, ChromeService
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    StaleElementReferenceException,
    WebDriverException,
)
from bs4 import BeautifulSoup as Soup
from bs4 import Tag

from .exceptions import ElementNotFound, MPError, ForbiddenError

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
            super(MPDriver, self).__init__(
                options=chrome_options, service=chrome_service
            )
        else:
            super(MPDriver, self).__init__(options=chrome_options)

        # self.__accept_cookies(url=base_url)

    def __accept_cookies(self, url: str) -> None:
        """Accept the cookies banner."""

        self.get(url)
        element_present = EC.presence_of_element_located((By.ID, MODAL_ID))
        WebDriverWait(self, ACCEPT_COOKIES_TIMEOUT_SECONDS).until(element_present)
        accept_btn = self.find_element(
            by=By.CSS_SELECTOR, value=BTN_COOKIES_ACCEPT_ARIA_LABEL
        )
        accept_btn.click()

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
        err_msg_name = "p"
        err_msg_attrs = {"class": "mp-Alert--error"}
        err_msgs = soup.find_all("p", attrs=err_msg_attrs)
        if len(err_msgs) > 0:
            err_msg = err_msgs[0]
            err_text = ""

            if not isinstance(err_msg, Tag):
                raise ElementNotFound(tag_name=err_msg_name, attrs=err_msg_attrs)

            err_text = err_msg.get_text(strip=True)
            return err_text

        err_pages_name = "div"
        err_pages_attrs = {"class": "hz-ErrorPage-message"}
        err_pages = soup.find_all(name=err_pages_name, attrs=err_pages_attrs)
        if len(err_pages) > 0:
            err_page = err_pages[0]

            if not isinstance(err_page, Tag):
                raise ElementNotFound(tag_name=err_pages_name, attrs=err_pages_attrs)

            err_div_name = "div"
            err_div_attrs = {"class": "u-textStyleTitle3"}
            err_div = err_page.find(name=err_div_name, attrs=err_div_attrs)

            if not isinstance(err_div, Tag):
                raise ElementNotFound(tag_name=err_div_name, attrs=err_div_attrs)

            err_text = err_div.get_text(strip=True)
            return err_text

        return None

    def get_soup(self) -> Soup:
        """Return a BeautifulSoup object of the requested page, raising any Marktplaats specific errors found."""
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
