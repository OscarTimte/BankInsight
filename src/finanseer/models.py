from decimal import Decimal
from sqlalchemy import (
    Column,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    TEXT,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

    subcategories = relationship("Subcategory", back_populates="category", cascade="all, delete-orphan")


class Subcategory(Base):
    __tablename__ = "subcategories"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)

    category = relationship("Category", back_populates="subcategories")
    transactions = relationship("Transaction", back_populates="subcategory")

    __table_args__ = (UniqueConstraint("name", "category_id", name="_name_category_uc"),)


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(String(64), primary_key=True, doc="SHA-256 hash for deduplication")
    account_id = Column(String, nullable=False)
    transaction_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False, index=True)
    currency = Column(String(3), nullable=False)
    counterparty_name = Column(String)
    counterparty_iban = Column(String, index=True)
    description_raw = Column(TEXT)
    mutation_type = Column(String, nullable=False)
    bank_source = Column(String, nullable=False)

    subcategory_id = Column(Integer, ForeignKey("subcategories.id"), nullable=True)
    subcategory = relationship("Subcategory", back_populates="transactions")
    # merchant_id = Column(Integer, ForeignKey('merchants.id'), nullable=True, index=True)


# --- Placeholder Tables for Future Epics ---

class Rule(Base):
    __tablename__ = "rules"
    id = Column(Integer, primary_key=True)
    type = Column(String, nullable=False)  # This will store RuleType enum values
    pattern = Column(String, nullable=False, index=True)
    priority = Column(Integer, nullable=False, default=100)
    confidence_base = Column(Numeric(3, 2), nullable=False, default=Decimal("1.00"))

    subcategory_id = Column(Integer, ForeignKey("subcategories.id"), nullable=False)
    subcategory = relationship("Subcategory")


class Budget(Base):
    __tablename__ = "budgets"
    id = Column(Integer, primary_key=True)
    subcategory_id = Column(Integer, ForeignKey("subcategories.id"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    month = Column(Date, nullable=False) # Store as the first day of the month


class Merchant(Base):
    __tablename__ = "merchants"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
