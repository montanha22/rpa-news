from datetime import date, datetime
from typing import Any

from dateutil.relativedelta import relativedelta
from robocorp import workitems
from robocorp.tasks import task
from RPA.Excel.Files import Files
from zoneinfo import ZoneInfo

from models import Article, OutputRow
from scraper import LATimesScraper
from utilities import is_empty_string, is_not_string


def validate_input_payload(payload: dict) -> tuple[bool, str]:
    """Validate the input payload.

    Args:
        payload (dict): The input payload.

    Returns:
        tuple[bool, str]: A tuple with a boolean indicating if the payload is valid and an error message.
    """

    search_query: str = payload.get("search_query")
    category: str = payload.get("category")
    months: Any = payload.get("months")

    if search_query is None or is_not_string(search_query) or is_empty_string(search_query):
        return (False, "The search query is required and should be a non-empty string.")

    if category is not None and (
        is_not_string(category)  # wrong type
        or is_empty_string(category)  # empty string
    ):
        return (False, "If provided, the category should be a non-empty string.")

    if months is not None:
        if not isinstance(months, int):
            return (False, "If provided, the number of months should be a positive integer.")

        if months < 0:
            return (False, "If provided, the number of months should be a positive integer.")

    return (True, "")


@task
def scrape_LA_times():
    """Scrape the LA Times website for the latest news based on the input payload from the workitems.

    The input payload should contain the following

    - search_query: The search query to use. It should be a non-empty string.

    - category:     The category to filter the news. If not provided, all categories are considered.

    - months:       The number of months to consider. It should be a positive integer.
                    If not provided, the current month is considered.
    """

    for order, item in enumerate(workitems.inputs):
        # Validate the input payload
        valid, error_message = validate_input_payload(item.payload)
        if not valid:
            workitems.outputs.create(payload={"status": "error", "error": error_message})
            item.fail("BUSINESS", message=error_message)
            continue

        search_query = item.payload.get("search_query")
        category = item.payload.get("category")
        n_months = int(item.payload.get("months") or 1)

        # Ensure that the number of months is at least 1 (current month)
        n_months = max(n_months, 1)

        # Get the latest news based on the search query, category, and number of months.
        news = get_la_times_latest_news(search_query, category, n_months)

        # Create output rows to be saved in an Excel file.
        output_rows = create_output_rows(news, search_query, category, n_months)

        # Save the output rows in an Excel file.
        excel_output_filepath = f"output/search_results_{order}.xlsx"

        excel = Files()
        excel.create_workbook(excel_output_filepath)
        excel.append_rows_to_worksheet(content=[row.to_dict() for row in output_rows], header=True)
        excel.save_workbook()

        # Create workitem outputs
        image_files = [row.picture_filename for row in output_rows if row.picture_filename]
        workitems.outputs.create(
            payload={
                "status": "success",
                "excel_output_filepath": excel_output_filepath,
                "search_query": search_query,
                "category": category,
                "months": n_months,
                "image_files": image_files,
            },
            files=[excel_output_filepath] + image_files,
        )


def compute_minimum_publication_date(n_months: int) -> date:
    """Compute the minimum date for the search based on the number of months."""
    current_month = datetime.now(ZoneInfo("UTC")).date().replace(day=1)
    return current_month - relativedelta(months=(n_months - 1))


def create_output_rows(articles: list[Article], search_query: str, category: str, n_months: int) -> list[OutputRow]:
    """Create output rows based on the news, search query, category, and number of months."""

    output_rows: list[OutputRow] = []

    for article in articles:
        query_count = article.count_search_query_occurrences(search_query)
        contains_money = article.is_there_any_money_amount()

        output_row = OutputRow(
            title=article.title,
            date=article.publication_date,
            description=article.description,
            picture_filename=article.image_filepath,
            search_phrase_count=query_count,
            contains_money=contains_money,
            search_query=search_query,
            category=category,
            months=n_months,
        )
        output_rows.append(output_row)

    return output_rows


def get_la_times_latest_news(search_query: str, category: str, n_months: int) -> list[Article]:
    """Get the latest news based on the search query, category, and number of months.

    Args:
        search_query (str): The search query to use.
        category (str): The category to filter the news.
        n_months (int): The number of months to consider.

    Returns:
        list[Article]: The list of articles found.
    """
    scraper = LATimesScraper()

    scraper.set_webdriver()

    scraper.open_homepage()
    scraper.search_for(search_query)
    scraper.filter_by_category(category)

    min_date = compute_minimum_publication_date(n_months)
    news = scraper.get_news(min_date)

    scraper.driver_quit()

    return news
