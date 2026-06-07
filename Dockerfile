FROM python:3.14.5-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_LOCKED=1
ENV UV_NO_DEV=1
ENV UV_NO_EDITABLE=1
ENV UV_PYTHON_DOWNLOADS=never
WORKDIR /app

RUN \
  --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  <<RUN
  set -eux
  uv sync --no-install-project
RUN

COPY . /app
RUN \
  --mount=type=cache,target=/root/.cache/uv \
  <<RUN
  set -eux
  uv sync --all-groups --all-extras
  uv pip install gunicorn
RUN

FROM python:3.14.5-alpine

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
CMD [ "gunicorn", "owe.app:create_app()" ]
