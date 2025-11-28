from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models import Base
import os

# SQLite database - store in persistent volume
DB_DIR = os.getenv("DB_PATH", "/app/db")
os.makedirs(DB_DIR, exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_DIR}/marketing_mvp.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}, echo=False
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize the database tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

