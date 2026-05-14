"""
db.py — Database helpers for subscriber storage.
Uses PostgreSQL via DATABASE_URL env var.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    """Create tables if they don't exist."""
    if not DATABASE_URL:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS subscribers (
                    id          SERIAL PRIMARY KEY,
                    email       TEXT UNIQUE NOT NULL,
                    cities      TEXT[] DEFAULT '{}',
                    depts       TEXT[] DEFAULT '{}',
                    exp_ranges  TEXT[] DEFAULT '{}',
                    created_at  TIMESTAMP DEFAULT NOW()
                );
            """)
        conn.commit()

def add_subscriber(email, cities, depts, exp_ranges):
    """Insert or update a subscriber. Returns (id, is_new)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO subscribers (email, cities, depts, exp_ranges)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (email) DO UPDATE
                SET cities     = EXCLUDED.cities,
                    depts      = EXCLUDED.depts,
                    exp_ranges = EXCLUDED.exp_ranges
                RETURNING id, (xmax = 0) AS is_new
            """, (email, cities, depts, exp_ranges))
            row = cur.fetchone()
        conn.commit()
    return row  # (id, is_new)

def get_all_subscribers():
    """Return all subscribers as list of dicts."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM subscribers ORDER BY created_at DESC")
            return cur.fetchall()

def subscriber_count():
    """Return total subscriber count."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM subscribers")
            return cur.fetchone()[0]
