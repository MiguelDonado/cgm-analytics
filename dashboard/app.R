library(shiny)
library(tidyverse)
library(bslib)
library(iglu)

# All readings, shared by every visitor. Every 5 minutes checkFunc asks for the
# time of the latest reading (cheap); only when it changes does valueFunc
# reload all the readings. session = NULL: not tied to one visitor, it runs as
# long as the app runs.
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

# A function instead of a fixed value: Shiny builds the page on each visit, so
# the default range includes the latest readings. isolate(): only the current
# value is needed to build the page (see docs/r-dashboard.md).
ui <- function(request) {
  days <- isolate(readings())$date

  # Fresh install: no readings stored yet, so there are no dates fro the picker
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
  # New readings: let the picker reach the new days. Only the limits change;
  # the dates the user selected stay as they are.
  observe({
    days <- readings()$date
    req(length(days) > 0)
    updateDateRangeInput(session, "dates", min = min(days), max = max(days))
  })

  # Readings in the chosen range; recomputed only when Apply is clicked 
  # or when new data is available
  # data 
  filtered <- eventReactive(list(input$apply,readings()), {
    readings() |>
      filter(
        date >= input$dates[1] & date <= input$dates[2]
      )
  }, ignoreNULL = FALSE)

  cgm <- reactive({
    req(nrow(filtered()) > 0)
    to_iglu(filtered())
  })
  output$agp_plot <- renderPlot({
    n_days <- length(unique(filtered()$date))
    validate(need(n_days >= 1, paste("The AGP needs at least 1 day of data, the selected range has", n_days)))
    # If I want to disable the daily plots: daily = FALSE
    # cgm(): Because cgm is the reactive expression, that contains the logic that only recomputed when the Apply button is clicked
    #        To pass its value, we need to call it as a function, cgm().
    agp(cgm(), tz = "Europe/Madrid")
  })
}

shinyApp(ui, server)