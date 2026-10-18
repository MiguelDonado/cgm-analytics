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
    └── db.R   ← connect_cgm_db(), read_readings()
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
con <- connect_cgm_db()
readings <- read_readings(con)
DBI::dbDisconnect(con)

server <- function(input, output, session) {
  # Inside server: runs once per browser session (each tab that opens the app)
}
```

| Where | Runs | Use for |
|---|---|---|
| Top of `app.R` (outside `server`) | Once, when the app starts | Work shared by all sessions: loading data, settings |
| Inside `server` | Once per browser session | Per-user state: inputs, outputs, reactives |

Loading the readings at the top means they're read once and shared by every
session, instead of hitting the database each time a tab opens. The connection
is closed right after the read, so no connection stays open while the app runs.

### The Apply button: one `eventReactive()`, the rest `reactive()`

Only the first step of the chain is tied to the button. Everything after it is
a plain `reactive()`:

```r
filtered <- eventReactive(input$apply, { ... }, ignoreNULL = FALSE)  # waits for Apply
cgm      <- reactive(to_iglu(filtered()))                            # follows filtered()
metrics  <- reactive(summary_metrics(cgm()))                         # follows cgm()

output$agp_plot <- renderPlot(plot_agp(cgm(), ...))
```

```
Apply click → filtered() → cgm() → metrics() → value boxes
                                 → agp_plot, lasagna_plot
```

A `reactive()` recomputes when a reactive it reads changes, and nothing else.
`cgm()` only reads `filtered()`, which only changes when Apply is clicked, so
`cgm()`, `metrics()` and every output downstream also update only on Apply.
Moving the date picker changes `input$dates`, but only `filtered` reads it, and
`eventReactive()` ignores it until the button is pressed.

Tying every step to `input$apply` with its own `eventReactive()` would behave
the same, but repeats the trigger everywhere. Adding a new output would then
mean remembering to tie it to the button too. With one gate at the start,
new outputs just read `cgm()` or `metrics()` and follow the button
automatically. Each reactive is also cached: `cgm()` is computed once per click
and shared by all the outputs that use it.


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
