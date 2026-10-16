"""Fetch the latest glucose readings from LibreLinkUp every hour.

LibreLinkUp's graph endpoint returns the last ~12 hours of readings, one about
every 15 minutes. The DAG runs much more often than that (hourly), so the
windows of consecutive runs overlap heavily:

    run 10:00 -> readings from ~22:00 to 10:00
    run 11:00 -> readings from ~23:00 to 11:00   (11 of its 12 hours already fetched)

That overlap is what makes the pipeline resilient. If a run fails (LibreLinkUp
down, rate limited, the machine off), no data is lost: the next successful run
still returns those readings, as long as the gap is shorter than ~12 hours.

Because each run fetches mosthe load step will
upsert (insert new readings, skip or update existing ones keyed on the reading's
timestamp) instead of a plai never create
duplicates. For now the task only logs the readings.
"""

import os

from airflow.sdk import dag, task
from pendulum import datetime

from cgm_analytics.main import fetch_recent_readings, get_my_patient, initialize_client


@dag(
    start_date=datetime(2026,10,16),
    schedule="@hourly",
    catchup=False,
    default_args={"retries": 3},
    tags=["cgm"]
)
def fetch_glucose():
    @task
    def fetch_readings() -> int:
        client = initialize_client(os.environ["LIBRELINK_EMAIL"], os.environ["LIBRELINK_PASSWORD"])
        my_patient = get_my_patient(client)
        readings = fetch_recent_readings(client, my_patient)
        for reading in readings:
            print(reading)
        return len(readings)

    fetch_readings()

fetch_glucose()

