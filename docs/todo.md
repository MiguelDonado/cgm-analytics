# Pending

1. Record video walkthrough
2. Record video setup and usage
3. CI/CD pipeline.

## CI/CD (GitHub Actions)

One PR per step, so the history shows the pipeline growing. CI uses fixture
readings only: never call LibreLinkUp or touch real glucose data.

- [ ] **4. DAG integrity.** Install the Astro CLI in the runner and run
  `astro dev parse` / `astro dev pytest` (the tests in `tests/dags/`).
- [ ] **5. R dashboard checks.** `r-lib/actions/setup-r` + `setup-renv`, then
  `lintr` and `testthat` for `dashboard/R/db.R`. Use path filters so R jobs
  only run when `dashboard/**` changes and Python jobs only for `src/**`,
  `dags/**`, `tests/**`.
- [ ] **Extras.** Dependabot (pip, GitHub Actions, Docker), branch protection
  requiring CI to pass, a reusable workflow / composite action for the uv
  setup, CodeQL and `trivy` image scanning, status badges in the README.
- [ ] **Publish the images.** Push them to Docker Hub, or ship the whole
  Compose project.

  A fresh install may not work as described. When someone follows these steps, the dashboard starts before the DAG has run, so glucose_readings doesn't exist yet. reactivePoll() queries it at startup and fails. The container then keeps restarting until the first DAG run creates the table. Even then, an empty table would make min(days) return Inf when building the date picker. I haven't tested either case, but I'd expect an error, or at least a broken first page. I'd check that before publishing these steps:
   - Test: stop the stack, start the dashboard against an empty database and see what happens.
   - Fix: make read_last_time()/read_readings() tolerate a missing table, and have ui show a "No readings yet" message when there's no data.

Push image dashboard to DockerHub.
