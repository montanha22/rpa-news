import logging
import random
import string
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
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
    title: str
    description: str
    published_at: datetime
    category: Optional[str] = None
    image_url: Optional[str] = None
    image_filepath: Optional[str] = None

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
        options.add_argument("--disable-dev-shm-usage")
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

    def get_news(self, min_date: int) -> list[Article]:
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

                    if article is None:
                        continue

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

    def parse_article(self, article: WebElement) -> Article | None:
        category = self.extract_article_cateogry(article)
        title = self.extract_article_title(article)
        description = self.extract_description(article)
        date = self.extract_article_date(article)
        image_url = self.extract_image_url(article)
        image_filepath = None

        if image_url:
            image_filepath = self.download_image(image_url)

        # if we don't have a title or description, we skip the article
        if not title or not description:
            return None

        return Article(
            title=title,
            description=description,
            published_at=date,
            category=category,
            image_url=image_url,
            image_filepath=image_filepath,
        )

    def extract_article_cateogry(self, article: WebElement) -> str:
        try:
            return article.find_element(By.CSS_SELECTOR, ".promo-category").text
        except NoSuchElementException:
            self.logger.error("No category found for the article")
            return None

    def extract_article_title(self, article: WebElement) -> str:
        try:
            return article.find_element(By.CSS_SELECTOR, ".promo-title").text
        except NoSuchElementException:
            self.logger.error("No title found for the article")
            return None

    def extract_description(self, article: WebElement) -> str:
        try:
            return article.find_element(By.CSS_SELECTOR, ".promo-description").text
        except NoSuchElementException:
            self.logger.error("No description found for the article")
            return None

    def extract_article_date(self, article: WebElement) -> datetime:
        try:
            timestamp_ns = article.find_element(By.CSS_SELECTOR, ".promo-timestamp").get_dom_attribute("data-timestamp")
            return datetime.fromtimestamp(int(timestamp_ns) / 1000, ZoneInfo("UTC"))
        except NoSuchElementException:
            self.logger.error("No date found for the article")
            return datetime.min

    def extract_image_url(self, article: WebElement) -> str | None:
        try:
            return article.find_element(By.CSS_SELECTOR, "img").get_dom_attribute("src")
        except NoSuchElementException:
            self.logger.warning("No image found for the article")
            return None

    def generate_random_filename(self, length: int = 8) -> str:
        return "".join(random.choices(string.ascii_letters + string.digits, k=length))

    def download_image(self, image_url: str, folderpath: str = None) -> str:
        """Download a image from a URL and save it to a file with a random name.

        Args:
            image_url (str): The URL of the image to download.
            folderpath (str, optional): The folder where the image will be saved. Defaults to None.
            if folderpath is None, the image will be saved in the output/imgs folder.

        Returns:
            str: The path to the downloaded image.
        """
        extension = image_url.split(".")[-1]
        folderpath = folderpath or "output"

        response = requests.get(image_url, stream=True)
        response.raise_for_status()

        random_filename = self.generate_random_filename()

        folder = Path(folderpath)
        folder.mkdir(parents=True, exist_ok=True)

        file = folder / f"image_{random_filename}.{extension}"
        with file.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return str(file)

    def driver_quit(self):
        if self._driver:
            self._driver.quit()
