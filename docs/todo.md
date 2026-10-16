# Pending

## When deploying to the Raspberry Pi

- [ ] **Maintenance DAG to clean old Airflow metadata and logs.** Airflow never
  deletes XComs, run history (`dag_run`, `task_instance`) or task log files on
  its own. The growth is small (XComs ~6 MB/year at 24 runs/day, measured
  2026-10-16; task logs probably tens of MB/year), so nothing is needed locally.
  On the Pi, add a small DAG (e.g. monthly) that removes anything older than
  90 days: `airflow db clean --clean-before-timestamp <date> --yes` for the
  metadata, plus deleting old files from the logs folder. The glucose data
  lives in `glucose_readings`, so none of this is needed after a run finishes.
  See "Passing data between tasks" in `docs/airflow-concepts.md`.

## Pipeline quality

- [ ] **Data quality checks on `glucose_readings`.** Run them as tasks after
  `load_readings`, so a bad load fails visibly instead of silently feeding the
  analytics. Ideas: values in a plausible range (~40–500 mg/dL), no nulls,
  freshness (newest reading less than ~1 hour old, which also catches a broken
  LibreLinkUp login), and no unexpected gaps between consecutive readings.
  `common.sql` (already installed) has `SQLColumnCheckOperator` and
  `SQLTableCheckOperator` for this.
- [ ] **A few unit tests.** The DAG integrity tests in `tests/dags/` already
  exist (`astro dev pytest`); what's missing are tests for our own logic, e.g.
  the regional-redirect handling in `initialize_client` (with the HTTP calls
  mocked) and the mapping from readings to table rows. `cgm_analytics` doesn't
  need Airflow, so its tests can run locally with `uv run pytest`.
