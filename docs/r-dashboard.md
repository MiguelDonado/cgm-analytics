# R dashboard

Notes on the R Shiny dashboard in `dashboard/`.

## What Shiny is for

Shiny is popular for **interactive data apps and dashboards**, not for general
websites. It's widely used in pharma (clinical trial data), academia, and for
internal analytics dashboards: an R user can build a web app without knowing
HTML, CSS or JavaScript, reusing the R code they already use for analysis.

Public websites (shops, blogs, social apps) use frameworks like Django, Rails or
Next.js instead, because each Shiny visitor holds a live connection to an R
session on the server (expensive to scale to many users), the page is generated
after it loads (bad for search engines), and custom design and user flows are
harder.

A personal dashboard (one user, interactive exploration of our own data, analysis
code in R with `iglu`) is exactly what Shiny is built for.

## Database access: DBI

`DBI` is R's standard **interface** to databases. A separate **driver** package
does the actual talking to a specific database:

| Layer | Package | Role |
|---|---|---|
| Interface | `DBI` | Defines the common functions: `dbConnect()`, `dbGetQuery()`, `dbExecute()`, `dbDisconnect()`, ... |
| Driver | `RPostgres` | Implements those functions for Postgres |

The same DBI code works with other databases by swapping the driver:
`RSQLite::SQLite()`, `RMariaDB::MariaDB()`, `duckdb::duckdb()`, or
`odbc::odbc()` (SQL Server and others). That's why the connection reads
`DBI::dbConnect(RPostgres::Postgres(), ...)`: DBI's function, told which driver
to use.

### Common functions

| Function | Use |
|---|---|
| `dbConnect()` / `dbDisconnect()` | Open / close a connection |
| `dbGetQuery(con, sql)` | Run a `SELECT`, get a data frame back |
| `dbExecute(con, sql)` | Run `INSERT` / `UPDATE` / `CREATE`, returns the number of rows affected |
| `dbListTables(con)` | List the tables |
| `dbReadTable()` / `dbWriteTable()` | Read or write a whole table as a data frame |

## Loading data: everything once vs. one query per selection

### Data size

One reading every 15 minutes:

| Period | Readings | Approx. size in R |
|---|---|---|
| 1 day | 96 | — |
| 1 year | ~35,000 | ~1 MB |
| 10 years | ~350,000 | ~10 MB |

Even after 10 years, that's small for R: loading takes a fraction of a second
and filtering an in-memory data frame is instant.

### The two options

**A. Load everything once, filter in R (chosen)**

```
app starts → SELECT all readings → data frame in memory
user picks dates → filter in R → iglu → metrics (instant)
```

- One query; every interaction is instant.
- The metrics are computed in R either way (`iglu` can't run inside Postgres),
  so the database's only job is to hand over the readings.
- Freshness: the DAG adds readings every hour, so data loaded at startup goes
  stale. `reactivePoll()` fixes it: every few minutes the app runs a cheap query
  (`SELECT max(factory_timestamp) FROM glucose_readings`) and reloads the data
  only when that value has changed.

**B. One query per selection**

```
user picks dates → SELECT ... WHERE factory_timestamp BETWEEN start AND end → iglu → metrics
```

- Always fresh, and scales to huge datasets (only the needed rows leave the
  database).
- But a query on every interaction: added latency and complexity with no benefit
  at this data size.

### Decision

Load all readings, refresh with `reactivePoll()` when new readings arrive, and do
date filtering and `iglu` metrics in R. Switch to B only if the data gets too big
for memory (millions of rows, many patients) or many users hit the app at once;
neither applies to a personal CGM dashboard, even after years of data.

## Package installs: source vs. binary (Posit Package Manager)

An R package comes in two forms:

| Form | What it is | Install speed |
|---|---|---|
| **Source** | The package's code, including C/C++ parts that must be **compiled** locally | Slow: minutes per package with C code (and `iglu` pulls in dozens of dependencies) |
| **Binary** | Already compiled, ready to use | Fast: seconds |

On Windows and macOS, CRAN serves binaries. **On Linux, CRAN only serves
source**, so every install compiles (which needs compilers and system development
libraries such as `libpq-dev`, `libssl-dev`).

**Posit Package Manager** (`packagemanager.posit.co`) is a free CRAN mirror that
serves **precompiled Linux binaries**, one set per distribution. For Ubuntu 24.04
("noble"), `dashboard/.Rprofile` sets it before activating renv:

```r
options(repos = c(CRAN = "https://packagemanager.posit.co/cran/__linux__/noble/latest"))

source("renv/activate.R")
```

`options()` must come **before** `source("renv/activate.R")`, so renv starts with
that repository. Check with `getOption("repos")` after restarting R.

### Why it matters for Docker

When the dashboard image is built, renv reinstalls every package listed in
`renv.lock`, and `renv.lock` also **records the repository** they come from:

- **Plain CRAN recorded:** the build compiles everything (possibly 20+ minutes,
  much longer on a Raspberry Pi), and the image needs compilers and development
  libraries, so it's bigger.
- **Posit Package Manager recorded:** the build downloads binaries (a minute or
  two), with a smaller image.

So the repository must be set **before** creating `renv.lock`.

**Raspberry Pi:** the URL above is for Ubuntu noble on x86-64. Binary
availability for the Pi's OS and ARM processor still has to be checked.
