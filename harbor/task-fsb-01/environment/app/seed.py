"""Build the FieldServiceBench world DB deterministically.

Usage: python3 seed.py <db_path>

Same inputs -> same bytes: fixed clock, fixed ids, insertion order fixed by
tasks.py, no randomness, no wall-clock reads.
"""

import os
import sqlite3
import sys

import tasks


def build(db_path):
    if os.path.exists(db_path):
        os.remove(db_path)
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = f.read()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema)
        rows = list(tasks.NOISE_ROWS)
        for task_id in tasks.TASK_IDS:
            rows.extend(tasks.TASKS[task_id]["seed_rows"])
        for table, row in rows:
            cols = list(row.keys())
            sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})"
            conn.execute(sql, [row[c] for c in cols])
        # generated-id counters all start at zero
        for prefix in ("BK", "Q", "RSV", "EM"):
            conn.execute("INSERT INTO counters (name, n) VALUES (?, 0)", (prefix,))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python3 seed.py <db_path>", file=sys.stderr)
        sys.exit(2)
    build(sys.argv[1])
    print(f"seeded {sys.argv[1]}")
