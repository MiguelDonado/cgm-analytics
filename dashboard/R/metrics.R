# Glucose metrics with iglu. iglu expects a data frame with columns id, time, gl.
to_iglu <- function(readings) {
  data.frame(id="me", time=readings$time, gl=readings$gl)
}

summary_metrics <- function(cgm) {
  list(
    mean = iglu::mean_glu(cgm)$mean,
    tir  = iglu::in_range_percent(cgm, list(c(70, 180)))$in_range_70_180,
    gmi  = iglu::gmi(cgm)$GMI,
    cv   = iglu::cv_glu(cgm)$CV
  )
}