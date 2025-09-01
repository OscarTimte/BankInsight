import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional

import pandas as pd
from pydantic import ValidationError
from sqlalchemy.orm import Session

from finanseer import models
from finanseer.schemas import Transaction, MutationType, BudgetCategory

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def _clean_str(value) -> Optional[str]:
    """Cleans a string value from pandas, handling NaN and stripping whitespace."""
    if pd.isna(value) or value is None:
        return None
    return str(value).strip()


def import_rabobank_csv(db: Session, filepath: str):
    """
    Imports transactions from a Rabobank CSV file and persists them to the database.
    Handles duplicates within the same file by skipping them.
    """
    try:
        df = pd.read_csv(
            filepath,
            encoding="latin-1",
            decimal=",",
            thousands=".",
            dtype=str,
        )
    except FileNotFoundError:
        logging.error(f"File not found: {filepath}")
        return
    except Exception as e:
        logging.error(f"Failed to read CSV file {filepath}: {e}")
        return

    transactions_processed = 0
    skipped_rows = 0
    processed_ids = set()

    for index, row in df.iterrows():
        try:
            account_id = _clean_str(row.get("IBAN/BBAN"))
            transaction_date_str = _clean_str(row.get("Datum"))
            amount_str = _clean_str(row.get("Bedrag"))
            currency = _clean_str(row.get("Munt"))

            if not all([account_id, transaction_date_str, amount_str, currency]):
                logging.warning(f"Skipping row {index + 2}: missing essential data.")
                skipped_rows += 1
                continue

            transaction_date = datetime.strptime(transaction_date_str, "%Y-%m-%d").date()
            amount_decimal = Decimal(amount_str.replace(",", "."))
            mutation_type = MutationType.CREDIT if amount_decimal >= 0 else MutationType.DEBIT
            amount_abs = abs(amount_decimal)

            counterparty_iban = _clean_str(row.get("Tegenrekening IBAN/BBAN"))
            counterparty_name = _clean_str(row.get("Naam tegenpartij"))
            desc_parts = [_clean_str(row.get(f"Omschrijving-{i}")) for i in range(1, 4)]
            description_raw = " ".join(p for p in desc_parts if p).strip() or None

            transaction_id = Transaction.generate_id(
                transaction_date=transaction_date,
                amount=amount_abs,
                counterparty_iban=counterparty_iban,
                counterparty_name=counterparty_name,
                description=description_raw,
            )

            if transaction_id in processed_ids:
                logging.warning(f"Skipping duplicate transaction in file (ID: {transaction_id[:8]}...)")
                skipped_rows += 1
                continue

            processed_ids.add(transaction_id)

            db_transaction = models.Transaction(
                id=transaction_id,
                account_id=account_id,
                transaction_date=transaction_date,
                amount=amount_abs,
                currency=currency,
                counterparty_name=counterparty_name,
                counterparty_iban=counterparty_iban,
                description_raw=description_raw,
                mutation_type=mutation_type.value,
                bank_source="Rabobank",
            )
            db.merge(db_transaction)
            transactions_processed += 1

        except (InvalidOperation, ValueError) as e:
            logging.warning(f"Skipping row {index + 2} due to parsing error: {e}")
            skipped_rows += 1
        except Exception as e:
            logging.error(f"An unexpected error occurred at row {index + 2}: {e}")
            skipped_rows += 1

    try:
        db.commit()
        logging.info(f"Successfully synced {transactions_processed} transactions from {filepath} to the database.")
    except Exception as e:
        db.rollback()
        logging.error(f"Failed to commit transactions to DB: {e}")

    if skipped_rows > 0:
        logging.info(f"A total of {skipped_rows} rows were skipped during import.")


def import_budget_categories(db: Session, filepath: str):
    """
    Imports budget category structure from a YNAB-like CSV export and persists to the DB.
    """
    try:
        df = pd.read_csv(filepath, encoding="utf-8-sig", dtype=str)
    except FileNotFoundError:
        logging.error(f"File not found: {filepath}")
        return
    except Exception as e:
        logging.error(f"Failed to read CSV file {filepath}: {e}")
        return

    df.dropna(subset=["Category Group", "Category"], inplace=True)
    df = df[df["Category Group"].str.strip() != ""]

    category_map = {}
    for _, row in df.iterrows():
        group = _clean_str(row["Category Group"])
        subcategory = _clean_str(row["Category"])
        if group and group not in category_map:
            category_map[group] = set()
        if group and subcategory:
            category_map[group].add(subcategory)

    for cat_name, sub_names in category_map.items():
        category_orm = db.query(models.Category).filter(models.Category.name == cat_name).first()
        if not category_orm:
            category_orm = models.Category(name=cat_name)
            db.add(category_orm)
            db.flush()

        for sub_name in sub_names:
            subcategory_orm = (
                db.query(models.Subcategory)
                .filter(models.Subcategory.name == sub_name, models.Subcategory.category_id == category_orm.id)
                .first()
            )
            if not subcategory_orm:
                db.add(models.Subcategory(name=sub_name, category_id=category_orm.id))

    try:
        db.commit()
        logging.info(f"Successfully synced {len(category_map)} budget categories from {filepath}.")
    except Exception as e:
        db.rollback()
        logging.error(f"Failed to commit budget categories to DB: {e}")
