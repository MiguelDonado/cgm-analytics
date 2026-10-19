# Database access for the dashboard: connection to cgm-db and queries.
# Connection settings come from environment variables (dashboard/.Renviron)

connect_cgm_db <- function() {
  DBI::dbConnect(
    RPostgres::Postgres(),
    host     = Sys.getenv("CGM_DB_HOST"),
    port     = as.integer(Sys.getenv("CGM_DB_PORT")),
    dbname   = Sys.getenv("CGM_DB_NAME"),
    user     = Sys.getenv("CGM_DB_USER"),
    password = Sys.getenv("CGM_DB_PASSWORD")
  )
}

read_readings <- function(con) {
  readings <- DBI::dbGetQuery(con, "
    SELECT factory_timestamp AS time, value_mg_dl AS gl
    FROM glucose_readings
    ORDER BY factory_timestamp
  ")
  # Same instants, displayed in Spanish lcoal time
  attr(readings$time, "tzone") <- "Europe/Madrid"
  readings
}

# reactivePoll() needs a cheap function that returns something
# that changes when new data arrives.
read_last_time <- function(con) {
  DBI::dbGetQuery(con, "
    SELECT max(factory_timestamp) AS last_time
    FROM glucose_readings
  ")$last_time
}