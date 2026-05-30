FROM ghcr.io/astral-sh/uv:alpine

RUN apk add --no-cache git

ENV UV_NO_DEV=1
COPY . /app
WORKDIR /app
RUN uv sync --locked

ENTRYPOINT [ "uv", "run", "gunicorn", "iou:app" ]
