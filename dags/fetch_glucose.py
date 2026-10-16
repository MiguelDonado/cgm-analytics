"""Fetch the latest glucose readings from LibreLinkUp every hour.

LibreLinkUp's graph endpoint returns the last ~12 hours of readings, one about
every 15 minutes. The DAG runs much more often than that (hourly), so the
windows of consecutive runs overlap heavily:

    run 10:00 -> readings from ~22:00 to 10:00
    run 11:00 -> readings from ~23:00 to 11:00   (11 of its 12 hours already fetched)

That overlap is what makes the pipeline resilient. If a run fails (LibreLinkUp
down, rate limited, the machine off), no data is lost: the next successful run
still returns those readings, as long as the gap is shorter than ~12 hours.

Because each run fetches mostly readings already stored, the load step will
upsert (insert new readings, skip existing ones keyed on
factory_timestamp (UTC), see docs/data-model.md) instead of a plain insert, so
overlapping runs never create duplicates.

Readings are stored in the glucose_readings table of cgm-db.
"""

import os
from pathlib import Path

from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import dag, task
from pendulum import datetime

from cgm_analytics.main import fetch_recent_readings, get_my_patient, initialize_client

# Folder where Airflow looks for .sql files
SQL_DIR = Path("/usr/local/airflow/include/sql")


@dag(
    start_date=datetime(2026, 10, 16),
    schedule="@hourly",
    catchup=False,
    default_args={"retries": 3},
    tags=["cgm"],
    # Folder where Airflow looks for .sql files. With sql="create_glucose_readings.sql",
    # Airflow treats the value as a file name, not SQL, and by default only searches
    # dags/. The files are in include/sql/, so add that folder to the search.
    # The path is where the folder is inside the container, which is where the task runs.
    template_searchpath=str(SQL_DIR),
)
def fetch_glucose():

    create_table = SQLExecuteQueryOperator(
        task_id="create_table", conn_id="cgm_db", sql="create_glucose_readings.sql"
    )

    @task
    def fetch_readings() -> list[dict]:
        client = initialize_client(
            os.environ["LIBRELINK_EMAIL"], os.environ["LIBRELINK_PASSWORD"]
        )
        my_patient = get_my_patient(client)
        readings = fetch_recent_readings(client, my_patient)
        print(f"Fetched {len(readings)} readings")
        # JSON-safe dicts (datetimes become ISO strings) so they can be passed as XCom.
        return [reading.model_dump(mode="json") for reading in readings]

    @task
    def load_readings(readings: list[dict]) -> int:
        upsert_sql = (SQL_DIR / "upsert_glucose_readings.sql").read_text()

        hook = PostgresHook(postgres_conn_id="cgm_db")
        conn = hook.get_conn()
        inserted = 0
        try:
            with conn.cursor() as cursor:
                for r in readings:
                    cursor.execute(
                        upsert_sql,
                        (
                            r["factory_timestamp"],
                            r["timestamp"],
                            r["value_in_mg_per_dl"],
                            r["is_high"],
                            r["is_low"],
                            r["measurement_color"],
                            r["type"],
                        ),
                    )
                    inserted += cursor.rowcount  # 1 if inserted, 0 if already stored
            # All rows in one transaction: either everything is saved or nothing
            conn.commit()
        finally:
            conn.close()

        print(
            f"Inserted {inserted} new readings, skipped {len(readings) - inserted} already stored"
        )
        return inserted

    readings = fetch_readings()  # return value is pushed to XCom
    loaded = load_readings(readings)  # pulls fetch_readings' XCom as its argument

    create_table >> loaded


fetch_glucose()
