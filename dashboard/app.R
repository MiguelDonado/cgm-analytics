# Reactive programming is a style of programming that focuses on values that 
# change over time, and calculations and actions that depend on those values. 

library(shiny)
library(dplyr)
library(bslib)
library(iglu)

# reactivePoll(): Used in Shiny applications to repeatedly check for changes in 
# a reactive expression at a specified time interval.
# readings is the reactive expression that gets created

# Every 5 minutes:
# 1. checkFunc(): Change detector
# 2. valueFunc(): Data retrieval
# session = NULL: not tied to one visitor, it runs as long as the app runs.
readings <- reactivePoll(
  intervalMillis = 5 * 60 * 1000,
  session = NULL,
  checkFunc = function() {
    con <- connect_cgm_db()
    on.exit(DBI::dbDisconnect(con))
    read_last_time(con)
  },
  valueFunc = function() {
    con <- connect_cgm_db()
    on.exit(DBI::dbDisconnect(con))
    readings <- read_readings(con)
    # Local calendar day of each reading
    readings$date <- as.Date(readings$time, tz = "Europe/Madrid")
    readings
  }
)

# Dynamic UI
# ui <- page_sidebar(...)                    # value: built once, when the app starts
# ui <- function(request) page_sidebar(...)  # function: built again on every page visit

# The difference matters because of start = min(days) and end = max(days):

# - As a value: the dates are read once, when the R process starts. 
#   On Posit Connect that process can stay alive for days. 
#   A visitor tomorrow would see a picker that stops at whatever the last reading 
#   was at startup, even though the DAG has stored more since.

# - As a function: Shiny calls it on each page load, so the picker's range 
#   always ends at the latest reading.

# isolate(): only the current value is needed to build the page (see docs/r-dashboard.md).
ui <- function(request) {
  # We use isolate() because without it we get an error readings() is a reactive expression
  # Shiny only lets you read a reactive from inside something that can react to it, 
  # like renderPlot(), observe() or reactive(). Those re-run when the reactive changes. 
  # The ui function is ordinary code and has no way to re-run, so Shiny refuses the read.
  # isolate() tells Shiny you only want the current value and don't want to react to future changes.
  days <- isolate(readings())$date

  # Fresh install: no readings stored yet, so there are no dates from the picker
  if (length(days) == 0) {
    return(page_fillable(
      title = "CGM dashboard",
      card(
        card_header("No readings yet"),
        "The fetch_glucose DAG stores new readings every hour. Reload this 
        page after its first run."
      )
    ))
  }

  page_sidebar(
    title = "CGM dashboard",
    sidebar = sidebar(
      dateRangeInput(
        "dates", "Dates",
        # Default values
        start = min(days), end = max(days),
        min = min(days), max = max(days),
        # Start of the week: Monday
        weekstart = 1,
        format = "dd-mm-yy"
      ),
      actionButton("apply", "Apply", class = "btn-primary")
    ),
    card(
      card_header("Ambulatory glucose profile"),
      plotOutput("agp_plot")
    )
  )
}

server <- function(input, output, session) {
  # Step 1
  # Empty DB (fresh install): ui showed the "No readings yet" page, which has
  # no inputs or outputs, so there is nothing for the server to set up.
  # isolate(): Reads the value of a reactive expression without creating a reactive dependency
  if (nrow(isolate(readings())) == 0) return()
  
  # Step 2
  # Dynamic UI
  observeEvent(readings(), {
    days <- readings()$date
    updateDateRangeInput(
      session, "dates",
      min = min(days),
      max = max(days)
    )
  })
  
  # Step 3
  # Filter "readings" df by the chosen range of dates
  # filtered has two reactive dependencies on:
  # 1. input$apply   computed only when Apply is clicked 
  # 2. readings()    when new data is available
  filtered <- eventReactive(list(input$apply,readings()), {
    readings() |>
      filter(
        date >= input$dates[1] & date <= input$dates[2]
      )
  }, ignoreNULL = FALSE)
  
  # Step 4
  # Create cgm reactive expression
  cgm <- reactive(to_iglu(filtered()))
  
  # Step 5
  # Update AGP plot in the UI
  output$agp_plot <- renderPlot({
    n_days <- length(unique(filtered()$date))
    validate(need(n_days >= 1, paste("The AGP needs at least 1 day of data, the selected range has", n_days)))
    agp(cgm(), tz = "Europe/Madrid")
  })
}

shinyApp(ui, server)