# Pending

1. Record video walkthrough
2. Record video setup and usage
3. CI/CD pipeline.

## CI/CD (GitHub Actions)

One PR per step, so the history shows the pipeline growing. CI uses fixture
readings only: never call LibreLinkUp or touch real glucose data.

- [ ] **1. Lint workflow.** `.github/workflows/ci.yml` on push to `main` and on
  PRs: `astral-sh/setup-uv` with `enable-cache`, `uv sync --locked` (catches a
  stale `uv.lock`), `ruff check` and `ruff format --check`.
- [ ] **3. SQL against a real Postgres.** A job with a `postgres:17` service
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
- [ ] **Publish the images.** Push them to Docker Hub, or ship the whole
  Compose project.

  A fresh install may not work as described. When someone follows these steps, the dashboard starts before the DAG has run, so glucose_readings doesn't exist yet. reactivePoll() queries it at startup and fails. The container then keeps restarting until the first DAG run creates the table. Even then, an empty table would make min(days) return Inf when building the date picker. I haven't tested either case, but I'd expect an error, or at least a broken first page. I'd check that before publishing these steps:
   - Test: stop the stack, start the dashboard against an empty database and see what happens.
   - Fix: make read_last_time()/read_readings() tolerate a missing table, and have ui show a "No readings yet" message when there's no data.

Push image dashboard to DockerHub.
