FROM ghcr.io/astral-sh/uv:alpine

RUN apk add --no-cache git tzdata

ENV UV_NO_DEV=1
COPY . /app
WORKDIR /app
RUN uv sync --locked

ENTRYPOINT [ "uv", "run", "gunicorn", "src.app:app" ]
