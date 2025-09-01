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

from finanseer.models import Rule
from finanseer.schemas import RuleType
from finanseer.core import apply_rules

def test_apply_rules_iban(db_session_with_data):
    """Test that a transaction is categorized by an IBAN rule."""
    session = db_session_with_data
    # Add a transaction with a specific IBAN
    t_iban = Transaction(id="t_iban", account_id="A1", transaction_date=date.today(), amount=Decimal("50.00"), currency="EUR", counterparty_iban="NL66INGB0001234567", mutation_type="debit", bank_source="Test")
    session.add(t_iban)
    # Get a subcategory to assign
    sub_rent = session.query(Subcategory).filter(Subcategory.name == "Rent").one()
    # Create the rule
    rule = Rule(type=RuleType.IBAN.value, pattern="NL66INGB0001234567", subcategory_id=sub_rent.id, priority=10)
    session.add(rule)
    session.commit()

    # Apply rules
    count = apply_rules(session)
    assert count == 1

    # Verify the transaction is categorized
    t_iban_updated = session.query(Transaction).filter(Transaction.id == "t_iban").one()
    assert t_iban_updated.subcategory_id == sub_rent.id

def test_apply_rules_counterparty_name(db_session_with_data):
    """Test categorization by a counterparty name rule."""
    session = db_session_with_data
    t_cp = Transaction(id="t_cp", account_id="A1", transaction_date=date.today(), amount=Decimal("75.00"), currency="EUR", counterparty_name="CoolBlue BV", mutation_type="debit", bank_source="Test")
    session.add(t_cp)
    sub_groceries = session.query(Subcategory).filter(Subcategory.name == "Groceries").one()
    rule = Rule(type=RuleType.COUNTERPARTY_NAME.value, pattern="coolblue", subcategory_id=sub_groceries.id, priority=10)
    session.add(rule)
    session.commit()

    count = apply_rules(session)
    assert count == 1
    t_cp_updated = session.query(Transaction).filter(Transaction.id == "t_cp").one()
    assert t_cp_updated.subcategory_id == sub_groceries.id

def test_apply_rules_description_contains(db_session_with_data):
    """Test categorization by a description contains rule."""
    session = db_session_with_data
    t_desc = Transaction(id="t_desc", account_id="A1", transaction_date=date.today(), amount=Decimal("80.00"), currency="EUR", description_raw="Online payment to Amazon.com", mutation_type="debit", bank_source="Test")
    session.add(t_desc)
    sub_groceries = session.query(Subcategory).filter(Subcategory.name == "Groceries").one()
    rule = Rule(type=RuleType.DESCRIPTION_CONTAINS.value, pattern="amazon", subcategory_id=sub_groceries.id, priority=10)
    session.add(rule)
    session.commit()

    count = apply_rules(session)
    assert count == 1
    t_desc_updated = session.query(Transaction).filter(Transaction.id == "t_desc").one()
    assert t_desc_updated.subcategory_id == sub_groceries.id

def test_apply_rules_priority(db_session_with_data):
    """Test that a higher priority rule (lower number) is chosen over a lower priority one."""
    session = db_session_with_data
    t_priority = Transaction(id="t_prio", account_id="A1", transaction_date=date.today(), amount=Decimal("100.00"), currency="EUR", counterparty_name="Albert Heijn", mutation_type="debit", bank_source="Test")
    session.add(t_priority)

    sub_rent = session.query(Subcategory).filter(Subcategory.name == "Rent").one()
    sub_groceries = session.query(Subcategory).filter(Subcategory.name == "Groceries").one()

    # Conflicting rules
    rule_low_prio = Rule(type=RuleType.COUNTERPARTY_NAME.value, pattern="albert heijn", subcategory_id=sub_rent.id, priority=100)
    rule_high_prio = Rule(type=RuleType.COUNTERPARTY_NAME.value, pattern="albert heijn", subcategory_id=sub_groceries.id, priority=10)
    session.add_all([rule_low_prio, rule_high_prio])
    session.commit()

    count = apply_rules(session)
    assert count == 1
    t_prio_updated = session.query(Transaction).filter(Transaction.id == "t_prio").one()
    # Should be categorized as Groceries due to higher priority
    assert t_prio_updated.subcategory_id == sub_groceries.id

def test_apply_rules_dry_run(db_session_with_data):
    """Test that dry_run simulates changes without committing them."""
    session = db_session_with_data
    t_dry = Transaction(id="t_dry", account_id="A1", transaction_date=date.today(), amount=Decimal("50.00"), currency="EUR", counterparty_iban="NL66INGB0001234567", mutation_type="debit", bank_source="Test")
    session.add(t_dry)
    sub_rent = session.query(Subcategory).filter(Subcategory.name == "Rent").one()
    rule = Rule(type=RuleType.IBAN.value, pattern="NL66INGB0001234567", subcategory_id=sub_rent.id, priority=10)
    session.add(rule)
    session.commit()

    # Apply rules with dry_run=True
    count = apply_rules(session, dry_run=True)
    assert count == 1

    # Verify the transaction is NOT categorized in the session
    session.expire_all() # Ensure we get fresh data from the DB
    t_dry_updated = session.query(Transaction).filter(Transaction.id == "t_dry").one()
    assert t_dry_updated.subcategory_id is None

def test_apply_rules_no_match(db_session_with_data):
    """Test that no changes are made if no rules match."""
    session = db_session_with_data
    # Use one of the existing uncategorized transactions
    t2 = session.query(Transaction).filter(Transaction.id == "t2").one()
    assert t2.subcategory_id is None

    # Add a rule that won't match
    sub_rent = session.query(Subcategory).filter(Subcategory.name == "Rent").one()
    rule = Rule(type=RuleType.IBAN.value, pattern="NON_EXISTENT_IBAN", subcategory_id=sub_rent.id, priority=10)
    session.add(rule)
    session.commit()

    count = apply_rules(session)
    assert count == 0

    # Verify the transaction is still uncategorized
    t2_updated = session.query(Transaction).filter(Transaction.id == "t2").one()
    assert t2_updated.subcategory_id is None
