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
