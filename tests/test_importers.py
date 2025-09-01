import io
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finanseer.models import Base, Transaction, Category, Subcategory
from finanseer.importers import import_rabobank_csv, import_budget_categories

# In-memory SQLite database for testing
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def db_session():
    """Create a new database session for a test."""
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


RABO_CSV_CONTENT = """
"IBAN/BBAN","Munt","BIC","Volgnr","Datum","Rentedatum","Bedrag","Saldo na trn","Tegenrekening IBAN/BBAN","Naam tegenpartij","Naam uiteindelijke partij","Naam initiërende partij","BIC tegenpartij","Code","Batch ID","Transactiereferentie","Machtigingskenmerk","Incassant ID","Betalingskenmerk","Omschrijving-1","Omschrijving-2","Omschrijving-3"
"NL01RABO0123456789","EUR","RABONL2U","1","2024-01-01","2024-01-01","-10,50","+100,00","NL02RABO0987654321","Test Payee","","","","","","","","","","Test omschrijving 1","",""
"NL01RABO0123456789","EUR","RABONL2U","2","2024-01-02","2024-01-02","+25,00","+125,00","NL03RABO0112233445","Test Payer","","","","","","","","","","Test omschrijving 2","",""
"NL01RABO0123456789","EUR","RABONL2U","3","2024-01-01","2024-01-01","-10,50","+114,50","NL02RABO0987654321","Test Payee","","","","","","","","","","Test omschrijving 1","",""
"""

def test_import_rabobank_csv_success(db_session, tmp_path):
    # GIVEN a valid Rabobank CSV content in a temporary file
    csv_file = tmp_path / "rabo.csv"
    csv_file.write_text(RABO_CSV_CONTENT)

    # WHEN importing the data
    import_rabobank_csv(db_session, str(csv_file))

    # THEN the transactions should be in the database
    transactions = db_session.query(Transaction).all()
    assert len(transactions) == 2 # 3 rows, but 1 is a duplicate

    # Check the first transaction
    t1 = db_session.query(Transaction).filter(Transaction.transaction_date == date(2024, 1, 1)).one()
    assert t1.amount == Decimal("10.50")
    assert t1.mutation_type == "debit"
    assert t1.counterparty_name == "Test Payee"
    assert t1.description_raw == "Test omschrijving 1"

    # Check the second transaction
    t2 = db_session.query(Transaction).filter(Transaction.transaction_date == date(2024, 1, 2)).one()
    assert t2.amount == Decimal("25.00")
    assert t2.mutation_type == "credit"


BUDGET_CSV_CONTENT = """
"Account","Category Group/Category","Category Group","Category"
"Test Account","Bills: Rent","Bills","Rent"
"Test Account","Bills: Utilities","Bills","Utilities"
"Test Account","Groceries: Supermarket","Groceries","Supermarket"
"Test Account","Bills: Rent","Bills","Rent"
"""

def test_import_budget_categories_success(db_session, tmp_path):
    # GIVEN a valid budget CSV content in a temporary file
    csv_file = tmp_path / "budget.csv"
    csv_file.write_text(BUDGET_CSV_CONTENT)

    # WHEN importing the budget categories
    import_budget_categories(db_session, str(csv_file))

    # THEN the categories and subcategories should be in the database
    categories = db_session.query(Category).order_by(Category.name).all()
    assert len(categories) == 2
    assert categories[0].name == "Bills"
    assert categories[1].name == "Groceries"

    bills_subs = db_session.query(Subcategory).filter(Subcategory.category_id == categories[0].id).all()
    assert len(bills_subs) == 2
    assert {s.name for s in bills_subs} == {"Rent", "Utilities"}
