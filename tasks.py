from dataclasses import dataclass
from datetime import date, datetime

from dateutil.relativedelta import relativedelta
from robocorp import workitems
from robocorp.tasks import task
from RPA.Excel.Files import Files
from zoneinfo import ZoneInfo

from models import Article
from scraper import LATimesScraper
from utilities import count_search_query_occurrences, is_there_any_money_amount


def is_not_empty_string(value: str) -> bool:
    return isinstance(value, str) and value.strip()


@dataclass
class OutputRow:
    """Output row to be saved in an Excel file."""

    title: str
    date: date
    description: str
    picture_filename: str
    search_phrase_count: int
    contains_money: bool

    search_query: str
    category: str
    months: int

    def __post_init__(self):
        assert is_not_empty_string(self.title)
        assert isinstance(self.date, date)
        assert is_not_empty_string(self.description)
        assert is_not_empty_string(self.picture_filename)
        assert isinstance(self.search_phrase_count, int) and self.search_phrase_count >= 0
        assert isinstance(self.contains_money, bool)
        assert is_not_empty_string(self.search_query)
        assert is_not_empty_string(self.category)
        assert isinstance(self.months, int) and self.months >= 1

    def to_dict(self):
        return {
            "Title": self.title,
            "Date": self.date.isoformat(),
            "Description": self.description,
            "Picture filename": self.picture_filename,
            "Search phrase count": self.search_phrase_count,
            "Contains money": self.contains_money,
            "Search query": self.search_query,
            "Category": self.category,
            "Months": self.months,
        }


def is_input_payload_valid(payload: dict) -> bool:
    """Validate the input payload."""
    search_query: str = str(payload.get("search_query", ""))
    category: str = str(payload.get("category", ""))
    months: str = str(payload.get("months", ""))

    return (
        # validate that search_query is a non-empty string
        is_not_empty_string(search_query)
        # validate that category is a non-empty string
        and is_not_empty_string(category)
        # validate that months is a positive integer
        and months.isdigit()
        and int(months) >= 0
    )


@task
def scrape_LA_times():
    """Scrape the LA Times website for the latest news based on the input payload from the workitems."""

    for order, item in enumerate(workitems.inputs):
        # Validate the input payload
        if not is_input_payload_valid(item.payload):
            workitems.outputs.create(payload={"status": "error", "error": "Invalid input payload."})
            item.fail("BUSINESS", message="Invalid input payload.")
            continue

        search_query = item.payload.get("search_query")
        category = item.payload.get("category")
        n_months = int(item.payload.get("months"))

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


def create_output_rows(news: list[Article], search_query: str, category: str, n_months: int) -> list[OutputRow]:
    """Create output rows based on the news, search query, category, and number of months."""

    output_rows: list[OutputRow] = []

    for new in news:
        query_count = count_search_query_occurrences(new, search_query)
        contains_money = is_there_any_money_amount(new.title) or is_there_any_money_amount(new.description)

        output_row = OutputRow(
            title=new.title,
            date=new.publication_date,
            description=new.description,
            picture_filename=new.image_filepath,
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
