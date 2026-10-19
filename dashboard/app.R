library(shiny)
library(tidyverse)
library(bslib)
library(iglu)

# Load all readings once at startup
con <-connect_cgm_db()
readings <- read_readings(con)
DBI::dbDisconnect(con)

# Local calendar day of each reading
readings$date <- as.Date(readings$time, tz = "Europe/Madrid")
first_day <- min(readings$date)
last_day <- max(readings$date)


ui <- page_sidebar(
  title = "CGM dashboard",
  sidebar = sidebar(
    dateRangeInput(
      "dates", "Dates",
      # Default values
      start = first_day, end = last_day,
      min = first_day, max = last_day,
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

server <- function(input, output) {
  # Readings in the chosen range; recomput, ed only when Apply is clicked
  filtered <- eventReactive(input$apply, {
    readings |> 
      filter(
        date >= input$dates[1] & date <= input$dates[2], 
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