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
