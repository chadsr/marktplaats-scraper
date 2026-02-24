
FROM python:3.14-alpine

ARG MP_USER="mp"
ARG MP_GROUP="mp"
ARG MP_UID="1000"
ARG MP_GID="1000"

LABEL org.opencontainers.image.title="marktplaats-scraper" \
    org.opencontainers.image.description="Scrape listings from Marktplaats and save to CSV file." \
    org.opencontainers.image.source="https://github.com/chadsr/marktplaats-scraper"

ENV PYTHONUNBUFFERED=1

RUN apk update
RUN apk add --no-cache --update chromium chromium-chromedriver xvfb uv

RUN addgroup -g ${MP_GID} -S ${MP_GROUP} && adduser -u ${MP_UID} -S ${MP_USER} -G ${MP_GROUP}

RUN mkdir /app && chown -R ${MP_USER}:${MP_GROUP} /app

RUN mkdir /data && chown -R ${MP_USER}:${MP_GROUP} /data
VOLUME [ "/data" ]

USER ${MP_USER}
WORKDIR /app

COPY --chown=${MP_USER}:${MP_GROUP} ./mpscraper ./mpscraper
COPY --chown=${MP_USER}:${MP_GROUP} ./pyproject.toml ./pyproject.toml
COPY --chown=${MP_USER}:${MP_GROUP} ./uv.lock ./uv.lock
COPY --chown=${MP_USER}:${MP_GROUP} ./README.md ./README.md
COPY --chown=${MP_USER}:${MP_GROUP} ./LICENSE ./LICENSE

RUN uv sync --no-group dev

CMD [ "uv", "run", "--no-group", "dev", "mpscraper", "--chromium-path", "/usr/bin/chromium-browser", "--driver-path", "/usr/bin/chromedriver", "--data-dir", "/data" ]
