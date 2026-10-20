"""
Integration tests for the SQL in include/sql/, run against a real Postgres.
They never touch cgm-db: the connection comes from the PG* environment
variables (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE), pointed at a
throwaway database locally and at a service container in CI.
"""

from pathlib import Path

import psycopg2
import pytest

from cgm_analytics.main import reading_to_row

SQL_DIR = Path(__file__).parents[2] / "include" / "sql"

# Three readings 15 minutes apart, in the shape load_readings receives from XCom.
READINGS = [
    {"factory_timestamp": "2026-10-19T06:15:00Z", "timestamp": "2026-10-19T08:15:00", "value_in_mg_per_dl": 99.0},
    {"factory_timestamp": "2026-10-19T06:30:00Z", "timestamp": "2026-10-19T08:30:00", "value_in_mg_per_dl": 104.0},
    {"factory_timestamp": "2026-10-19T06:45:00Z", "timestamp": "2026-10-19T08:45:00", "value_in_mg_per_dl": 110.0},
]

@pytest.fixture
def conn():
    """A connection to a database without glucose_readings, so each test starts empty."""
    conn = psycopg2.connect()  # no arguments: libpq reads the PG* variables
    with conn.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS glucose_readings")
    conn.commit()
    yield conn
    conn.close()

def create_table(conn):
    with conn.cursor() as cursor:
        cursor.execute((SQL_DIR / "create_glucose_readings.sql").read_text())
    conn.commit()

def load(conn, readings: list[dict]) -> int:
    """Same steps as load_readings in dags/fetch_glucose.py; returns rows inserted."""
    upsert_sql = (SQL_DIR / "upsert_glucose_readings.sql").read_text()
    inserted = 0
    with conn.cursor() as cursor:
        for r in readings:
            cursor.execute(upsert_sql, reading_to_row(r))
            inserted += cursor.rowcount
    conn.commit()
    return inserted

def count_rows(conn) -> int:
    with conn.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM glucose_readings")
        return cursor.fetchone()[0]

def test_create_table_can_run_every_hour(conn):
    # The DAG runs create_table before every load, so a second run must not fail.
    create_table(conn)
    create_table(conn)

def test_upsert_twice_stores_each_reading_once(conn):
    create_table(conn)

    assert load(conn, READINGS) == 3
    assert load(conn, READINGS) == 0
    assert count_rows(conn) == 3

def test_overlapping_run_inserts_only_new_readings(conn):
    # Like two consecutive DAG runs: the second window repeats one reading.
    create_table(conn)

    assert load(conn, READINGS[:2]) == 2
    assert load(conn, READINGS[1:]) == 1
    assert count_rows(conn) == 3