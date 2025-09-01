import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finanseer.models import Base

DATABASE_URL = "sqlite:///finanseer.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """
    Initializes the database by creating all tables defined in the Base metadata.
    This is safe to run multiple times; it won't recreate existing tables.
    """
    logging.info("Initializing database...")
    try:
        Base.metadata.create_all(bind=engine)
        logging.info("Database initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize database: {e}")

def get_db():
    """
    Generator function to get a database session.
    Ensures the session is properly closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
