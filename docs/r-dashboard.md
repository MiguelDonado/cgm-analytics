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

## App structure: the `R/` folder

```
dashboard/
├── app.R      ← ui, server, shinyApp()
└── R/
    └── db.R   ← connect_cgm_db(), read_readings(), read_last_time()
```

`app.R` calls `connect_cgm_db()` without any `source("R/db.R")`. That works
because when Shiny starts an app (`shiny::runApp()` or RStudio's **Run App**),
it first sources every `.R` file in the `R/` folder next to `app.R`, in
alphabetical order (since Shiny 1.5, done by `shiny::loadSupport()`). By the
time `app.R` runs, the functions already exist.

R has no `import` like Python: `source("R/db.R")` just runs the file, and the
functions it defines become available. Shiny does that step automatically.

**The catch:** this only happens when Shiny starts the app. Running `app.R` line
by line in the console, or with `source("app.R")`, doesn't load `R/`, and fails
with `could not find function "connect_cgm_db"`. Run `source("R/db.R")` first in
that case.

Adding `source("R/db.R")` at the top of `app.R` would also work, but under
`runApp()` the file would then be sourced twice. Relying on the `R/` folder is
the Shiny convention, and it scales as more files are added (`R/metrics.R`,
`R/plots.R`, ...).

### Code outside vs. inside `server`

```r
# Outside server: runs once, when the app starts
readings <- reactivePoll(..., session = NULL, ...)

ui <- function(request) {
  # A function: runs once per page load
}

server <- function(input, output, session) {
  # Inside server: runs once per browser session (each tab that opens the app)
}
```

| Where | Runs | Use for |
|---|---|---|
| Top of `app.R` (outside `server`) | Once, when the app starts | Work shared by all sessions: loading data, settings |
| `ui` as a function | Once per page load | Page content that depends on the data (the date range) |
| Inside `server` | Once per browser session | Per-user state: inputs, outputs, reactives |

Defining `readings` at the top means the data is loaded once and shared by every
session, instead of hitting the database each time a tab opens. It's a
`reactivePoll()`, so it also reloads when new readings arrive (see
[Refreshing the data](#refreshing-the-data-reactivepoll)).

### The Apply button: one `eventReactive()`, the rest `reactive()`

Only the first step of the chain is tied to its triggers: the Apply button and
new readings. Everything after it is a plain `reactive()`:

```r
filtered <- eventReactive(list(input$apply, readings()), { ... },   # waits for Apply
                          ignoreNULL = FALSE)                       # or new readings
cgm      <- reactive(to_iglu(filtered()))                            # follows filtered()
metrics  <- reactive(summary_metrics(cgm()))                         # follows cgm()

output$agp_plot <- renderPlot(plot_agp(cgm(), ...))
```

```
Apply click  ─┐
              ├→ filtered() → cgm() → metrics() → value boxes
new readings ─┘                     → agp_plot, lasagna_plot
```

The first argument of `eventReactive()` is what triggers it. A `list()` of
triggers reruns it when **any** of them changes: a click, or a new value of
`readings()` from the [`reactivePoll()`](#refreshing-the-data-reactivepoll). So
the plot redraws on its own when new readings arrive, without clicking Apply.

A `reactive()` recomputes when a reactive it reads changes, and nothing else.
`cgm()` only reads `filtered()`, which only changes on those two triggers, so
`cgm()`, `metrics()` and every output downstream follow the same rule.
Moving the date picker changes `input$dates`, but it isn't a trigger: inside
`eventReactive()` it's only read, so it's ignored until one of the triggers
fires.

**Edge case:** if the picker was moved without clicking Apply and new readings
arrive meanwhile, the automatic refresh uses the dates currently in the picker,
as if Apply had been clicked. Rare for a personal dashboard; if it matters,
store the applied dates in a `reactiveVal()` on Apply and filter with those.

Tying every step to `input$apply` with its own `eventReactive()` would behave
the same, but repeats the trigger everywhere. Adding a new output would then
mean remembering to tie it to the button too. With one gate at the start,
new outputs just read `cgm()` or `metrics()` and follow the button
automatically. Each reactive is also cached: `cgm()` is computed once per
trigger and shared by all the outputs that use it.


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

## Refreshing the data: `reactivePoll()`

The readings used to be loaded once, at the top of `app.R`. That's fine when the
app is started by hand, but the container runs for days, so the dashboard would
freeze at the moment it started. `reactivePoll()` keeps the data current:

```r
readings <- reactivePoll(
  intervalMillis = 5 * 60 * 1000,
  session = NULL,
  checkFunc = function() { ... read_last_time(con) },  # cheap: one value
  valueFunc = function() { ... read_readings(con) }    # expensive: every row
)
```

```
every 5 min → checkFunc: SELECT max(factory_timestamp)
                  │
                  ├── same as last time → nothing happens
                  └── changed           → valueFunc: SELECT all readings
                                            → readings() has a new value
                                            → every output that uses it reruns
```

- **`checkFunc`** returns something that changes when there's new data: the time
  of the latest reading (`read_last_time()` in `R/db.R`). It's one small query,
  answered from the index on `factory_timestamp`.
- **`valueFunc`** loads all the readings. It runs once at startup and then only
  when `checkFunc` returns something different: with an hourly DAG, at most once
  an hour. The `date` column is computed here, so it's redone on every reload.
- **5 minutes**: the dashboard is at most 5 minutes behind the database, at the
  cost of one tiny query every 5 minutes.
- **`on.exit(DBI::dbDisconnect(con))`** closes the connection when the function
  finishes, even if the query fails. No connection stays open between checks.

`readings` is now a **reactive expression**, not a data frame: its value is read
by calling it, `readings()`, like `filtered()` or `cgm()`.

### `session = NULL`: one copy for every visitor

Defined at the top of `app.R` (outside `server`), with `session = NULL`, the poll
doesn't belong to any visitor:

- It runs as long as the app runs; closing a tab doesn't stop it.
- Every session reads the same `readings()`: ten open tabs mean one check every
  5 minutes and one copy of the data in memory, not ten.
- When it gets a new value, Shiny reruns whatever uses `readings()` in **every**
  open session, so open tabs update without reloading the page.

### `isolate()`: read a reactive value once, without following it

Reactive values work like cells in a spreadsheet. When a formula reads a cell,
it's **linked** to it: change the cell and the formula recomputes. In Shiny, the
"formulas" are `reactive()`, `eventReactive()`, the `render*()` functions and
`observe()`; they're called **reactive contexts**. Reading `readings()` inside
one links them, and that's how outputs update on their own.

Outside a reactive context (at the top of `app.R`, or in the `ui`), there's no
formula to link, so nothing could ever recompute. Shiny refuses instead of
silently giving a value that will never update:

```
Error: Operation not allowed without an active reactive context.
```

`isolate()` says: *give me the current value, once, and don't link anything*.
It's like copying a cell and pasting the value instead of a formula.

```r
min(readings()$date)            # top of app.R: error, nothing to link to
min(isolate(readings())$date)   # works: current value, read once
```

It's used where the value is only needed at that moment, such as the date
range for the date picker when the page is built. Inside `server`, reactives
read `readings()` without `isolate()`, because there the link is what makes
them update.

### The date picker follows the data

New readings must also become selectable in the date picker. Two pieces handle
that, and neither changes the dates the user selected:

**On each page load: `ui` is a function.** A plain `ui <- page_sidebar(...)` is
built once, when the app starts, so the picker's range would stay fixed at that
moment. As a function, Shiny builds the page on every visit, with the range of
the data at that time:

```r
ui <- function(request) {
  days <- isolate(readings())$date
  page_sidebar(
    ...
    dateRangeInput("dates", "Dates",
      start = min(days), end = max(days),
      min = min(days), max = max(days), ...)
  )
}
```

Building the page isn't a reactive context, hence `isolate()`.

**In open tabs: an observer moves the limits.**

```r
observe({
  days <- readings()$date
  updateDateRangeInput(session, "dates", min = min(days), max = max(days))
})
```

- `observe()` reruns whenever a reactive it reads changes, like `reactive()`, but
  returns nothing: it's for **doing** something, here updating the picker.
- `updateDateRangeInput()` only changes the arguments it's given. `start` and
  `end` aren't passed, so the user's selection stays as it is; only the range
  of selectable days grows.
- `session` tells Shiny which tab's picker to update, which is why `server`
  takes it as an argument.

The plot redraws on its own with the fresh data: `filtered` is triggered by
new readings as well as by Apply (see
[The Apply button](#the-apply-button-one-eventreactive-the-rest-reactive)).

**Why `ui` must be a function.** `ui <- page_sidebar(...)` is evaluated once,
when the app starts, and every visitor gets that same page: open it on Friday
in a container started on Monday, and the picker ends on Monday. A function is
a recipe Shiny runs on every page load, so it reads the data at that moment.
It's the same difference as `x <- Sys.time()` (one time, stored forever) and
`f <- function() Sys.time()` (the current time, each call).

**Why both pieces are needed.** The observer also runs when a tab opens, so it
would fix the limits on its own, but it never touches `start`/`end`. Without the
`ui` function, the default selection would stay frozen at startup.

| Piece | Runs | Sets |
|---|---|---|
| `ui` as a function | On each page load | The default selection (first → latest day) and the limits |
| The observer | When new data loads, in open tabs | Only the limits, so new days become selectable |

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

### System libraries

Binaries don't need compiling, but they still link against system libraries at
runtime (`libpq` for RPostgres, `libuv` for fs, `libicu` for stringi, ...). A
missing one fails the build with `unable to load shared object ... cannot open
shared object file`. Posit Package Manager lists what every package in
`renv.lock` needs (run from `dashboard/`):

```bash
pkgs=$(python3 -c "import json;print('&'.join('pkgname='+p for p in json.load(open('renv.lock'))['Packages']))")
curl -s "https://packagemanager.posit.co/__api__/repos/cran/sysreqs?all=false&distribution=ubuntu&release=24.04&$pkgs"
```

## Running in Docker

The dashboard runs as one more container next to Airflow and `cgm-db`, defined
as the `dashboard` service in `docker-compose.override.yml`.

| File | Role |
|---|---|
| `dashboard/Dockerfile` | `rocker/r-ver` (same R version as `renv.lock`) + system libraries + `renv::restore()` + the app |
| `dashboard/.env` | Connection settings for `db.R`, not in git (template: `dashboard/.env.example`) |
| `docker-compose.override.yml` | Runs the image on the `airflow` network, port `127.0.0.1:3838` |

### The image is built by hand

Astro only builds its own Airflow image: it ignores `build:` in the override
file (`No such image: cgm-analytics_121cb8-dashboard`). So the service uses a
local image, `image: cgm-dashboard` with `pull_policy: never`, built separately.
After changing `app.R`, `R/`, `renv.lock` or the Dockerfile:

```bash
docker build -t cgm-dashboard dashboard && astro dev restart
```

The Dockerfile copies `renv.lock` and runs `renv::restore()` **before** copying
the app code. Docker caches each step, so changing `app.R` rebuilds in seconds;
only a change in `renv.lock` reinstalls the packages.

### Connection settings: Docker network values

`db.R` reads the same variables everywhere, with different values:

| Where the app runs | File | Host | Port |
|---|---|---|---|
| RStudio on the laptop | `dashboard/.Renviron` | `localhost` | `5433` (the port published on the host) |
| The container | `dashboard/.env` | `cgm-db` | `5432` (Postgres' own port, over the Docker network) |

### Listening on `0.0.0.0`

The container starts Shiny with `host = '0.0.0.0'`. Shiny's default,
`127.0.0.1`, is the container's own loopback: Docker forwards requests from the
host's port 3838 to the container's network interface (`eth0`, an address like
`172.18.0.5`), never to its loopback, so Shiny would never see them. `0.0.0.0`
listens on all interfaces.

```
browser → host localhost:3838
            │  Docker NAT rule
            ▼
        container eth0 172.18.0.5:3838  ✅ Shiny on 0.0.0.0 hears it
        container lo   127.0.0.1:3838   ❌ nothing arrives here
```
