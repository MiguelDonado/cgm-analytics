# Same R version as in renv.lock
# rocker/r-ver is a minimal Ubuntu (noble) image with just R installed
FROM rocker/r-ver:4.6.1

# System libraries the R packages need. The packages come precompiled, so
# nothing is built from source, but they still link against these libraries
# at runtime (libpq for RPostgres, the rest for tidyverse and the plots).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libpq-dev \
        libuv1-dev libicu-dev zlib1g-dev \
        libxml2-dev libcurl4-openssl-dev libssl-dev \
        libfontconfig1-dev libfreetype6-dev libharfbuzz-dev libfribidi-dev \
        libpng-dev libtiff-dev libjpeg-dev libwebp-dev \
      && rm -rf /var/lib/apt/lists/*

# Use /app as the current directory for subsequent instructions
WORKDIR /app

# Install the R packages BEFORE copying the app code. Docker caches each step,
# so editing app.R doesn't reinstall every package.

# Copy two files into the current working directory inside the image
COPY renv.lock .Rprofile ./
# Copy two files into the renv directory inside /app
COPY renv/activate.R renv/settings.json renv/
# R starts in /app
#       |
#       v
# R reads /app/.Rprofile
#        |
#        v
# .Rprofile sources renv/activate.R
#        |
#        v
# renv activates the project environment
#        |
#        v
# R uses the project's package library

# Starts R executes the command and then exits
# renv::restore(): Attempts to install the recorded versions into
# project's library 
RUN R -e "renv::restore(prompt = FALSE)"

# The app itself. Shiny automatically sources every file in R/.
COPY app.R ./
COPY R/ R/

# Shiny's usual port. EXPOSE only documents it; the actual forwarding from the
# host comes from `ports:` in docker-compose.override.yml.
EXPOSE 3838

# A machine answers on several addresses, one per network interface, like a
# person who answers to both "Mike" and "Migue":
#   - lo   127.0.0.1   loopback: only reachable from inside the container
#   - eth0 172.x.x.x   the container's address on Docker's bridge network
# When the browser opens localhost:3838 on the host, Docker forwards the
# request to the container's eth0 address, never to its loopback. Listening on
# 0.0.0.0 (all interfaces) makes Shiny answer there; with 127.0.0.1 the request
# would never reach it.
CMD ["R", "-e", "shiny::runApp('/app', host = '0.0.0.0', port = 3838)"]

