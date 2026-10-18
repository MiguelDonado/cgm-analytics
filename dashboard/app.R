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
  layout_column_wrap(
    width = 1/4,
    fill = FALSE,
    value_box("Time in range", textOutput("tir")),
    value_box("Mean glucose", textOutput("mean")),
    value_box("GMI", textOutput("gmi")),
    value_box("CV", textOutput("cv"))
  ),
  card(
    card_header("Ambulatory glucose profile"),
    plotOutput("agp_plot")
  ),
  card(
    card_header("Lasagna plot"),
    plotOutput("lasagna_plot")
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
    validate(need(n_days >= 14, paste("The AGP needs at least 14 days of data, the selected range has", n_days)))
    plot_agp(cgm(), tz = "Europe/Madrid")
  })
  
  output$lasagna_plot <- renderPlot({
    plot_glu(
      cgm(), 
      plottype = "lasagna",
      datatype = "average",
      color_scheme = "red-orange",
      tz = "Europe/Madrid")
  })
  
  metrics <- reactive(summary_metrics(cgm()))
  
  output$tir  <- renderText(sprintf("%.0f %%", metrics()$tir))
  output$mean <- renderText(sprintf("%.0f mg/dL", metrics()$mean))
  output$gmi  <- renderText(sprintf("%.1f %%", metrics()$gmi))
  output$cv   <- renderText(sprintf("%.0f %%", metrics()$cv))
}

shinyApp(ui, server)