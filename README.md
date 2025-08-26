# Marktplaats Scraper

[![Python Tests](https://github.com/chadsr/marktplaats-scraper/actions/workflows/test.yml/badge.svg)](https://github.com/chadsr/marktplaats-scraper/actions/workflows/test.yml)
[![Docker Image CI](https://github.com/chadsr/marktplaats-scraper/actions/workflows/docker.yml/badge.svg)](https://github.com/chadsr/marktplaats-scraper/actions/workflows/docker.yml)
[![codecov](https://codecov.io/gh/chadsr/marktplaats-scraper/graph/badge.svg?token=UISQZBFTMR)](https://codecov.io/gh/chadsr/marktplaats-scraper)

Marktplaats.nl (Dutch Classifieds) Listing Scraper.

## Configuration

```shell
usage: mpscraper [-h] [--limit LIMIT] [--headless HEADLESS] [--chromium-path CHROMIUM_PATH]
                 [--driver-path DRIVER_PATH] [--timeout TIMEOUT] [--recrawl-hours RECRAWL_HOURS]
                 [--data-dir DATA_DIR] [--wait-seconds WAIT_SECONDS]

options:
  -h, --help            show this help message and exit
  --limit, -l LIMIT     The limit of new listings to scrape. (MP_LIMIT) (default: 0)
  --headless HEADLESS   Run browser in headless mode. (MP_HEADLESS) (default: False)
  --chromium-path CHROMIUM_PATH
                        Path to Chromium executable. (default: /usr/bin/chromium)
  --driver-path DRIVER_PATH
                        Path to Chromium ChromeDriver executable. (default: None)
  --timeout, -t TIMEOUT
                        Seconds before timeout occurs. (MP_TIMEOUT_SECONDS) (default: 10)
  --recrawl-hours, -r RECRAWL_HOURS
                        Recrawl listings that haven't been checked for this many hours or more
                        (MP_RECRAWL_HOURS) (default: 24)
  --data-dir, -d DATA_DIR
                        Directory to save output data. (default: ./)
  --wait-seconds WAIT_SECONDS
                        Seconds to wait before re-trying after being rate-limited. (MP_WAIT_SECONDS)
                        (default: 10)
```

## Running

### Docker

```shell
mkdir data/ && chown -R 1000:1000 data/
docker run -it -v ${PWD}/data:/data ghcr.io/chadsr/marktplaats-scraper:latest
```

### Poetry

```shell
poetry install
poetry run mpscraper -d data/
```

## Examples

1. [**Category Classification Model**](./examples/category_classification/) - Predicts the appropriate Marktplaats category for a given listing title text.
2. [**Category Statistics**](./examples/category_statistics/) - Calculates some basic data-science/statistics tasks for a given category, ranking views/popularity of listing types.
