# Airflow concepts

Notes on Airflow concepts used in this project's DAGs.

## Tasks: operators vs. `@task`

Airflow has two ways to create a task. Both produce the same kind of object and
live side by side in the same DAG.

### Operators: a ready-made task class

An **operator** is a class that already knows how to do one kind of job. No
logic is written; it's just configured:

```python
create_table = SQLExecuteQueryOperator(
    task_id="create_table",               # the task's name in the UI
    conn_id="cgm_db",                     # which database
    sql="create_glucose_readings.sql",    # what to run
)
```

`SQLExecuteQueryOperator` already contains "open a connection, run this SQL,
close it". Creating the object **inside the DAG function** registers it as a task
of that DAG. There's no Python function because there's no custom logic.

Other examples: `BashOperator` (runs a shell command), `EmailOperator` (sends an
email).

### `@task`: a Python function becomes a task

When no ready-made operator does the job, the logic is written as a function and
`@task` turns it into a task:

```python
@task
def fetch_readings():
    ...  # our own code
```

Under the hood, `@task` **also creates an operator**: a Python operator that runs
the function. It's a shorter way to write it. This style is called **TaskFlow**.

### Side by side

| | Operator | `@task` |
|---|---|---|
| What is written | Configuration (arguments) | A Python function |
| Who writes the logic | Airflow / the provider | Us |
| Task name | `task_id="..."` | The function name |
| Use when | A ready-made operator does the job (run SQL, a shell command, ...) | Custom Python (call the LibreLinkUp API, transform data) |

Both connect the same way:

```python
create_table >> loaded       # operator → @task
```

### Creating a task is not running it

Neither `SQLExecuteQueryOperator(...)` nor calling `fetch_readings()` inside the
DAG function executes anything when the DAG file is parsed. They only declare
"this task exists, with this configuration". The SQL and the function body run
later, when the scheduler runs the task.

## Passing data between tasks: XCom vs. external storage

Each task runs as a separate process, so data passes between tasks as an
**XCom**: the return value of one task, stored in Airflow's metadata database
and read back by the next task.

**XCom is for small values**: IDs, counts, file paths, at most a few hundred
rows. `fetch_glucose` passes ~48 small dicts per run (a few KB), which is exactly
the intended use.

**External storage** (write the data to a database or object storage, and pass
only a reference through XCom) is better when:

- the data is big: large XComs slow down and bloat the metadata database, which
  every Airflow component depends on;
- several tasks or DAGs need the same intermediate data;
- the intermediate data should be kept after the run, for auditing or
  reprocessing.

**Decision:** keep XCom. A staging table just to replace it would add complexity
with no benefit at this data size.

**Possible future improvement: a raw layer.** The pipeline goes API → parse →
table. If a parsing mistake were found later, old readings couldn't be re-derived:
the API only goes back 14 days and there's no backfill (see
`docs/data-model.md`). Storing the API's JSON as-is before parsing would fix that:

```
fetch_readings → raw_glucose_responses   (API JSON as-is, one row per run)
              → glucose_readings        (parsed, upserted, used by the analytics)
```

This is a common pattern (raw/staging, or bronze/silver layers). The risk is
small here, since `glucose_readings` already stores nearly every field, so it's
an option to keep in mind rather than something needed now.

## Retries: fixed vs. exponential backoff

With only `retries` set, Airflow waits a **fixed** `retry_delay` (default 5
minutes) between attempts; `retry_exponential_backoff` is `False` by default.

`fetch_glucose` uses exponential backoff:

```python
default_args={
    "retries": 3,
    "retry_delay": timedelta(minutes=2),          # first wait
    "retry_exponential_backoff": True,            # double the wait each time
    "max_retry_delay": timedelta(minutes=30),     # upper limit for any single wait
}
```

The wait roughly doubles each time (~2, 4, 8 minutes), plus a little randomness
so failing tasks don't all retry at the same instant. `max_retry_delay` caps a
single wait if `retries` is raised later. All retries finish within ~15
minutes, well before the next hourly run.

**Why exponential:**

- The likely failures come from an external API: temporary overload or rate
  limiting (HTTP 430). Retrying quickly just gets rejected again; waiting longer
  each time gives the API time to recover.
- It costs nothing at this scale, and it's the standard pattern for anything
  that calls an external API.

**Why not more retries:** the next hourly run fetches the same ~12-hour window
anyway, so no data is lost if all retries fail. More retries would only mean
more calls to an API that's already failing.

## Missed runs: `catchup`

When the scheduler is down (machine off, asleep), hourly runs are missed. When
it comes back, `catchup` decides what happens to them:

- `catchup=True`: run **all** the missed runs, one per missed hour.
- `catchup=False`: run **only the last one** (the most recent hour that has
  passed) and skip the rest.

`catchup=False` does **not** mean "skip all of them". Example: machine off from
23:07 to 07:18 (CEST):

```
22:00  23:00  00:00  01:00  02:00  03:00  04:00  05:00 | 05:19 UTC, scheduler back
 └──────────────── missed ───────────────────┘   └ latest passed → runs now
```

The 05:00 UTC run starts at 05:19, as soon as the scheduler is up.
