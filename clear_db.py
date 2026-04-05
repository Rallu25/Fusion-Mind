"""Clear all data from the Fusion Mind database (tables remain)."""

import sqlite3
import os

DB_PATH = os.path.join("data", "fusion_mind.db")


def clear_all():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    tables = ["submissions", "quiz_starts", "shared_quizzes", "teachers"]

    for table in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            conn.execute(f"DELETE FROM {table}")
            print(f"  {table}: deleted {count} rows")
        except sqlite3.OperationalError:
            print(f"  {table}: (table does not exist)")

    conn.commit()
    conn.close()
    print("\nAll data cleared. Tables are intact.")


if __name__ == "__main__":
    confirm = input("Delete ALL data from the database? (yes/no): ")
    if confirm.strip().lower() == "yes":
        clear_all()
    else:
        print("Cancelled.")
