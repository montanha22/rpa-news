from dataclasses import dataclass
from datetime import datetime
from typing import Optional


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
