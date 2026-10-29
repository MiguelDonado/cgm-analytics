"""Smoke test against the real LibreLinkUp API (see docs/ci-cd.md).

Run daily by .github/workflows/api-check.yml to catch the unofficial API
changing under us (new app version required, endpoint moved, login flow changed).
Needs AIRFLOW_CONN_LIBRELINKUP, the same JSON as in .env.

Only counts are printed, never readings or patient details
"""

import json
import os

from cgm_analytics.main import fetch_recent_readings, get_my_patient, initialize_client


def test_librelinkup_api_works():
    # If secret is missing, test fails with a KeyError
    credentials = json.loads(os.environ["AIRFLOW_CONN_LIBRELINKUP"])

    # Same logic than fetch_readings() task in fetch_glucose.py file
    client = initialize_client(credentials["login"], credentials["password"])
    # Raises an error if there is no patient -> IndexError
    patient = get_my_patient(client)
    readings = fetch_recent_readings(client, patient)

    # An empty list is a working API with no sensor data (e.g. sensor
    # change), not a failure

    # Reaching the print already means the API works
    # 1. Each of the previous calls raises an error if it breaks
    print(f"LibreLinkUp OK: {len(readings)} readings")