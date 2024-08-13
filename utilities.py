import re

from scraper import Article


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
    # matches: 1 | 11 | 111 | 1.1 | 11.1 | 111.1 | 1,111.1 | 11,111.11
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


def count_search_query(text: str, search_query: str) -> int:
    if not search_query:
        return 0
    return text.lower().count(search_query.lower())


def count_search_query_occurrences(article: Article, search_query: str) -> int:
    return count_search_query(article.title, search_query) + count_search_query(article.description, search_query)
