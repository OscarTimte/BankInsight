import hashlib
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class MutationType(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class Transaction(BaseModel):
    """A uniform, internal representation of a bank transaction."""

    id: str = Field(..., description="A unique hash identifying the transaction for deduplication.")
    account_id: str = Field(..., description="The IBAN of the account holder.")
    transaction_date: date = Field(..., description="The date the transaction occurred.")
    amount: Decimal = Field(..., description="The transaction amount.")
    currency: str = Field(..., description="The currency of the transaction (e.g., EUR).")
    counterparty_name: Optional[str] = Field(None, description="The name of the counterparty.")
    counterparty_iban: Optional[str] = Field(None, description="The IBAN of the counterparty.")
    description_raw: Optional[str] = Field(None, description="The raw, combined description from the bank.")
    mutation_type: MutationType = Field(..., description="The type of mutation (debit or credit).")
    bank_source: str = Field(..., description="The source bank (e.g., Rabobank).")

    @field_validator("amount")
    @classmethod
    def amount_must_be_two_decimal_places(cls, v: Decimal) -> Decimal:
        """Ensure the amount is quantized to two decimal places."""
        return v.quantize(Decimal("0.01"))

    @staticmethod
    def generate_id(
        transaction_date: date,
        amount: Decimal,
        counterparty_iban: Optional[str],
        counterparty_name: Optional[str],
        description: Optional[str],
    ) -> str:
        """
        Generates a unique ID hash for deduplication purposes.
        Based on date, amount, counterparty (IBAN or name), and raw description.
        """
        # Use IBAN if available, otherwise name. Fallback to empty string.
        counterparty_id = counterparty_iban or counterparty_name or ""

        data_to_hash = (
            f"{transaction_date.isoformat()}"
            f"{amount.quantize(Decimal('0.01'))}"
            f"{counterparty_id.strip()}"
            f"{description.strip() if description else ''}"
        )
        return hashlib.sha256(data_to_hash.encode("utf-8")).hexdigest()


class BudgetCategory(BaseModel):
    """Represents a main budget category with its subcategories."""
    name: str
    subcategories: set[str] = Field(default_factory=set)
