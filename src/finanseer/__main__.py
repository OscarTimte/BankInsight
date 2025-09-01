import logging
from finanseer.db import init_db, get_db
from finanseer.importers import import_rabobank_csv, import_budget_categories
from finanseer.exporters import export_transactions_to_ynab_csv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    """Main function to run the Finanseer application."""
    print("Finanseer: Your financial co-pilot.")
    print("=" * 30)

    # 1. Initialize the database
    init_db()

    db_session_generator = get_db()
    db = next(db_session_generator)

    try:
        # 2. Import data
        rabobank_file = "CSV_A_NL77RABO0327533137_EUR_20240518_20250830.csv"
        logging.info(f"Importing transactions from '{rabobank_file}'...")
        import_rabobank_csv(db, rabobank_file)

        budget_file = "budget-data.csv"
        logging.info(f"Importing budget categories from '{budget_file}'...")
        import_budget_categories(db, budget_file)

        # 3. Export data
        export_file = "export.csv"
        export_transactions_to_ynab_csv(db, export_file)

        print("\n" + "=" * 30)
        print(f"Process finished. Exported data can be found in '{export_file}'.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
