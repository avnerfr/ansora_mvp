from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models import Base
import os
import sqlite3
import logging

logger = logging.getLogger(__name__)

# SQLite database - store in persistent volume
DB_DIR = os.getenv("DB_PATH", "/app/db")
os.makedirs(DB_DIR, exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_DIR}/marketing_mvp.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}, echo=False
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def migrate_database():
    """Automatically migrate database schema by adding missing columns."""
    db_path = f"{DB_DIR}/marketing_mvp.db"
    
    if not os.path.exists(db_path):
        logger.info("Database file doesn't exist yet, will be created by SQLAlchemy")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check existing columns
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add missing columns if they don't exist
        if 'retrieved_docs' not in columns:
            logger.info("Adding retrieved_docs column to jobs table...")
            cursor.execute("ALTER TABLE jobs ADD COLUMN retrieved_docs JSON")
        
        if 'final_prompt' not in columns:
            logger.info("Adding final_prompt column to jobs table...")
            cursor.execute("ALTER TABLE jobs ADD COLUMN final_prompt TEXT")
        
        if 'email_content' not in columns:
            logger.info("Adding email_content column to jobs table...")
            cursor.execute("ALTER TABLE jobs ADD COLUMN email_content TEXT")
        
        conn.commit()
        conn.close()
        logger.info("Database migration completed successfully")
    except Exception as e:
        logger.warning(f"Database migration check failed (non-critical): {e}")


def init_db():
    """Initialize the database tables and run migrations."""
    Base.metadata.create_all(bind=engine)
    # Run migrations after creating tables
    migrate_database()


def get_db():
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

