# Pending

## When deploying to the Raspberry Pi

Goal: run Airflow 24/7. On the laptop, any time it's off for more than ~12 hours
(the window LibreLinkUp returns) loses readings for good, e.g. the 32-hour gap
from 2026-10-16 18:36 to 2026-10-18 02:27.

- [ ] **1. Hardware and OS.** Raspberry Pi 5 with 8 GB of RAM (4 GB works but is
  tight: Airflow 3's containers alone use ~2–3 GB, plus `cgm-db` and Shiny).
  An SSD (USB 3 or an NVMe HAT) instead of the SD card: Postgres writes
  constantly, and SD cards wear out and corrupt under that load. The official
  27 W power supply. OS: Ubuntu Server 24.04 LTS 64-bit, the same release
  (noble) as the laptop, so the Posit Package Manager repository in
  `dashboard/.Rprofile` keeps the same distribution name. It must be 64-bit,
  because the Airflow and Postgres images are arm64. Flash it with Raspberry
  Pi Imager, setting the hostname (e.g. `cgm-pi`), the user, SSH with a public
  key, and Wi-Fi if needed (Ethernet is more reliable). Then
  `ssh <user>@cgm-pi.local`.
- [ ] **2. Docker and Astro CLI on the Pi.** Both have arm64 builds.
- [ ] **3. Run Airflow and `cgm-db` on the Pi.** Clone the repo, move the
  credentials hardcoded in `docker-compose.override.yml` to `.env`, and
  `astro dev start`. `astro dev` is meant for local development, but it's fine
  for a personal always-on box and keeps the same setup as the laptop. If the
  Pi struggles, a `cron` job running the fetch script is a much lighter
  alternative.
- [ ] **4. Start on boot.** A systemd service that runs `astro dev start`, so the
  Pi recovers from power cuts and reboots without manual steps.
- [ ] **5. Move the data.** `pg_dump` the laptop's `cgm-db` and restore it on the
  Pi (LibreLinkUp can't return the old readings again), then pause the
  laptop's DAG.
- [ ] **6. Dashboard on the Pi.** The R app as a container next to `cgm-db`.
  Check that Posit Package Manager has arm64 binaries for noble (see
  `docs/r-dashboard.md`); otherwise every package compiles from source.
- [ ] **7. Remote access with Tailscale.** Open the dashboard and the Airflow UI
  from the phone or laptop without exposing anything to the internet.
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

## CI/CD (GitHub Actions)

One PR per step, so the history shows the pipeline growing. CI uses fixture
readings only: never call LibreLinkUp or touch real glucose data.

- [ ] **1. Lint workflow.** `.github/workflows/ci.yml` on push to `main` and on
  PRs: `astral-sh/setup-uv` with `enable-cache`, `uv sync --locked` (catches a
  stale `uv.lock`), `ruff check` and `ruff format --check`.
- [ ] **2. Unit tests in CI.** Add a `uv run pytest` step once the unit tests
  above exist (`uv add --dev ruff pytest`).
- [ ] **3. SQL against a real Postgres.** A job with a `postgres:16` service
  container that runs `create_glucose_readings.sql`, then the upsert twice
  with fixture rows and asserts no duplicates (proves it's idempotent).
- [ ] **4. DAG integrity.** Install the Astro CLI in the runner and run
  `astro dev parse` / `astro dev pytest` (the tests in `tests/dags/`).
- [ ] **5. R dashboard checks.** `r-lib/actions/setup-r` + `setup-renv`, then
  `lintr` and `testthat` for `dashboard/R/db.R`. Use path filters so R jobs
  only run when `dashboard/**` changes and Python jobs only for `src/**`,
  `dags/**`, `tests/**`.
- [ ] **6. Multi-arch image to GHCR.** `docker/setup-qemu-action` + buildx +
  `docker/build-push-action` with layer caching, building amd64 and arm64
  (needed for the Pi). Tag with the commit SHA, and semver on release tags.
- [ ] **7. Deploy to the Pi.** A self-hosted runner on the Pi (or Tailscale +
  SSH) that pulls the image, runs `docker compose up -d`, and smoke-tests the
  Airflow health endpoint. Gate it with a `production` GitHub Environment
  (manual approval, environment secrets for the DB password).
- [ ] **Extras.** Dependabot (pip, GitHub Actions, Docker), branch protection
  requiring CI to pass, a reusable workflow / composite action for the uv
  setup, CodeQL and `trivy` image scanning, status badges in the README.
