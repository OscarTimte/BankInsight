import argparse
import logging
from finanseer.db import init_db, get_db
from finanseer.importers import import_rabobank_csv, import_budget_categories
from finanseer.exporters import export_transactions_to_ynab_csv
from finanseer.core import (
    get_uncategorized_transactions,
    get_all_categories,
    set_category_for_transactions,
    get_transactions_by_text,
    add_rule,
    apply_rules,
)
from finanseer import models

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def handle_import(args):
    """Handles the import command."""
    logging.info("Starting data import process...")
    db_session_generator = get_db()
    db = next(db_session_generator)
    try:
        rabobank_file = "CSV_A_NL77RABO0327533137_EUR_20240518_20250830.csv"
        logging.info(f"Importing transactions from '{rabobank_file}'...")
        import_rabobank_csv(db, rabobank_file)

        budget_file = "budget-data.csv"
        logging.info(f"Importing budget categories from '{budget_file}'...")
        import_budget_categories(db, budget_file)

        logging.info("Data import finished.")

        if args.and_list:
            print("\n" + "=" * 30)
            handle_list_categories(args)

    finally:
        db.close()

def handle_export(args):
    """Handles the export command."""
    logging.info("Starting data export process...")
    db_session_generator = get_db()
    db = next(db_session_generator)
    try:
        export_file = args.output if args.output else "export.csv"
        export_transactions_to_ynab_csv(db, export_file)
        print(f"Process finished. Exported data can be found in '{export_file}'.")
    finally:
        db.close()

def handle_list_categories(args):
    """Handles the list-categories command."""
    db_session_generator = get_db()
    db = next(db_session_generator)
    try:
        categories = get_all_categories(db)
        if not categories:
            print("No categories found. Run the import command first.")
            return

        print("Available categories and subcategories:\n")

        flat_list = []
        for cat in categories:
            for sub in sorted(cat.subcategories, key=lambda s: s.name):
                flat_list.append(sub)

        for i, sub in enumerate(flat_list, 1):
            print(f"  {i: >3} | {sub.category.name: <20} | {sub.name}")

    finally:
        db.close()

def handle_review(args):
    """Handles the interactive transaction review and categorization command."""
    db_session_generator = get_db()
    db = next(db_session_generator)
    try:
        # HACK: Re-import data to ensure it exists in the ephemeral environment for review.
        # In a real-world scenario, the database would be persistent.
        handle_import(argparse.Namespace())

        while True:
            transactions = get_uncategorized_transactions(db, sort_by=args.sort_by)
            if not transactions:
                print("No more uncategorized transactions to review. Well done!")
                break

            print(f"\nFound {len(transactions)} uncategorized transactions to review (showing first 20):\n")
            for i, t in enumerate(transactions[:20], 1):
                print(f"  {i: >3} | {t.transaction_date} | {t.amount: >8.2f} {t.currency} | {t.counterparty_name or 'N/A': <35} | {t.description_raw or 'N/A'}")

            print("\nEnter transaction numbers to categorize (e.g., 1,2,5-7), 'l' to list categories, or 'q' to quit.")
            user_input = input("> ")

            if user_input.lower() == 'q':
                break
            if user_input.lower() == 'l':
                handle_list_categories(args)
                continue

            try:
                # Parse transaction numbers (e.g., "1,2,5-7")
                selected_indices = set()
                parts = user_input.split(',')
                for part in parts:
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        selected_indices.update(range(start - 1, end))
                    else:
                        selected_indices.add(int(part) - 1)

                selected_transactions = [transactions[i] for i in sorted(list(selected_indices)) if i < len(transactions)]
                if not selected_transactions:
                    print("Invalid selection.")
                    continue

                # Get category choice
                print("Enter the category number to assign (or 'c' to cancel):")
                cat_input = input("> ")
                if cat_input.lower() == 'c':
                    continue

                cat_index = int(cat_input) - 1

                # Flatten categories to get the selected one
                all_categories = get_all_categories(db)
                flat_subcategories = []
                for cat in sorted(all_categories, key=lambda x: x.name):
                    for sub in sorted(cat.subcategories, key=lambda s: s.name):
                        flat_subcategories.append(sub)

                if 0 <= cat_index < len(flat_subcategories):
                    chosen_subcategory = flat_subcategories[cat_index]
                    transaction_ids = [t.id for t in selected_transactions]
                    set_category_for_transactions(db, transaction_ids, chosen_subcategory.id)

                    # B2: Rule creation suggestion
                    print(f"Successfully categorized {len(transaction_ids)} transaction(s).")
                    print("\nTo create a rule for this, you could use a command like:")

                    # Suggest a rule based on counterparty name if available
                    counterparty = selected_transactions[0].counterparty_name
                    if counterparty:
                        print(f'  poetry run python -m finanseer add-rule --type counterparty_name --pattern "{counterparty}" --category-id {chosen_subcategory.id}')

                    # Suggest a rule based on IBAN if available
                    iban = selected_transactions[0].counterparty_iban
                    if iban:
                        print(f'  poetry run python -m finanseer add-rule --type iban --pattern "{iban}" --category-id {chosen_subcategory.id}')

                else:
                    print("Invalid category number.")

            except (ValueError, IndexError):
                print("Invalid input. Please try again.")

    finally:
        db.close()

