from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from utilities import count_search_query, is_there_any_money_amount, string_has_value


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

    def __hash__(self) -> int:
        return hash((self.title, self.published_at.isoformat()))

    def __eq__(self, other) -> bool:
        return self.title == other.title and self.published_at == other.published_at

    def count_search_query_occurrences(self, search_query: str) -> int:
        """Count the number of occurrences of the search query in the article title and description."""
        title_count = count_search_query(self.title, search_query)
        description_count = count_search_query(self.description, search_query)
        return title_count + description_count

    def is_there_any_money_amount(self) -> bool:
        """Check if there is any money amount in the article title or description."""
        return is_there_any_money_amount(self.title) or is_there_any_money_amount(self.description)


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
        assert string_has_value(self.title)
        assert isinstance(self.date, date)
        assert string_has_value(self.description)
        assert string_has_value(self.picture_filename)
        assert isinstance(self.search_phrase_count, int) and self.search_phrase_count >= 0
        assert isinstance(self.contains_money, bool)
        assert string_has_value(self.search_query)
        assert self.category is None or string_has_value(self.category)
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
