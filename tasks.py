from dataclasses import dataclass
from datetime import datetime, date

from dateutil.relativedelta import relativedelta
from robocorp import workitems
from robocorp.tasks import task
from RPA.Excel.Files import Files
from zoneinfo import ZoneInfo

from scraper import LATimesScraper
from utilities import count_search_query_occurrences, is_there_any_money_amount


@dataclass
class OutputRow:
    title: str
    date: date
    description: str
    picture_filename: str
    search_phrase_count: int
    contains_money: bool

    search_query: str
    category: str
    months: int

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


@task
def scrape_LA_times():
    for order, item in enumerate(workitems.inputs):
        search_query = item.payload.get("search_query")
        category = item.payload.get("category")
        n_months = int(item.payload.get("months"))

        n_months = max(n_months, 1)

        scraper = LATimesScraper()
        scraper.set_webdriver()
        scraper.open_homepage()
        scraper.search_for(search_query)
        scraper.filter_by_category(category)

        current_month = datetime.now(ZoneInfo("UTC")).date().replace(day=1)
        min_date = current_month - relativedelta(months=(n_months - 1))
        news = scraper.get_news(min_date)
        scraper.driver_quit()

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

        excel = Files()
        excel.create_workbook(f"output/search_results_{order}.xlsx")
        excel.append_rows_to_worksheet(content=[row.to_dict() for row in output_rows])
        excel.save_workbook()
