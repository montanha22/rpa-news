import logging
import random
import string
from datetime import datetime
from pathlib import Path

import requests
from RPA.core.webdriver import start
from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait
from zoneinfo import ZoneInfo

from models import Article
from utilities import is_there_any_stale_web_element


# create error class to articles we failed to parse
class ArticleParseError(Exception):
    pass


class LATimesScraper:
    """A class to scrape articles from the LA Times website."""

    def __init__(self, homepage_url: str = "https://www.latimes.com/") -> None:
        self.homepage_url: str = homepage_url
        self.logger = logging.getLogger(__name__)

        self._driver: WebDriver | None = None

    @property
    def driver(self) -> WebDriver:
        if not self._driver:
            msg = "Webdriver not set. Please set webdriver first calling the set_webdriver method."
            self.logger.error(msg)
            raise ValueError(msg)

        return self._driver

    def set_webdriver(self) -> None:
        """Set the webdriver to use for scraping. This method should be called before using the driver."""
        self._driver = start("Chrome", options=self.set_chrome_options())

    def set_chrome_options(self) -> webdriver.ChromeOptions:
        """Set the Chrome options for the webdriver."""
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

    def open_homepage(self) -> None:
        """Open the LA Times homepage."""
        self.driver.get(self.homepage_url)

    def search_for(self, search_query: str):
        """Search for a query in the LA Times website.

        Args:
            search_query (str): The query to search for.
        """

        self.logger.info(f"Searching for: {search_query}")

        # First we need to wait for the magnify-icon data-element to be visible to click on it.
        search_icon = WebDriverWait(self.driver, timeout=5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "svg[data-element='magnify-icon']"))
        )
        search_icon.click()

        # Then we wait for the search input field, write the search query on it and submit the form.
        search_input = WebDriverWait(self.driver, timeout=5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "input[data-element='search-form-input']"))
        )
        search_input.click()
        search_input.send_keys(search_query)
        search_input.submit()

        self.logger.info("Search submitted")

    def filter_by_category(self, category: str):
        """Filter the search results by a category.

        With the search results page open, this method will click on the "See all" button to show all the categories,
        then it will click on the category specified in the argument.
        If the category is not found, it will log a warning and continue without filtering.

        Args:
            category (str): The category to filter by.
        """
        self.logger.info(f"Filtering by category: {category}")

        # Wait for the "see all categories" button to be visible and click on it.
        see_all_button = WebDriverWait(self.driver, timeout=5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".see-all-button"))
        )
        see_all_button.click()

        # Wait for the categories to be visible
        categories = WebDriverWait(self.driver, timeout=5).until(
            EC.visibility_of_all_elements_located(
                (By.CSS_SELECTOR, ".search-filter-menu[data-name=Topics] > li .checkbox-input-label")
            )
        )

        # Click on the category specified in the argument, if found.
        clicked = False
        for cat in categories:
            if cat.get_attribute("textContent").lower().strip() == category.lower().strip():
                cat.click()
                clicked = True
                break

        # If the category was found, we wait for the reset button to be visible.
        if clicked:
            # now we wait for the reset button to be visible
            WebDriverWait(self.driver, timeout=3).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, ".search-results-module-filters-selected-reset"))
            )

        # If the category was not found, we log a warning and continue without filtering.
        else:
            self.logger.warning(f"Category '{category}' not found. Continuing without filtering.")

    def get_news(self, min_date: int) -> list[Article]:
        """Get news articles from the search results page, up to a certain date, sorted by newest.

        Args:
            min_date (int): The minimum date for the articles to be included.
        """

        # Wait for element with the news articles to be visible
        search_results = WebDriverWait(self.driver, timeout=5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".search-results-module-results-menu"))
        )

        # Wait for the sort by dropdown to be visible and select "Newest"
        sort_by_newest_select = WebDriverWait(self.driver, timeout=5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".search-results-module-sorts select"))
        )
        Select(sort_by_newest_select).select_by_visible_text("Newest")

        # Wait for the search results to be stale, meaning that the page loaded the articles sorted by newest.
        WebDriverWait(self.driver, timeout=5).until(EC.staleness_of(search_results))

        news = set()

        # Loop through the pages of the search results
        # until we reach the minimum date or there are no more pages.
        while True:
            should_stop_pagination = False
            should_refetch_articles = False

            articles = self.fetch_articles_on_page_and_make_sure_they_are_not_stale()

            for article_webelement in articles:
                try:
                    # parse the article
                    article = self.parse_article(article_webelement)

                    # if the article is older than the minimum date, we stop the loop
                    # and flag the should_break variable to True, so we can break the outer loop.
                    if article.publication_month < min_date:
                        should_stop_pagination = True
                        break

                    # append the article to the news list if it's not older than the minimum date.
                    news.add(article)

                # if an error occurs while parsing the article, we log the error and continue to the next article.
                except ArticleParseError:
                    random_name = self.generate_random_filename()
                    filepath = f"output/error_screenshot_{random_name}.png"
                    article_webelement.screenshot(filepath)
                    self.logger.error(
                        "An error occurred while parsing an article", exc_info=True, extra={"screenshot": filepath}
                    )

                except StaleElementReferenceException:
                    should_refetch_articles = True

            # if the should_refetch_articles variable is True, we restart the loop.
            if should_refetch_articles:
                continue

            # if the should_stop_pagination variable is True, we break the loop.
            if should_stop_pagination:
                break

            next_page_found = self.go_to_next_page()

            # if there is no next page, we break the loop.
            if not next_page_found:
                break

        return sorted(news, key=lambda x: x.published_at, reverse=True)

    # add function to go to next page if it is possible and if it is not let the caller know
    def go_to_next_page(self) -> bool:
        """Go to the next page of the search results.

        Returns:
            bool: True if the next page was found and clicked, False otherwise.
        """
        next_page_buttons = self.driver.find_elements(By.CSS_SELECTOR, ".search-results-module-next-page")

        if not next_page_buttons:
            return False

        assert len(next_page_buttons) == 1, "More than one next page button found"

        next_page_button = next_page_buttons[0]

        if next_page_button.find_element(By.TAG_NAME, "svg").get_dom_attribute("data-inactive"):
            return False

        try:
            next_page_button.click()
            return True
        except ElementClickInterceptedException:
            return False

    def fetch_articles_on_page_and_make_sure_they_are_not_stale(self) -> list[WebElement]:
        """Fetch the articles on the page and make sure they are not stale.

        Returns:
            list[WebElement]: The list of articles on the page.
        """
        articles = WebDriverWait(self.driver, timeout=5).until(
            EC.visibility_of_all_elements_located((By.CSS_SELECTOR, ".search-results-module-results-menu > li"))
        )

        if is_there_any_stale_web_element(articles):
            return self.fetch_articles_on_page_and_make_sure_they_are_not_stale()

        return articles

    def parse_article(self, article: WebElement) -> Article:
        """Parse an article from the search results page.

        Args:
            article (WebElement): The WebElement representing the article.

        Returns:
            Article: The parsed article.
        """

        category = self.extract_article_category(article)
        title = self.extract_article_title(article)
        description = self.extract_description(article)
        date = self.extract_article_date(article)
        image_url = self.extract_image_url(article)
        image_filepath = None

        if image_url:
            image_filepath = self.download_image(image_url)

        # if the title or description is not found, we raise an error.
        if not title or not description:
            raise ArticleParseError("Title or description not found")

        return Article(
            title=title,
            description=description,
            published_at=date,
            category=category,
            image_url=image_url,
            image_filepath=image_filepath,
        )

    def extract_article_category(self, article: WebElement) -> str | None:
        """Extract the category of an article."""
        try:
            return article.find_element(By.CSS_SELECTOR, ".promo-category").text
        except NoSuchElementException:
            self.logger.error("No category found for the article")
            return None

    def extract_article_title(self, article: WebElement) -> str | None:
        """Extract the title of an article."""
        try:
            return article.find_element(By.CSS_SELECTOR, ".promo-title").text
        except NoSuchElementException:
            self.logger.error("No title found for the article")
            return None

    def extract_description(self, article: WebElement) -> str | None:
        """Extract the description of an article."""
        try:
            return article.find_element(By.CSS_SELECTOR, ".promo-description").text
        except NoSuchElementException:
            self.logger.error("No description found for the article")
            return None

    def extract_article_date(self, article: WebElement) -> datetime:
        """Extract the date of an article. If the date is not found, return the minimum datetime."""
        try:
            timestamp_ns = article.find_element(By.CSS_SELECTOR, ".promo-timestamp").get_dom_attribute("data-timestamp")
            return datetime.fromtimestamp(int(timestamp_ns) / 1000, ZoneInfo("UTC"))
        except NoSuchElementException:
            self.logger.error("No date found for the article")
            return datetime.min

    def extract_image_url(self, article: WebElement) -> str | None:
        """Extract the URL of the image of an article."""
        try:
            return article.find_element(By.CSS_SELECTOR, "img").get_dom_attribute("src")
        except NoSuchElementException:
            self.logger.warning("No image found for the article")
            return None

    def generate_random_filename(self, length: int = 8) -> str:
        """Generate a random filename with a given length."""
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
        extension = image_url.split(".")[-1].lower()

        if extension not in ["jpg", "jpeg", "png", "gif"]:
            extension = "jpg"

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
        """Quit the webdriver."""
        if self._driver:
            self._driver.quit()
