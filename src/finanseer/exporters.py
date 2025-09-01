import logging
import pandas as pd
from sqlalchemy.orm import Session

from finanseer.models import Transaction, Subcategory, Category

def export_transactions_to_ynab_csv(db: Session, filepath: str):
    """
    Exports all transactions from the database to a YNAB-compatible CSV file.

    Args:
        db: The database session.
        filepath: The path for the output CSV file.
    """
    logging.info(f"Starting export of transactions to {filepath}...")

    # Query all transactions, joining with categories to get category names
    transactions_query = (
        db.query(Transaction, Category.name, Subcategory.name)
        .outerjoin(Transaction.subcategory)
        .outerjoin(Subcategory.category)
        .order_by(Transaction.transaction_date)
        .all()
    )

    if not transactions_query:
        logging.info("No transactions found in the database to export.")
        return

    records = []
    for transaction, cat_name, sub_name in transactions_query:
        # Format category string as "Category: Subcategory"
        category_str = f"{cat_name}: {sub_name}" if cat_name and sub_name else ""

        outflow = None
        inflow = None
        if transaction.mutation_type == 'debit':
            # Format as a string with a dot decimal separator for CSV consistency
            outflow = f"{transaction.amount:.2f}"
        else:
            inflow = f"{transaction.amount:.2f}"

        records.append({
            'Date': transaction.transaction_date.strftime('%m/%d/%Y'), # YNAB likes MM/DD/YYYY
            'Payee': transaction.counterparty_name,
            'Memo': transaction.description_raw,
            'Outflow': outflow,
            'Inflow': inflow,
            'Category': category_str,
        })

    df = pd.DataFrame(records)

    try:
        df.to_csv(filepath, index=False, encoding='utf-8')
        logging.info(f"Successfully exported {len(df)} transactions to {filepath}")
    except Exception as e:
        logging.error(f"Failed to write to CSV file {filepath}: {e}")
