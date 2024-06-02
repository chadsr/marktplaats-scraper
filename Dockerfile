ARG PYTHON_MAJOR_MINOR_VERSION="3.12"

FROM python:${PYTHON_MAJOR_MINOR_VERSION}-alpine

LABEL org.opencontainers.image.title="marktplaats-scraper" \
    org.opencontainers.image.description="Scrape listings from Marktplaats and save to CSV file." \
    org.opencontainers.image.source="https://github.com/chadsr/marktplaats-scraper"

ARG PYTHON_MAJOR_MINOR_VERSION
ARG MP_USER="mp"
ARG MP_GROUP="mp"
ARG MP_UID="1000"
ARG MP_GID="1001"

ENV PYTHONUNBUFFERED=1

# install chromium & deps
RUN apk update
RUN apk add --no-cache --update chromium chromium-chromedriver xvfb gcc musl-dev libffi-dev linux-headers g++ build-base python3-dev

# upgrade pip
RUN pip install --no-cache-dir --upgrade pip

RUN pip install --no-cache-dir poetry

RUN addgroup -g ${MP_GID} -S ${MP_GROUP} && adduser -u ${MP_UID} -S ${MP_USER} -G ${MP_GROUP}

RUN mkdir /app && chown -R ${MP_USER}:${MP_GROUP} /app

RUN mkdir /data && chown -R ${MP_USER}:${MP_GROUP} /data
VOLUME [ "/data" ]

USER ${MP_USER}
WORKDIR /app

COPY --chown=${MP_USER}:${MP_GROUP} ./mpscraper ./mpscraper
COPY --chown=${MP_USER}:${MP_GROUP} ./pyproject.toml ./pyproject.toml
COPY --chown=${MP_USER}:${MP_GROUP} ./poetry.lock ./poetry.lock
COPY --chown=${MP_USER}:${MP_GROUP} ./README.md ./README.md
COPY --chown=${MP_USER}:${MP_GROUP} ./LICENSE ./LICENSE

RUN poetry install --compile --without=dev

CMD [ "poetry", "run", "python", "-m", "mpscraper", "--chromium-path", "/usr/bin/chromium-browser", "--driver-path", "/usr/bin/chromedriver", "--data-dir", "/data" ]
