import logging
import re
from dataclasses import dataclass
from datetime import datetime

from RPA.core.webdriver import start
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait
from zoneinfo import ZoneInfo


@dataclass
class Article:
    category: str
    title: str
    description: str
    published_at: datetime
    image_url: str

    @property
    def publication_date(self):
        return self.published_at.date()

    @property
    def publication_month(self):
        return self.published_at.replace(day=1).date()


class LATimesScraper:
    def __init__(self, url: str = "https://www.latimes.com/"):
        self.url: str = url
        self.logger = logging.getLogger(__name__)

        self._driver: WebDriver | None = None

    @property
    def driver(self) -> WebDriver:
        if not self._driver:
            self.logger.error("Webdriver not set. Please set webdriver first.")

        return self._driver

    def set_webdriver(self):
        self._driver = start("Chrome", options=self.set_chrome_options())

    def set_chrome_options(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-web-security")
        options.add_argument("--start-maximized")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--remote-debugging-port=9222")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])

        return options

    def open_homepage(self):
        self.driver.get(self.url)

    def search_for(self, search_query: str):
        self.logger.info(f"Searching for: {search_query}")

        # first, we need to wait for the magnify-icon data-element to be visible
        search_icon = WebDriverWait(self.driver, timeout=5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "svg[data-element='magnify-icon']"))
        )
        search_icon.click()

        # now we get the search input field
        search_input = WebDriverWait(self.driver, timeout=5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "input[data-element='search-form-input']"))
        )

        search_input.click()
        search_input.send_keys(search_query)
        search_input.submit()

        self.logger.info("Search submitted")

    def filter_by_category(self, category: str):
        self.logger.info(f"Filtering by category: {category}")

        # we need to click on the .data-see-all button
        # to show all the categories
        see_all_button = WebDriverWait(self.driver, timeout=5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".see-all-button"))
        )

        see_all_button.click()

        # we need to wait for the categories inputs to be visible
        categories = WebDriverWait(self.driver, timeout=5).until(
            EC.visibility_of_all_elements_located(
                (By.CSS_SELECTOR, ".search-filter-menu[data-name=Topics] > li .checkbox-input-label")
            )
        )

        for cat in categories:
            if cat.get_attribute("textContent").lower().strip() == category.lower().strip():
                cat.click()
                break

        # now we wait for the reset button to be visible
        WebDriverWait(self.driver, timeout=3).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".search-results-module-filters-selected-reset"))
        )

    def get_news(self, search_query: str, min_date: int):
        # get results div (.search-results-module-results-menu)
        # wait for the search results to be visible
        search_results = WebDriverWait(self.driver, timeout=5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".search-results-module-results-menu"))
        )

        # first we need to sort by newest
        sort_by_newest_select = WebDriverWait(self.driver, timeout=5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".search-results-module-sorts select"))
        )

        # select "Newest" from the dropdown
        Select(sort_by_newest_select).select_by_visible_text("Newest")

        # wait for the search results to be stale
        WebDriverWait(self.driver, timeout=5).until(EC.staleness_of(search_results))

        news = []
        failed = []

        while True:
            # wait for element with class search-results-module-results-menu to be visible
            # and have child elements
            articles = WebDriverWait(self.driver, timeout=5).until(
                EC.visibility_of_all_elements_located(
                    (By.CSS_SELECTOR, ".search-results-module-results-menu > li"),
                )
            )

            should_break = False

            for article_webelement in articles:
                try:
                    article = self.parse_article(article_webelement)

                    if article.publication_month < min_date:
                        should_break = True
                        break

                    else:
                        news.append(article)

                except Exception:
                    failed.append(article_webelement)

            if should_break:
                break

            # check if the button ".search-results-module-next-page" exists and is not disabled
            next_page_buttons = self.driver.find_elements(By.CSS_SELECTOR, ".search-results-module-next-page")

            if not next_page_buttons:
                break

            assert len(next_page_buttons) == 1, "More than one next page button found"

            next_page_button = next_page_buttons[0]

            if next_page_button.find_element(By.TAG_NAME, "svg").get_dom_attribute("data-inactive"):
                break

            next_page_button.click()

        return news

    def parse_article(self, article: WebElement) -> Article:
        category = self.extract_article_cateogry(article)
        title = self.extract_article_title(article)
        description = self.extract_description(article)
        date = self.extract_article_date(article)
        picture_url = self.extract_picture_url(article)

        return Article(category, title, description, date, picture_url)

    def extract_article_cateogry(self, article: WebElement) -> str:
        return article.find_element(By.CSS_SELECTOR, ".promo-category").text

    def extract_article_title(self, article: WebElement) -> str:
        return article.find_element(By.CSS_SELECTOR, ".promo-title").text

    def extract_description(self, article: WebElement) -> str:
        return article.find_element(By.CSS_SELECTOR, ".promo-description").text

    def extract_article_date(self, article: WebElement) -> datetime:
        timestamp_ns = article.find_element(By.CSS_SELECTOR, ".promo-timestamp").get_dom_attribute("data-timestamp")
        return datetime.fromtimestamp(int(timestamp_ns) / 1000, ZoneInfo("UTC"))

    def extract_picture_url(self, article: WebElement) -> str | None:
        try:
            return article.find_element(By.CSS_SELECTOR, "img").get_dom_attribute("src")
        except NoSuchElementException:
            return None

    def driver_quit(self):
        if self._driver:
            self._driver.quit()


def is_there_any_money_amount(text: str) -> bool:
    """Check if there is any money amount in the text.

    Possible formats: $11.1 | $111,111.11 | 11 dollars | 11 USD

    Args:
        text (str): The text to be checked.

    Returns:
        bool: True if there is any money amount in the text, False otherwise.

    Examples:
        >>> is_there_any_money_amount("The price is $11.1")
        True
        >>> is_there_any_money_amount("The price is $11.1 dollars")
        True
        >>> is_there_any_money_amount("The price is 11 dollars")
        True
        >>> is_there_any_money_amount("The price is 11 USD")
        True
        >>> is_there_any_money_amount("The price is 11")
        False
    """
    # boolean to check if there is any money amount in the article
    # possible formats: $11.1 | $111,111.11 | 11 dollars | 11 USD

    # regex for numbers with 1 or 2 decimal places and thousands separator
    # 1, 11, 111, 1.1, 11.1, 111.1, 1,111.1, 11,111.11
    NUMBERS = r"\d{1,3}(,\d{3})*(\.\d{1,2})?"

    # regex for money amounts
    dollar_first = re.compile(rf"\${NUMBERS}")
    dollar_last = re.compile(rf"{NUMBERS}\s?dollars", re.IGNORECASE)
    usd = re.compile(rf"{NUMBERS}\s?USD", re.IGNORECASE)

    money_amount = False
    money_amount |= bool(dollar_first.search(text))
    money_amount |= bool(dollar_last.search(text))
    money_amount |= bool(usd.search(text))

    return money_amount
