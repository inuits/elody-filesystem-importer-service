### Base stage
FROM python:3.12-alpine AS base-stage

ENV FLASK_APP=app.py

RUN adduser --disabled-password --home /app --shell /bin/bash app

USER app
WORKDIR /app

COPY docker/entrypoint*.sh /
COPY requirements.txt ./

RUN echo "export PATH=${PATH}:/app/.local/bin" >> .bashrc

ENTRYPOINT ["/entrypoint.sh"]

### Development stage
FROM base-stage AS development-stage

ENV APP_ENV=dev

COPY docker/pip.conf /etc

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

### Build stage
FROM base-stage AS build-stage

COPY api ./api

RUN --mount=type=secret,id=PIP_INDEX_URL,uid=1000 \
  --mount=type=secret,id=PIP_TRUSTED_HOST,uid=1000 \
  export PIP_INDEX_URL="$(cat /run/secrets/PIP_INDEX_URL)" \
  PIP_TRUSTED_HOST="$(cat /run/secrets/PIP_TRUSTED_HOST)" && \
  pip install --no-cache-dir -r requirements.txt

### Production stage
FROM base-stage AS production-stage

ENV APP_ENV=prod

COPY --from=build-stage /app /app

ENV GUNICORN_CMD_ARGS="--workers=3"

EXPOSE 8000
