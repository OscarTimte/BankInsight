from datetime import date
from decimal import Decimal

from finanseer.schemas import Transaction

def test_transaction_generate_id_is_deterministic():
    """
    Tests that generating an ID for the same data twice produces the same hash.
    """
    t_date = date(2024, 1, 1)
    amount = Decimal("10.50")
    counterparty_iban = "NL01RABO0123456789"
    counterparty_name = "Test Payee"
    description = "Test Description"

    id1 = Transaction.generate_id(t_date, amount, counterparty_iban, counterparty_name, description)
    id2 = Transaction.generate_id(t_date, amount, counterparty_iban, counterparty_name, description)

    assert id1 == id2

def test_transaction_generate_id_handles_whitespace():
    """
    Tests that leading/trailing whitespace in fields does not affect the hash.
    """
    t_date = date(2024, 1, 1)
    amount = Decimal("10.50")

    id1 = Transaction.generate_id(
        t_date, amount, " NL01RABO0123456789 ", " Test Payee ", " Test Description "
    )
    id2 = Transaction.generate_id(
        t_date, amount, "NL01RABO0123456789", "Test Payee", "Test Description"
    )

    assert id1 == id2

def test_transaction_generate_id_is_sensitive_to_changes():
    """
    Tests that any change in the key fields results in a different hash.
    """
    t_date = date(2024, 1, 1)
    amount = Decimal("10.50")
    counterparty_iban = "NL01RABO0123456789"
    counterparty_name = "Test Payee"
    description = "Test Description"

    base_id = Transaction.generate_id(t_date, amount, counterparty_iban, counterparty_name, description)

    # Change date
    id_date_change = Transaction.generate_id(date(2024, 1, 2), amount, counterparty_iban, counterparty_name, description)
    assert base_id != id_date_change

    # Change amount
    id_amount_change = Transaction.generate_id(t_date, Decimal("10.51"), counterparty_iban, counterparty_name, description)
    assert base_id != id_amount_change

    # Change counterparty
    id_counterparty_change = Transaction.generate_id(t_date, amount, "NL02...", counterparty_name, description)
    assert base_id != id_counterparty_change

    # Change description
    id_desc_change = Transaction.generate_id(t_date, amount, counterparty_iban, counterparty_name, "Different Description")
    assert base_id != id_desc_change
