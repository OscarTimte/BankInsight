import logging
from typing import List

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from . import models


def get_uncategorized_transactions(db: Session, sort_by: str = "date") -> List[models.Transaction]:
    """
    Fetches all transactions that have not yet been assigned a subcategory.

    Args:
        db: The database session.
        sort_by: The field to sort by ('date' or 'amount').

    Returns:
        A list of uncategorized Transaction objects, sorted as specified.
    """
    logging.info(f"Fetching uncategorized transactions, sorting by {sort_by}...")

    query = db.query(models.Transaction).filter(models.Transaction.subcategory_id.is_(None))

    if sort_by == "amount":
        query = query.order_by(models.Transaction.amount.desc())
    else: # Default to date
        query = query.order_by(models.Transaction.transaction_date.desc())

    transactions = query.all()

    logging.info(f"Found {len(transactions)} uncategorized transactions.")
    return transactions


def get_all_categories(db: Session) -> List[models.Category]:
    """
    Fetches all categories and their subcategories from the database,
    eagerly loading the subcategories to prevent N+1 query issues.

    Args:
        db: The database session.

    Returns:
        A list of all Category objects, with their subcategories pre-loaded.
    """
    logging.info("Fetching all categories...")
    categories = (
        db.query(models.Category)
        .options(joinedload(models.Category.subcategories))
        .order_by(models.Category.name)
        .all()
    )
    logging.info(f"Found {len(categories)} categories.")
    return categories


def get_transactions_by_text(db: Session, text_pattern: str) -> List[models.Transaction]:
    """
    Finds uncategorized transactions that contain a given text pattern in their
    counterparty name or description.

    Args:
        db: The database session.
        text_pattern: The case-insensitive text to search for.

    Returns:
        A list of matching uncategorized transaction objects.
    """
    logging.info(f"Searching for uncategorized transactions matching '%{text_pattern}%'...")

    pattern = f"%{text_pattern}%"
    transactions = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.subcategory_id.is_(None),
            or_(
                models.Transaction.counterparty_name.ilike(pattern),
                models.Transaction.description_raw.ilike(pattern),
            ),
        )
        .order_by(models.Transaction.transaction_date.desc())
        .all()
    )

    logging.info(f"Found {len(transactions)} matching transactions.")
    return transactions


def set_category_for_transactions(db: Session, transaction_ids: List[str], subcategory_id: int):
    """
    Assigns a subcategory to a list of transactions.

    Args:
        db: The database session.
        transaction_ids: A list of transaction IDs to update.
        subcategory_id: The ID of the subcategory to assign.
    """
    # Verify the subcategory exists
    subcategory = db.query(models.Subcategory).filter(models.Subcategory.id == subcategory_id).first()
    if not subcategory:
        logging.error(f"No subcategory found with ID {subcategory_id}. Aborting.")
        return

    logging.info(f"Assigning category '{subcategory.category.name}: {subcategory.name}' to {len(transaction_ids)} transactions.")

    # Update transactions
    (
        db.query(models.Transaction)
        .filter(models.Transaction.id.in_(transaction_ids))
        .update({"subcategory_id": subcategory_id}, synchronize_session=False)
    )

    try:
        db.commit()
        logging.info("Successfully updated transactions.")
    except Exception as e:
        db.rollback()
        logging.error(f"Failed to update transactions in DB: {e}")


def add_rule(db: Session, type: str, pattern: str, subcategory_id: int, priority: int = 100):
    """
    Creates a new rule and adds it to the database.

    Args:
        db: The database session.
        type: The type of the rule (e.g., 'iban', 'description_contains').
        pattern: The pattern to match.
        subcategory_id: The subcategory to assign on a match.
        priority: The priority of the rule.
    """
    # Verify the subcategory exists
    subcategory = db.query(models.Subcategory).filter(models.Subcategory.id == subcategory_id).first()
    if not subcategory:
        logging.error(f"No subcategory found with ID {subcategory_id}. Rule not created.")
        return

    logging.info(f"Adding new rule: TYPE={type}, PATTERN='{pattern}', CATEGORY='{subcategory.category.name}: {subcategory.name}', PRIO={priority}")

    new_rule = models.Rule(
        type=type,
        pattern=pattern,
        subcategory_id=subcategory_id,
        priority=priority,
    )
    db.add(new_rule)

    try:
        db.commit()
        logging.info("Successfully added new rule.")
    except Exception as e:
        db.rollback()
        logging.error(f"Failed to add rule to DB: {e}")


def apply_rules(db: Session, dry_run: bool = False) -> int:
    """
    Applies all active rules to uncategorized transactions.

    Args:
        db: The database session.
        dry_run: If True, no changes will be committed to the database.

    Returns:
        The number of transactions that were categorized.
    """
    from .text_processing import normalize_description
    from .schemas import RuleType

    logging.info(f"Starting rule application process. Dry run: {dry_run}")

    rules = db.query(models.Rule).order_by(models.Rule.priority).all()
    if not rules:
        logging.warning("No rules found in the database. Aborting.")
        return 0

    transactions = get_uncategorized_transactions(db)
    if not transactions:
        logging.info("No uncategorized transactions to process.")
        return 0

    categorized_count = 0
    for t in transactions:
        for rule in rules:
            matched = False
            # Check for match based on rule type
            if rule.type == RuleType.IBAN.value and t.counterparty_iban == rule.pattern:
                matched = True
            elif rule.type == RuleType.COUNTERPARTY_NAME.value and t.counterparty_name and rule.pattern.lower() in t.counterparty_name.lower():
                matched = True
            elif rule.type == RuleType.DESCRIPTION_CONTAINS.value and t.description_raw:
                normalized_desc = normalize_description(t.description_raw)
                if rule.pattern.lower() in normalized_desc:
                    matched = True

            if matched:
                categorized_count += 1
                if dry_run:
                    logging.info(
                        f"[Dry Run] Transaction '{t.id[:8]}...' ({t.counterparty_name}) would be categorized as "
                        f"'{rule.subcategory.category.name}: {rule.subcategory.name}' by rule ID {rule.id} (pattern: '{rule.pattern}')."
                    )
                else:
                    logging.info(
                        f"Transaction '{t.id[:8]}...' ({t.counterparty_name}) categorized as "
                        f"'{rule.subcategory.category.name}: {rule.subcategory.name}' by rule ID {rule.id}."
                    )
                    t.subcategory_id = rule.subcategory_id
                break  # Stop processing rules for this transaction

    if not dry_run:
        try:
            db.commit()
            logging.info(f"Successfully committed {categorized_count} new categorizations.")
        except Exception as e:
            db.rollback()
            logging.error(f"Failed to commit categorizations: {e}")

    return categorized_count
