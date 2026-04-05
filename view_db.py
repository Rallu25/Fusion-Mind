"""View all data from the Fusion Mind database."""

import sqlite3
import os

DB_PATH = os.path.join("data", "fusion_mind.db")


def view_all():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    tables = ["teachers", "shared_quizzes", "submissions", "quiz_starts"]

    for table in tables:
        print(f"\n{'='*60}")
        print(f"  {table.upper()}")
        print(f"{'='*60}")

        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        except sqlite3.OperationalError:
            print("  (table does not exist yet)")
            continue

        if not rows:
            print("  (empty)")
            continue

        columns = rows[0].keys()
        for i, row in enumerate(rows, 1):
            print(f"\n  --- Row {i} ---")
            for col in columns:
                value = row[col]
                # Truncate long values (like questions_json)
                if isinstance(value, str) and len(value) > 100:
                    value = value[:100] + "..."
                print(f"  {col}: {value}")

    conn.close()
    print(f"\n{'='*60}")
    print("  Done.")


if __name__ == "__main__":
    view_all()
