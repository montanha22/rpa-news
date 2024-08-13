from datetime import datetime

from dateutil.relativedelta import relativedelta
from robocorp.tasks import task
from zoneinfo import ZoneInfo

from scraper import LATimesScraper


@task
def minimal_task():
    print("oi")
    search_query = "Golf"
    category = "greenspace"
    n_months = 1

    n_months = max(n_months, 1)

    scraper = LATimesScraper()
    scraper.set_webdriver()
    scraper.open_homepage()
    scraper.search_for(search_query)
    scraper.filter_by_category(category)

    current_month = datetime.now(ZoneInfo("UTC")).date().replace(day=1)
    min_date = current_month - relativedelta(months=(n_months - 1))
    news = scraper.get_news(search_query, min_date)

    for n in news:
        print(n)

    print(f"Found {len(news)} articles")

    scraper.driver_quit()
