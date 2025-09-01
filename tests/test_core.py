from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finanseer.models import Base, Transaction, Category, Subcategory
from finanseer.core import get_uncategorized_transactions, get_all_categories, set_category_for_transactions, get_transactions_by_text


@pytest.fixture(scope="function")
def db_session_with_data():
    """Create a new in-memory DB session and populate it with test data."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()

    # Create categories
    cat_bills = Category(name="Bills")
    cat_food = Category(name="Food")
    session.add_all([cat_bills, cat_food])
    session.commit()

    sub_rent = Subcategory(name="Rent", category_id=cat_bills.id)
    sub_groceries = Subcategory(name="Groceries", category_id=cat_food.id)
    session.add_all([sub_rent, sub_groceries])
    session.commit()

    # Create transactions
    today = date.today()
    t1 = Transaction(id="t1", account_id="A1", transaction_date=today, amount=Decimal("10.00"), currency="EUR", mutation_type="debit", bank_source="TestBank", subcategory_id=sub_rent.id)
    t2 = Transaction(id="t2", account_id="A1", transaction_date=today - timedelta(days=1), amount=Decimal("20.00"), currency="EUR", mutation_type="debit", bank_source="TestBank")
    t3 = Transaction(id="t3", account_id="A1", transaction_date=today - timedelta(days=2), amount=Decimal("30.00"), currency="EUR", mutation_type="debit", bank_source="TestBank")
    session.add_all([t1, t2, t3])
    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(engine)

def test_get_uncategorized_transactions(db_session_with_data):
    """Test that only transactions without a category are returned."""
    uncategorized = get_uncategorized_transactions(db_session_with_data)

    assert len(uncategorized) == 2
    assert uncategorized[0].id == "t2" # Most recent
    assert uncategorized[1].id == "t3"
    assert all(t.subcategory_id is None for t in uncategorized)

def test_get_uncategorized_transactions_sorted_by_amount(db_session_with_data):
    """Test that transactions are correctly sorted by amount."""
    uncategorized = get_uncategorized_transactions(db_session_with_data, sort_by="amount")

    assert len(uncategorized) == 2
    assert uncategorized[0].id == "t3" # 30.00 is the highest amount
    assert uncategorized[1].id == "t2" # 20.00 is the second highest

def test_get_transactions_by_text(db_session_with_data):
    """Test finding transactions by a text pattern."""
    # Add more specific test data
    t4 = Transaction(id="t4", account_id="A1", transaction_date=date.today(), amount=Decimal("100.00"), currency="EUR", mutation_type="debit", bank_source="TestBank", counterparty_name="UNIQUE_PAYEE")
    t5_categorized = Transaction(id="t5", account_id="A1", transaction_date=date.today(), amount=Decimal("200.00"), currency="EUR", mutation_type="debit", bank_source="TestBank", description_raw="unique_description", subcategory_id=1)
    db_session_with_data.add_all([t4, t5_categorized])
    db_session_with_data.commit()

    # Test search by counterparty name (case-insensitive)
    results = get_transactions_by_text(db_session_with_data, "unique_payee")
    assert len(results) == 1
    assert results[0].id == "t4"

    # Test that it doesn't find categorized transactions
    results_categorized = get_transactions_by_text(db_session_with_data, "unique_description")
    assert len(results_categorized) == 0

    # Test no results found
    results_none = get_transactions_by_text(db_session_with_data, "nonexistent")
    assert len(results_none) == 0

def test_get_all_categories(db_session_with_data):
    """Test fetching all categories and their subcategories."""
    categories = get_all_categories(db_session_with_data)

    assert len(categories) == 2
    bills = next(c for c in categories if c.name == "Bills")
    food = next(c for c in categories if c.name == "Food")

    assert len(bills.subcategories) == 1
    assert bills.subcategories[0].name == "Rent"
    assert len(food.subcategories) == 1
    assert food.subcategories[0].name == "Groceries"

def test_set_category_for_transactions(db_session_with_data):
    """Test assigning a category to one or more transactions."""
    # First, get the uncategorized transactions
    uncategorized_before = get_uncategorized_transactions(db_session_with_data)
    assert len(uncategorized_before) == 2

    # Get the ID of the subcategory to assign
    groceries_sub = db_session_with_data.query(Subcategory).filter(Subcategory.name == "Groceries").one()

    # Assign the category to one transaction
    set_category_for_transactions(db_session_with_data, ["t2"], groceries_sub.id)

    # Verify
    t2_updated = db_session_with_data.query(Transaction).filter(Transaction.id == "t2").one()
    assert t2_updated.subcategory_id == groceries_sub.id

    # Check that there is one less uncategorized transaction
    uncategorized_after = get_uncategorized_transactions(db_session_with_data)
    assert len(uncategorized_after) == 1
    assert uncategorized_after[0].id == "t3"
