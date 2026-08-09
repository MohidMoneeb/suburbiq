"""SQLite persistence. Idempotent by construction (FR12)."""
import os
import sqlite3
from typing import Dict, Iterable, List

from .models import Business

from .paths import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  raw_category TEXT,
  suburb TEXT,
  state TEXT,
  postcode TEXT,
  street TEXT,
  lat REAL,
  lon REAL,
  phone TEXT,
  website TEXT,
  opening_hours TEXT,
  digital_gap_score INTEGER,
  ingested_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_cat_suburb ON businesses(category, suburb);
CREATE INDEX IF NOT EXISTS idx_gap ON businesses(digital_gap_score DESC);
"""

COLUMNS = ["id", "source", "name", "category", "raw_category", "suburb", "state",
           "postcode", "street", "lat", "lon", "phone", "website",
           "opening_hours", "digital_gap_score", "ingested_at"]


def connect(path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert(conn: sqlite3.Connection, businesses: Iterable[Business]) -> Dict[str, int]:
    """Insert or refresh. Re-ingesting updates in place rather than duplicating."""
    cols = ", ".join(COLUMNS)
    marks = ", ".join("?" for _ in COLUMNS)
    updates = ", ".join(f"{c}=excluded.{c}" for c in COLUMNS if c != "id")
    sql = (f"INSERT INTO businesses ({cols}) VALUES ({marks}) "
           f"ON CONFLICT(id) DO UPDATE SET {updates}")

    before = conn.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]
    rows = [tuple(b.as_dict()[c] for c in COLUMNS) for b in businesses]
    conn.executemany(sql, rows)
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]
    return {"written": len(rows), "inserted": after - before,
            "updated": len(rows) - (after - before), "total": after}


def query(conn: sqlite3.Connection, category: str, source: str = "") -> List[sqlite3.Row]:
    sql = "SELECT * FROM businesses WHERE category = ?"
    params = [category]
    if source:
        sql += " AND source = ?"
        params.append(source)
    return conn.execute(sql + " ORDER BY digital_gap_score DESC, name", params).fetchall()


def categories(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT category, source, COUNT(*) n, MAX(ingested_at) last "
        "FROM businesses GROUP BY category, source ORDER BY n DESC"
    ).fetchall()
