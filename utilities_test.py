from utilities import count_search_query, is_there_any_money_amount


def test_valid_money_amounts():
    assert is_there_any_money_amount("The price is $11.1")
    assert is_there_any_money_amount("The total amount is $111,111.11")
    assert is_there_any_money_amount("The price is 11 dollars")
    assert is_there_any_money_amount("The cost is 11 USD")
    assert is_there_any_money_amount("Price: $0.99")


def test_invalid_money_amounts():
    assert not is_there_any_money_amount("The price is $")
    assert not is_there_any_money_amount("The price is 11")
    assert not is_there_any_money_amount("The price is eleven dollars")
    assert not is_there_any_money_amount("The price is 11.11")
    assert not is_there_any_money_amount("The cost is twenty dollars")


def test_edge_cases():
    assert not is_there_any_money_amount("")
    assert is_there_any_money_amount("11usd")
    assert is_there_any_money_amount("Price is $10000")
    assert is_there_any_money_amount("The price is $123,456.78, that's a lot!")
    assert is_there_any_money_amount("The cost of the item is 50 USD. Is it enough?")


def test_count_search_query():
    # Test cases where the search query is present multiple times
    assert count_search_query("Hello world, hello Universe", "hello") == 2
    assert count_search_query("This is a test. This is only a test.", "test") == 2

    # Test cases where the search query is present once
    assert count_search_query("The quick brown fox", "fox") == 1
    assert count_search_query("Python is fun", "fun") == 1

    # Test cases where the search query is not present
    assert count_search_query("The quick brown fox", "cat") == 0
    assert count_search_query("No matches here", "example") == 0

    # Case with an empty search query
    assert count_search_query("Any text here", "") == 0

    # Case with an empty text
    assert count_search_query("", "search") == 0

    # Case with empty text and search query
    assert count_search_query("", "") == 0

    # Case with case insensitivity
    assert count_search_query("Python PYTHON python", "python") == 3

    # Edge case with special characters
    assert count_search_query("!@# $%^ &*() !@#", "!@#") == 2
    assert count_search_query("!! !! !! !!", "!!") == 4

    # Case with a very long text and search query
    long_text = "word " * 1000  # "word" repeated 1000 times
    assert count_search_query(long_text, "word") == 1000