def handle_bulk_categorize(args):
    """Handles the bulk categorization command."""
    db_session_generator = get_db()
    db = next(db_session_generator)
    try:
        transactions = get_transactions_by_text(db, args.text)

        if not transactions:
            print(f"No transactions found matching '{args.text}'.")
            return

        print(f"Found {len(transactions)} matching transactions for the pattern '{args.text}':\n")
        for t in transactions[:10]: # Preview first 10
            print(f"  {t.transaction_date} | {t.amount: >8.2f} {t.currency} | {t.counterparty_name or 'N/A': <35} | {t.description_raw or 'N/A'}")
        if len(transactions) > 10:
            print(f"  ...and {len(transactions) - 10} more.")

        confirm = input(f"\nProceed with assigning category ID {args.category_id} to these {len(transactions)} transactions? (y/n): ").lower()

        if confirm == 'y':
            transaction_ids = [t.id for t in transactions]
            set_category_for_transactions(db, transaction_ids, args.category_id)
        else:
            print("Bulk categorization cancelled.")

    finally:
        db.close()

def handle_add_rule(args):
    """Handles the add-rule command."""
    db_session_generator = get_db()
    db = next(db_session_generator)
    try:
        add_rule(
            db=db,
            type=args.type,
            pattern=args.pattern,
            subcategory_id=args.category_id,
            priority=args.priority
        )
    finally:
        db.close()

def handle_apply_rules(args):
    """Handles the apply-rules command."""
    logging.info("Starting to apply categorization rules...")
    db_session_generator = get_db()
    db = next(db_session_generator)
    try:
        # HACK: Ensure data is present for the demo
        handle_import(argparse.Namespace(and_list=False))

        count = apply_rules(db, dry_run=args.dry_run)

        if args.dry_run:
            print(f"\n[Dry Run] Completed. {count} transactions would be categorized.")
        else:
            print(f"\nRule application complete. {count} transactions were categorized.")
    finally:
        db.close()


def main():
    """Main function to run the Finanseer application."""
    init_db()  # Ensure DB is initialized before any command is run
    parser = argparse.ArgumentParser(description="Finanseer: Your financial co-pilot.")
    subparsers = parser.add_subparsers(dest='command', required=True, help='Available commands')

    # Import command
    parser_import = subparsers.add_parser('import', help='Import data from CSV files into the database.')
    parser_import.add_argument('--and-list', action='store_true', help='List categories immediately after importing.')
    parser_import.set_defaults(func=handle_import)

    # Export command
    parser_export = subparsers.add_parser('export', help='Export data from the database to a CSV file.')
    parser_export.add_argument('-o', '--output', type=str, help='Output file path for the export.')
    parser_export.set_defaults(func=handle_export)

    # Review command
    parser_review = subparsers.add_parser('review', help='Review and categorize uncategorized transactions.')
    parser_review.add_argument('--sort-by', type=str, choices=['date', 'amount'], default='date', help='Sort the review queue by date or amount.')
    parser_review.set_defaults(func=handle_review)

    # List Categories command
    parser_list_cats = subparsers.add_parser('list-categories', help='List all available categories and subcategories.')
    parser_list_cats.set_defaults(func=handle_list_categories)

    # Bulk Categorize command
    parser_bulk = subparsers.add_parser('bulk-categorize', help='Categorize multiple transactions based on a text pattern.')
    parser_bulk.add_argument('text', type=str, help='The text pattern to search for in payee and description.')
    parser_bulk.add_argument('category_id', type=int, help='The numeric ID of the subcategory to assign.')
    parser_bulk.set_defaults(func=handle_bulk_categorize)

    # Add Rule command
    parser_add_rule = subparsers.add_parser('add-rule', help='Add a new categorization rule.')
    parser_add_rule.add_argument('--type', type=str, required=True, choices=['iban', 'counterparty_name', 'description_contains'], help='Type of the rule.')
    parser_add_rule.add_argument('--pattern', type=str, required=True, help='The pattern to match (e.g., an IBAN or a keyword).')
    parser_add_rule.add_argument('--category-id', type=int, required=True, help='The numeric ID of the subcategory to assign.')
    parser_add_rule.add_argument('--priority', type=int, default=100, help='The priority of the rule (lower is higher).')
    parser_add_rule.set_defaults(func=handle_add_rule)

    # Apply Rules command
    parser_apply_rules = subparsers.add_parser('apply-rules', help='Apply all active rules to uncategorized transactions.')
    parser_apply_rules.add_argument('--dry-run', action='store_true', help='Simulate rule application without saving changes.')
    parser_apply_rules.set_defaults(func=handle_apply_rules)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
