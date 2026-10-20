"""
Tests for dags/fetch_glucose.py. Run inside the Airflow image with
`astro dev pytest tests/dags`, so they see the same Airflow, providers and
cgm_analytics as the scheduler. They only load the DAG: no task runs, and
nothing calls LibreLinkUp or cgm-db.
"""

import os
from pathlib import Path

import pytest
from airflow.models import DagBag

DAG_ID = "fetch_glucose"
SQL_DIR = Path(os.environ["AIRFLOW_HOME"]) / "include" / "sql"


@pytest.fixture(scope="module")
def dag_bag():
    # Parses every file in dags/, like the scheduler does
    return DagBag(include_examples=False)


@pytest.fixture(scope="module")
def dag(dag_bag):
    return dag_bag.dags[DAG_ID]


def test_no_import_errors(dag_bag):
    assert dag_bag.import_errors == {}


def test_tasks(dag):
    assert set(dag.task_ids) == {"create_table", "fetch_readings", "load_readings"}


def test_load_waits_for_table_and_readings(dag):
    assert dag.get_task("load_readings").upstream_task_ids == {
        "create_table",
        "fetch_readings",
    }
    assert dag.get_task("create_table").upstream_task_ids == set()
    assert dag.get_task("fetch_readings").upstream_task_ids == set()


def test_runs_hourly_without_catchup(dag):
    assert dag.schedule == "@hourly"
    assert dag.catchup is False


def test_every_task_retries(dag):
    for task in dag.tasks:
        assert task.retries == 3, f"{task.task_id} has retries={task.retries}"


def test_sql_files_exist(dag):
    # A renamed or missing .sql file only fails when the task runs, so check here.
    assert str(SQL_DIR) in dag.template_searchpath
    # Parsing the DAG replaces create_table's file name with the file's contents;
    # if the file isn't found, the name is left there instead.
    assert "CREATE TABLE IF NOT EXISTS glucose_readings" in dag.get_task("create_table").sql
    assert (SQL_DIR / "upsert_glucose_readings.sql").is_file()