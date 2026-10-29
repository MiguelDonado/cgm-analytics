# Deployment

Goal: a dashboard my father can open every night from any browser, even when
the laptop is off. The laptop only runs Airflow; the database and the dashboard
move to the cloud:

```
Laptop (Airflow, when it's on)  ──writes──▶  Neon (Postgres)  ◀──reads──  Shiny host  ◀──  browser
```

## The database: Neon

The local `cgm-db` container only exists on the laptop, so a dashboard hosted
anywhere else can't reach it. The database has to live somewhere that is always
on and reachable over the internet: [Neon](https://neon.tech), a managed
Postgres service.

**Why Neon:**

- **Free plan, no credit card.** It includes storage (about 0.5 GB per project)
  and a monthly allowance of compute hours (limits at the time of writing; see
  neon.tech/pricing). One reading every ~15 minutes is about 35,000 rows a year,
  a few MB, so storage isn't a concern for years.
- **Scale to zero.** After ~5 minutes without connections the database pauses
  and stops using compute hours. It only runs while Airflow writes (a few
  seconds per hour) or someone has the dashboard open. The first connection
  after a pause takes a moment to wake it.
- **Plain Postgres 17**, the same major version as the local `cgm-db`
  (`image: postgres:17`), so `psql`, `pg_dump`, RPostgres and Airflow work
  unchanged.

**How it works:** Neon splits Postgres into two parts.

- **Compute**: Postgres itself, running in a small VM. It runs the SQL and can
  be shut down at any time.
- **Storage**: a separate, always-on service (backed by AWS S3) that keeps every
  change. Postgres writes to it and reads pages from it over the network
  instead of from a local disk.

Because the data doesn't live on the VM, Neon can turn the VM off when idle and
start a new one on the next connection without losing anything. That is what
makes scale to zero (and the free plan) possible.

**Project settings:** project `cgm-analytics`, Postgres 17, region AWS Europe
(Frankfurt, closest to Spain). The connection string comes from the **Connect**
button in the Neon console and always ends in `?sslmode=require`: over the
internet, Neon only accepts encrypted connections.

## Loading the existing data into Neon

Neon starts empty, but `cgm-db` already holds every reading fetched so far. The
table was copied **before** pointing Airflow at Neon.

`psql` and `pg_dump` aren't installed on the laptop, but the `cgm-db` container
has both (Postgres 17) and can reach the internet, so the commands run inside
it.

**1. Store the connection string in a shell variable:**

```bash
read -s NEON_URL
```

Paste the connection string and press Enter. `-s` (silent) hides the password
on screen, and since it's typed into `read` instead of a command, it doesn't end
up in the bash history.

**2. Dump the local table and load it into Neon in one go:**

```bash
docker exec cgm-analytics_121cb8-cgm-db-1 \
  pg_dump -U cgm -d cgm -t glucose_readings --no-owner --no-privileges \
  | docker exec -i cgm-analytics_121cb8-cgm-db-1 psql "$NEON_URL"
```

- `pg_dump`: The output is SQL that can recreate the selected table and insert its data. 
  It is an utility used to export a PostgreSQL db.
- `|` (pipe) sends that SQL output straight into the next command as its
  input
- `psql "$NEON_URL"` runs in the same container but connects to **Neon**, and
  executes the SQL it receives. `docker exec -i` keeps the container's stdin
  open; without `-i` the piped SQL would never reach `psql`.

In short: `pg_dump` (local) → SQL text → `psql` (Neon).

**3. Check both sides have the same number of rows:**

```bash
docker exec cgm-analytics_121cb8-cgm-db-1 psql -U cgm -d cgm -c "SELECT count(*) FROM glucose_readings;"
docker exec cgm-analytics_121cb8-cgm-db-1 psql "$NEON_URL" -c "SELECT count(*) FROM glucose_readings;"
```

A difference of a reading or two is fine if Airflow ran in between: the upsert
fills it in once Airflow writes to Neon.

The local `cgm-db` is left untouched and stays as a backup.

## Pointing Airflow at Neon

The DAG never names a database server, only `conn_id="cgm_db"`. Airflow builds
that connection from the `AIRFLOW_CONN_CGM_DB` variable in `.env`, so switching
to Neon is a one-line change, with no DAG or SQL changes. The old line stays
commented out as a fallback:

```bash
# Local cgm-db (before Neon)
# AIRFLOW_CONN_CGM_DB='postgresql://cgm:<local-password>@cgm-db:5432/'
AIRFLOW_CONN_CGM_DB='postgresql://neondb_owner:<neon-password>@<neon-host>:5432/cgm?sslmode=require'
```

- Host: the Docker container name `cgm-db` becomes Neon's
  `ep-...eu-central-1.aws.neon.tech`. User and password come from the Neon
  connection string.
- Anything after `?` becomes the connection's **extra** field, and
  `PostgresHook` passes `sslmode=require` on to the driver, so the connection
  is encrypted.
- The single quotes keep the shell from treating `?` and `&` as special
  characters.

Environment variables are only read when a container starts, so editing `.env`
needs a restart:

```bash
astro dev restart
```

**Check:** trigger `fetch_glucose` in the Airflow UI, then look at the newest
rows in Neon:

```bash
docker exec cgm-analytics_121cb8-cgm-db-1 psql "$NEON_URL" -c \
  "SELECT max(factory_timestamp), max(ingested_at) FROM glucose_readings;"
```

## Pointing the dashboard at Neon

Before deploying the dashboard anywhere, the local container was switched to
Neon to check that the R side can reach it. If it fails on the laptop, it will
fail on the server too, and it's easier to debug here.

`db.R` reads each setting separately with `Sys.getenv()`, so `dashboard/.env`
gets the same values as Airflow's URI, one per variable:

```bash
# Local cgm-db (before Neon)
# CGM_DB_HOST=cgm-db
# CGM_DB_PORT=5432
# CGM_DB_NAME=cgm
# CGM_DB_USER=cgm
# CGM_DB_PASSWORD=<local-password>

CGM_DB_HOST=<neon-host>
CGM_DB_PORT=5432
CGM_DB_NAME=cgm
CGM_DB_USER=neondb_owner
CGM_DB_PASSWORD=<neon-password>
```

After `astro dev restart`, http://localhost:3838 shows today's readings, which
now only exist in Neon. The local `cgm-db` no longer receives new data.

## The dashboard: Posit Connect Cloud

The dashboard is hosted on [Posit Connect Cloud](https://connect.posit.cloud),
Posit's hosting service for Shiny apps. The alternative was shinyapps.io:

| | Connect Cloud | shinyapps.io |
|---|---|---|
| Deploys from | The GitHub repo (repo, branch, file) | The laptop, with `rsconnect::deployApp()` |
| Updates | Can republish on every push to `main` | Run `deployApp()` again by hand |
| Secrets (`CGM_DB_*`) | Entered in a web form, never in the repo | Usually shipped as a `.Renviron` file with the app |

**Why Connect Cloud:**

- **It fits the existing workflow.** Changes already go through PRs and CI;
  with Connect Cloud, merging into `main` also updates the live dashboard. That
  is **continuous deployment**, the step `ci-cd.md` lists as not used.
- **Secrets stay out of the code**, entered once in the Connect Cloud UI, the
  same idea as GitHub Actions secrets.
- **Free plan** for apps deployed from a public GitHub repo, with a monthly
  usage limit (see their pricing page). The app sleeps when idle, so a few
  minutes a night is well within it.

The app has no login for now: anyone with the URL can open it.

### How it works

Connect Cloud doesn't use the Dockerfile or the Docker Hub image. It builds the
app from the repo:

```
GitHub repo (main)  →  Connect Cloud: read manifest.json  →  install R + packages  →  run app.R
                                                                                      ↑
                                                         CGM_DB_* secrets as env vars ┘
```

1. It clones the repo at the chosen branch.
2. It reads `dashboard/manifest.json` to know which R version and which exact
   package versions to install.
3. It starts `app.R`, with the `CGM_DB_*` secrets set as environment variables,
   so `db.R` connects to Neon exactly as it does locally from `dashboard/.env`.

### `manifest.json`

The manifest is to Connect Cloud what the Dockerfile is to Docker Hub: the
recipe for the app's environment. It's generated from the `renv` project, in
the R console with the dashboard project open:

```r
renv::install("rsconnect")
rsconnect::writeManifest(appFiles = c("app.R", "R/db.R", "R/metrics.R"))
```

- `rsconnect` is Posit's deployment package; it writes the manifest.
- `writeManifest()` finds the packages the app uses, records their exact
  versions and the R version, and lists the app's files with a checksum each.
- `appFiles` limits that list to the files the app needs. Without it, every file
  in the folder was listed, including `.env`, `.Renviron` and `.Rprofile`. Only
  checksums are stored, so no password leaked, but those files aren't on GitHub
  (git-ignored), and `.Rprofile` starts `renv`, which can conflict with how
  Connect Cloud installs packages. rsconnect adds `renv.lock` on its own.

**Run it again whenever the dashboard's packages change** and commit the new
manifest. Otherwise Connect Cloud won't install the new package and the app
fails with `there is no package called ...`.