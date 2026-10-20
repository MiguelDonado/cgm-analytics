# Airflow setup (Astro CLI)

Airflow runs locally with the [Astro CLI](https://www.astronomer.io/docs/astro/cli/overview).
`astro dev init` created the project scaffolding, and `astro dev start` builds the
image and starts the containers (Postgres, scheduler, DAG processor, API server,
triggerer). No Astronomer account is needed.

## Project files created by `astro dev init`

| File/folder | Purpose |
|---|---|
| `Dockerfile` | Builds the Airflow image. Based on Astro Runtime, which copies the project into the image and installs `packages.txt` and `requirements.txt` (see below). |
| `dags/` | The DAGs. Mounted into the containers, so edits show up without a rebuild. |
| `include/` | Extra files used by the DAGs (SQL, configs). Also mounted. |
| `plugins/` | Custom Airflow plugins. |
| `requirements.txt` | Extra Python packages. Kept empty: dependencies come from `pyproject.toml`. |
| `packages.txt` | System (apt) packages. Kept empty. |
| `airflow_settings.yaml` | Connections and variables for local development only. Not committed (may contain secrets). |
| `.astro/` | Astro CLI config and the built-in DAG integrity test. Not committed. |
| `.dockerignore` | Files that are **not** copied into the image (`.env`, `.venv`, `.git`, ...). |
| `tests/dags/test_dag_example.py` | Checks that every DAG imports without errors, has tags and has retries set. |

### What goes in `include/`

`include/` holds **files the DAGs use that aren't DAGs themselves**. Airflow only
looks for DAG definitions in `dags/`; everything the DAGs *need* goes in
`include/`.

| What | Example | Why it goes there |
|---|---|---|
| **SQL files** | `include/sql/create_glucose_readings.sql` | Keeps long SQL out of Python, with syntax highlighting, and it can be run in psql too. The most common use. |
| **Config files** | `include/config/thresholds.yaml` | Settings the DAGs read (target ranges, lists of things to process). |
| **Templates** | `include/templates/report.html` | Jinja templates for emails or reports. |
| **Small static data** | `include/data/seed.csv` | Reference or lookup tables, test fixtures. |
| **External tool projects** | `include/dbt/` | E.g. a dbt project run from Airflow (common with the Cosmos library). |
| **Helper Python modules** | `include/utils.py` | Imported as `from include.utils import ...`; works because `/usr/local/airflow` is on `PYTHONPATH` in the image. |

What doesn't belong there:

- **Secrets:** `include/` is copied into the image and committed to git. Use
  `.env` or Airflow connections.
- **Large data or outputs:** those belong in the database or object storage.

`include/` is mounted live like `dags/`, so editing a SQL file there takes effect
on the next task run, without `astro dev restart`.

### How this project splits code

This project already has a better home for Python logic, so `include/` won't
need helper modules:

```
src/cgm_analytics/   Python business logic (fetching, transforming). Works without
                     Airflow, installed as a package, testable on its own.
dags/                Thin DAGs: scheduling and wiring tasks together, calling into
                     cgm_analytics.
include/             Non-Python assets the DAGs use: SQL files now, maybe configs
                     or dbt later.
```

**Rule of thumb** for where new code or files go:

- **`include/`**: things that only exist *for the DAGs*: SQL files
  (`include/sql/`), small templates, config.
- **`src/`**: the actual application/domain code, which should stay importable,
  testable and reusable **without Airflow** (e.g. `uv run pytest` on the host).

- `src/cgm_analytics/` is a real package defined in `pyproject.toml`.


## How the project gets into the containers

`/usr/local/airflow` is a path **inside the Docker image**, not on the host. It is
Airflow's home directory (`AIRFLOW_HOME`) and the image's working directory.

### At build time: copied into the image

The Astro Runtime base image has `ONBUILD` instructions. They run when *our*
`Dockerfile` builds `FROM` it, so our short `Dockerfile` effectively becomes:

```dockerfile
FROM astrocrpublic.azurecr.io/runtime:3.3-9
# --- hidden ONBUILD steps from the base image ---
COPY packages.txt .        # then apt-get install the listed packages
COPY requirements.txt .    # then pip install the listed packages
COPY . .                   # whole project -> /usr/local/airflow (minus .dockerignore)
# --- our own line ---
RUN pip install --no-cache-dir /usr/local/airflow
```

So the whole project (except what `.dockerignore` excludes) is **copied into the
image** at `/usr/local/airflow`. Our `RUN pip install` line then installs the
`cgm_analytics` package from `src/`, with the dependencies listed in
`pyproject.toml`.

Why `pip install <folder>`:

- `pyproject.toml` stays the single source of truth for dependencies. After
  `uv add <package>`, the next image build installs it; there's no need to also
  list it in `requirements.txt`.
- The `src/` layout is kept. The alternative, copying the code into `include/`
  and adjusting import paths, is messy.
- Packages already in the image that satisfy our requirements (e.g. `requests`)
  are left alone, so Airflow's own versions don't change.

### What "building" the package means

After `pip install`, our code is an installed library, just like `pylibrelinkup`
or `requests`:

1. **Build:** pip uses the build backend set in `pyproject.toml` (`uv_build`) to
   package `src/cgm_analytics/` into a **wheel** (`cgm_analytics-0.1.0-py3-none-any.whl`),
   the standard file format for distributing Python libraries.
2. **Install:** pip unpacks the wheel into the image's **site-packages**, the
   folder where Python looks for installed libraries
   (`/home/astro/.local/lib/python3.14/site-packages/cgm_analytics/`, next to
   `pylibrelinkup`).

So:

- Any code in the containers can `import cgm_analytics`, from any folder, with no
  path tricks. The DAGs don't need to know where `src/` is.
- `pip show cgm-analytics` and `pip list` show it like any other package (version
  `0.1.0`, from `pyproject.toml`).
- It's a **copy**: a snapshot of `src/` taken at build time. The containers import
  that copy, not the files in the repo, which is why changes to `src/` need
  `astro dev restart`.

### At runtime: some folders are mounted on top

Every container starts from that image. `astro dev` also mounts these local
folders over the copies baked into the image:

```
host (this repo)    inside each container
dags/        ──▶    /usr/local/airflow/dags/
include/     ──▶    /usr/local/airflow/include/
plugins/     ──▶    /usr/local/airflow/plugins/
tests/       ──▶    /usr/local/airflow/tests/
```

> **Remember:** changes in `dags/` and `include/` are picked up live, but `src/`
> is not mounted. The `cgm_analytics` package was installed into the image at
> build time, so after changing code in `src/` (or `pyproject.toml`,
> `Dockerfile`, `requirements.txt`, `packages.txt`), rebuild with
> `astro dev restart`. Otherwise the containers keep running the old code.

To look inside a running container:

```bash
astro dev bash              # shell in the scheduler container
ls -la /usr/local/airflow
pip show cgm-analytics      # confirms the package is installed
```

## Docker Compose: how `astro dev start` runs the containers

There is no `docker-compose.yaml` in this repo, but Docker Compose is still used.
The Astro CLI generates the Compose configuration internally from a template
built into the CLI. `astro dev start`:

1. **Builds the image** from our `Dockerfile` (see above).
2. **Generates the Compose configuration** and runs it with Docker Compose.
3. **Starts the containers** (see the table below).
4. **Mounts** `dags/`, `include/`, `plugins/` and `tests/` into the containers.
5. **Loads `.env`** as environment variables in every container, plus the
   connections and variables in `airflow_settings.yaml`.

It uses the **LocalExecutor**: tasks run inside the scheduler container, so there
are no Celery workers and no Redis. That is lighter than the `docker-compose.yaml`
from the official Airflow docs, which uses the CeleryExecutor.

To see the generated Compose file (Airflow must be running):

```bash
astro dev object export --compose --compose-file compose.yaml
```

### Containers and images

| Container | Image | Command it runs |
|---|---|---|
| `scheduler` | **our image** (built from `Dockerfile`) | `airflow scheduler` (also runs the tasks, LocalExecutor) |
| `dag-processor` | **our image** | `airflow dag-processor` (parses DAG files, separate service since Airflow 3) |
| `api-server` | **our image** | `airflow api-server` (UI + REST API on http://localhost:8080) |
| `triggerer` | **our image** | `airflow triggerer` (for deferrable tasks) |
| `postgres` | a standard Postgres image | Airflow's metadata database (DAG runs, task states, connections, ...) |

**Why the four Airflow containers share one image:** they are the same Airflow
installation, each started with a different command. All of them need the DAGs,
the `cgm_analytics` package and the same dependencies, because the DAG processor
parses the DAG files and the tasks run in the scheduler. Building one image keeps
them identical.

**Why Postgres is separate:** it doesn't need Airflow or our code. It's just a
database server, so it uses a plain Postgres image. The Airflow containers reach
it over the Docker network that Compose creates.

To check:

```bash
astro dev ps
docker ps --format 'table {{.Names}}\t{{.Image}}'
```

### Adding containers: `docker-compose.override.yml`

To add a service (e.g. a separate Postgres database for the glucose data), create
`docker-compose.override.yml` in the project root. `astro dev start` merges it
into the generated Compose configuration:

```yaml
services:
  cgm-db:
    image: postgres:17
    env_file:
      - ./cgm-db.env         # POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB (not in git)
    ports:
      - "127.0.0.1:5433:5432" # localhost only; 5432 on the host is taken by Airflow's own Postgres
    volumes:
      - cgm_db_data:/var/lib/postgresql/data   # keeps data across restarts
    networks:
      - airflow              # Astro's network, so Airflow can reach it

volumes:
  cgm_db_data:
```

- `networks: - airflow` puts the container on the same network as Airflow.
  Without it, Airflow can't reach it. Compose prefixes the name with the project,
  so the real network is `cgm-analytics_121cb8_airflow`
  (`docker network ls | grep cgm-analytics`).
- `postgres:17` is pinned on purpose: Postgres 18 moved the data directory, which
  breaks this volume path.

Each setting is explained in the comments of `docker-compose.override.yml`.

### The `airflow` network: user-defined, not Docker's default

Docker always has a network called `bridge`, used by `docker run` when no
`--network` is given. Compose never uses it: it creates its own **user-defined**
bridge network for each project. Astro's generated Compose file defines one
called `airflow`, and Compose prefixes it with the project name:

```bash
docker network ls
# cgm-analytics_121cb8_airflow   bridge   ← user-defined, created by Compose
# bridge                         bridge   ← Docker's default, not used here
```

The difference that matters: **only user-defined networks have DNS between
containers.** Each container is registered under its service name, so `cgm-db`
resolves to its address on the network (e.g. `172.18.0.5`). That's why the
Airflow connection and the dashboard use `cgm-db` as the host. On the default
`bridge`, names don't resolve and containers can only reach each other by IP,
which changes every time a container is recreated.

Every service that needs to talk to another one must join the same network
(`networks: - airflow`). Services on different networks can't see each other.

### Airflow connection to `cgm-db`

The DAGs need to know where the database is and how to log in. Instead of
hardcoding that in the code, Airflow uses **connections**: named sets of
credentials stored outside the code. A DAG only refers to the connection's ID:

```python
from airflow.providers.postgres.hooks.postgres import PostgresHook

hook = PostgresHook(postgres_conn_id="cgm_db")
```

The hook looks up `cgm_db`, reads host, port, user and password, and opens the
connection.

`PostgresHook` comes from the Postgres provider, which isn't in the Astro Runtime
image. It's listed in `requirements.txt`

#### Defined as an environment variable in `.env`

Connections can live in the UI (metadata database), in `airflow_settings.yaml`,
or in environment variables. Airflow treats any variable named
`AIRFLOW_CONN_<CONNECTION_ID in uppercase>` as a connection:

```
AIRFLOW_CONN_CGM_DB='postgresql://cgm:cgm@cgm-db:5432/cgm'
```

defines the connection `cgm_db`. It goes in `.env` because the Astro CLI passes
`.env` to every container, it's gitignored (the password stays out of git), it
survives `astro dev kill` (UI-created connections don't)- Connections defined this way don't show up in the UI's connection list; that's normal.

#### What the URI means

```
postgresql://cgm:cgm@cgm-db:5432/cgm
│            │   │   │      │    │
│            │   │   │      │    └─ database name   (POSTGRES_DB)
│            │   │   │      └────── port            (inside the Docker network)
│            │   │   └───────────── host            (service name in the override file)
│            │   └───────────────── password        (POSTGRES_PASSWORD)
│            └───────────────────── user            (POSTGRES_USER)
└────────────────────────────────── connection type (tells Airflow it's Postgres)
```



Run `astro dev restart` after creating or changing the override file. The same
service block works in a plain `docker-compose.yml`, so it isn't Astro-specific.

### Airflow connection to LibreLinkUp

The LibreLinkUp credentials are also an Airflow connection, `librelinkup`,
instead of plain environment variables read with `os.environ`.

#### Why a connection instead of `os.environ`

- **Masking in logs:** Airflow automatically hides connection passwords in task
  logs. A value read directly from `os.environ` isn't registered as a secret, so
  if it's ever printed or appears in an error, it shows in plain text.
- **One mechanism for all secrets:** the database and the API credentials work
  the same way.
- **Storage can change without code changes:** connections can come from
  environment variables, the metadata database or a secrets backend (HashiCorp
  Vault, AWS Secrets Manager, ...). The DAG only knows the ID `librelinkup`.

`.env` doesn't go away: the connection is **how the code reads** the secret,
`.env` is still **where the value is stored**.

#### How log masking works

Airflow never writes `.env` or the environment variables to the logs on its own.
Masking is about what happens **if the code ever outputs a password**.

Airflow's **secrets masker** keeps a list of values known to be secrets and,
before writing any line to a task log, replaces them with `***`. Reading a
connection with `BaseHook.get_connection(...)` registers its password on that
list. A value read with `os.environ[...]` is just a Python string: Airflow
doesn't know it's a password, so it's never registered.

It makes a difference when the password ends up in a log by accident: a debug
`print`, an error message that includes it, or a library logging its requests:

```
password from the connection:  INFO - Logging in with password ***
password from os.environ:      INFO - Logging in with password MyRealPassword123
```

- Nothing leaks today: the code doesn't print the password. Masking is a
  **safety net** for mistakes, not a fix for a current problem.
- Only the **password** is masked, not the login (the email would still show).
- Values shorter than 5 characters aren't masked (that's the "Skipping masking
  for a secret as it's too short" warning for the `cgm` database password):
  masking every "cgm" would garble the logs.

#### Defined in `.env`, in JSON format

```
AIRFLOW_CONN_LIBRELINKUP='{"conn_type": "generic", "login": "you@example.com", "password": "your-password"}'
```

- `AIRFLOW_CONN_LIBRELINKUP` defines the connection `librelinkup`, like
  `AIRFLOW_CONN_CGM_DB` does for `cgm_db`.
- **JSON instead of a URI:** the login is an email, and the URI format uses `@`
  as a separator, so it would have to be written `you%40example.com`, plus any
  special characters in the password encoded. JSON has named fields, so values
  go in as they are (tested: `@ : / #` are read correctly).
- `"conn_type": "generic"` is Airflow's type for "just credentials", used when
  there's no dedicated provider. LibreLinkUp has none, and `pylibrelinkup`
  handles the URLs itself, so no `host` is needed.
- The single quotes `'...'` keep the whole JSON as one value (it contains spaces
  and double quotes).

`.env` is only read when the containers start, so apply changes with
`astro dev restart`, then check:

```bash
astro dev run connections get librelinkup
```

## Running Airflow

### Start it and test the DAG

```bash
astro dev start
```

The first run builds the image (slow; later builds reuse the cached layers) and
starts the containers. Then:

1. Open http://localhost:8080.
2. Find `fetch_glucose`, switch it on and click **Trigger**.
3. Open the run, click the `fetch_readings` task and go to **Logs**. It should show
   "Authentication successful." followed by the readings.

If the DAG doesn't show up in the UI, it probably failed to import. Check the
scheduler/DAG processor logs or run the tests (below).

### Useful commands

```bash
astro dev ps          # list running containers
astro dev logs -s     # scheduler logs (DAG import errors show here)
astro dev pytest      # run tests/ inside the container
astro dev bash        # shell inside the scheduler container
astro dev restart     # rebuild the image after changing src/, Dockerfile, requirements
astro dev stop        # stop the containers (data is kept)
astro dev kill        # remove containers AND volumes (data is deleted)
```

### Stop, restart, kill: what happens to the data

"Data" here is Airflow's **metadata database** (the `postgres` container): the
history of DAG and task runs, which DAGs are on or paused, connections and
variables created in the UI, and XComs.

Postgres keeps its files in a **Docker volume**, storage that Docker manages
separately from the container. Stopping a container doesn't touch its volume.

| Command | Containers | Metadata DB (volume) |
|---|---|---|
| `astro dev stop` | stopped | **kept** |
| `astro dev restart` | rebuilt and restarted | **kept** |
| `astro dev kill` | removed | **deleted** |

`astro dev kill` gives a fresh, empty Airflow: no run history, all DAGs paused.
Connections defined in `.env` or `airflow_settings.yaml` come back on the next
start, because they are loaded from files.

> **Warning:** volumes declared in `docker-compose.override.yml` (e.g.
> `cgm_db_data` for `cgm-db`) belong to the same Compose project, so
> `astro dev kill` will most likely delete them too, **including the stored
> glucose readings**. Once there is real data, use `stop`/`restart` day to day
> and back up (e.g. `pg_dump`) before any `kill`.

### After a reboot: the containers come back on their own

The Compose configuration that Astro generates gives every Airflow container
`restart: unless-stopped`, and `cgm-db` has the same setting in
`docker-compose.override.yml`. Docker starts at boot (the `docker` systemd
service is enabled) and restarts every container with that policy. So after a
reboot the whole stack is running again **without `astro dev start`**.

`unless-stopped` means "restart it, unless it was stopped on purpose":

| Before the reboot | After the reboot |
|---|---|
| running | started again |
| stopped with `astro dev stop` | stays stopped |

To check a container's policy:

```bash
docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' cgm-analytics_121cb8-cgm-db-1
```

### Docker waits for `/home` to be mounted

On this machine `/home` is a **separate partition**, mounted during boot. Without
extra configuration, systemd can start Docker **before** `/home` is mounted.
That broke the DAGs once:

1. Docker restarted the containers and set up the bind mounts (`dags/`,
   `include/`, `plugins/`, `tests/`).
2. `/home/miguel/6.Projects/cgm-analytics/dags` didn't exist yet. When a bind
   mount's source is missing, Docker **creates it**: an empty folder owned by
   root, on the root partition.
3. That empty folder was mounted into the containers. A bind mount always
   **hides** what the image has at that path (no merging, no fallback), so the
   copy of `dags/` baked into the image was hidden too.
4. Then `/home` was mounted on top. The host showed the real files, but the
   containers still saw the empty folder: `Found 0 files for bundle
   dags-folder` in the DAG processor logs, and no DAG in the UI.

`cgm_analytics` still worked, because `src/` isn't mounted: it's installed in
the image.

**Fix:** a systemd drop-in that makes Docker wait for `/home`:

```bash
sudo systemctl edit docker
```

```ini
[Unit]
RequiresMountsFor=/home
```

```bash
sudo systemctl daemon-reload
```

- `systemctl edit` doesn't change the original `docker.service`, which a package
  update would overwrite. It writes an override file
  (`/etc/systemd/system/docker.service.d/override.conf`) that systemd combines
  with the original.
- `RequiresMountsFor=/home` tells systemd that Docker needs `/home`. Docker
  starts only after `/home` is mounted, and doesn't start if that mount fails.

To check:

```bash
systemctl show docker -p RequiresMountsFor   # should print RequiresMountsFor=/home
```

If the DAGs ever disappear after a reboot again, `astro dev restart` recreates
the containers with the real folders mounted.