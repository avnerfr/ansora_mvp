#!/usr/bin/env python3
"""
Database migration script to add new columns to existing tables.
Run this script to update your database schema after adding new fields.
"""

import sqlite3
import os

def migrate_database():
    """Add new columns to existing tables using raw SQLite."""

    # Possible database locations
    possible_paths = [
        "/app/db/marketing_mvp.db",  # Docker path
        "marketing_mvp.db",          # Local development
        "../db/marketing_mvp.db",    # Relative path
        "./db/marketing_mvp.db",     # Local db folder
    ]

    db_path = None
    for path in possible_paths:
        if os.path.exists(path):
            db_path = path
            break

    if not db_path:
        print("Database not found. Possible locations checked:")
        for path in possible_paths:
            print(f"  - {path}")
        print("\nMake sure your FastAPI application has been run at least once to create the database.")
        print("Then re-run this migration script.")
        print("\nAlternatively, you can manually run these SQL commands on your database:")
        print("  ALTER TABLE jobs ADD COLUMN retrieved_docs JSON;")
        print("  ALTER TABLE jobs ADD COLUMN final_prompt TEXT;")
        return

    print(f"Found database at: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check existing columns
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [row[1] for row in cursor.fetchall()]

        # Add retrieved_docs column if it doesn't exist
        if 'retrieved_docs' not in columns:
            print("Adding retrieved_docs column to jobs table...")
            cursor.execute("ALTER TABLE jobs ADD COLUMN retrieved_docs JSON")
        else:
            print("retrieved_docs column already exists")

        # Add final_prompt column if it doesn't exist
        if 'final_prompt' not in columns:
            print("Adding final_prompt column to jobs table...")
            cursor.execute("ALTER TABLE jobs ADD COLUMN final_prompt TEXT")
        else:
            print("final_prompt column already exists")

        conn.commit()
        print("Migration completed successfully!")

        # Show final schema
        cursor.execute("PRAGMA table_info(jobs)")
        print("\nFinal jobs table schema:")
        for row in cursor.fetchall():
            print(f"  {row[1]}: {row[2]}")

    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
