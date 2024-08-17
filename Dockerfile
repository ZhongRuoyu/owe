# syntax=docker/dockerfile:1

FROM python:3.12-slim

RUN apt-get update && \
  apt-get install --no-install-recommends -y git && \
  rm -rf /var/lib/apt/lists/*

ADD . /app
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT [ "gunicorn", "src.app:app" ]
