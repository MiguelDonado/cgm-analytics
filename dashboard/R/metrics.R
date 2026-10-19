# Glucose metrics with iglu. iglu expects a data frame with columns id, time, gl.
to_iglu <- function(readings) {
  data.frame(id="me", time=readings$time, gl=readings$gl)
}