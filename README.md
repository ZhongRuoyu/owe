# Owe

Owe is a simple web application for splitting bills and tracking who owes whom
how much.

## Overview

Owe lets a group of users record debts and payments between each other.
The Summary tab shows the minimum set of transactions needed to settle all
outstanding balances, and provides a one-click Settle button for each.

Core concepts:

- Users - participants identified by email address.
- Records - individual transactions of type `DEBT` (someone owes money) or
  `PAYMENT` (money has been physically transferred).
  Records can be cancelled (invalidated) if entered by mistake.
- Summary - the net balances across all active records, reduced to the minimum
  number of settlement transactions using
  [a simple greedy algorithm](https://stackoverflow.com/a/15723286).

## Requirements

Owe runs on Python 3.10 or later.
It uses SQLite for data storage, so no additional database setup is required.
For notifications, it can optionally integrate with Telegram via a bot token and
chat ID.

For development, [uv](https://github.com/astral-sh/uv) is recommended but
pip can also be used.

## Setup

Owe is available on PyPI as [`owe`](https://pypi.org/project/owe/).
You can get started with uv:

```sh
# Run the development server
uvx --with owe flask --app owe run
# Or run the production server with a WSGI server like Gunicorn
uvx --with owe gunicorn "owe:create_app()"
```

Or if you prefer pip:

```sh
# Install the package
pip install owe
# Run the development server
flask --app owe run
# Or run the production server with a WSGI server like Gunicorn
pip install gunicorn
gunicorn "owe:create_app()"
```

### App factory customization

The application exposes an app factory, `create_app`, with two optional
keyword arguments:

- `url_prefix`: Prefix all registered routes (e.g. `"/owe"`).
- `api_only`: Register only the API blueprint (skip the bundled UI).

For example, to run API-only routes under `/owe`:

```sh
# With Flask
uvx --with owe flask --app "owe:create_app(api_only=True, url_prefix='/owe')" run

# With Gunicorn
uvx --with owe gunicorn "owe:create_app(api_only=True, url_prefix='/owe')"
```

With this configuration, API endpoints are served under `/owe/...`.

### Environment variables

The application can be configured with the following environment variables:

- `OWE_LOG_LEVEL`: Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`,
  `CRITICAL`).
  Default: `INFO`.
- `OWE_DATABASE`: Path to the SQLite database file.
  Default: `owe.db`.
- `OWE_CURRENCY`: ISO 4217 currency code displayed in the UI.
  Default: `USD`.
- `OWE_REQUEST_EMAIL_HEADER`: HTTP header to trust for the authenticated user's
  email, to be used as the creator of records.
  When run behind Cloudflare Access, this can be set to
  `cf-access-authenticated-user-email` so that the application can identify the
  user by their email address.
  When unset, the remote IP address will be used to identify the user instead.
  Default: unset.
- `OWE_TELEGRAM_BOT_TOKEN`: Telegram bot token for notifications.
  Default: unset.
- `OWE_TELEGRAM_CHAT_ID`: Telegram chat ID for notifications.
  Default: unset.

## Docker

Docker images are available on Docker Hub as
[`zhongruoyu/owe`](https://hub.docker.com/r/zhongruoyu/owe),
and on GitHub Container Registry as
[`ghcr.io/zhongruoyu/owe`](https://ghcr.io/zhongruoyu/owe).
The `main` tag tracks the latest commit on the main branch,
and the `latest` and named `v<version>` tags track the stable releases.

You may run the application with Docker as follows:

```sh
docker run -p 8000:8000 \
  -v /path/to/data:/data \
  -e OWE_DATABASE=/data/owe.db \
  -e OWE_CURRENCY=USD \
  zhongruoyu/owe:main \
  --bind "0.0.0.0:8000" \
  --workers 4
```

The container image runs the [Gunicorn](https://gunicorn.org/) WSGI server and
accepts its command-line arguments, so you can customize the server
configuration (e.g. `--bind` for socket binding, `--workers` for the number of
worker processes) using standard Gunicorn options.
Run with `--help` for details.

## API Endpoints

The server exposes the following API endpoints:

- `GET /api/config`: Get application configuration (e.g. currency).
- `GET /api/users`: List all users.
- `GET /api/records`: List all active and inactive records.
- `POST /api/records`: Create a new record.
  Request body should be JSON with the following fields:
  - `type`: "DEBT" or "PAYMENT"
  - `lender`: email of the lender
  - `borrowers`: list of emails of the borrowers
  - `amount`: total amount (will be split evenly among borrowers)
  - `remarks`: optional remarks for the record
- `PATCH /api/records/status`: Update the status of records.
  Request body should be JSON with the following fields:
  - `ids`: list of record IDs to update
  - `active`: boolean indicating whether the records should be active or
    inactive
- `GET /api/summary`:
  Get the minimum set of settlement transactions.

## Utilities

The package also comes with two command-line utilities:

- `owe-dump`: Dump all records in the database as CSV.
  Use `--output` to set the output file path (default: `records.csv`);
  use `--database` to choose the SQLite database file (default: `owe.db`).
- `owe-users`: Manage users from the command line.
  Use `--database` to choose the SQLite database file (default: `owe.db`).
  Usage:
  - `owe-users [--database <path>] create <email> <name>`:
    Add a user with the given email and name.
  - `owe-users [--database <path>] list`: List all users.
  - `owe-users [--database <path>] activate <email>`:
    Activate the user with the given email.
  - `owe-users [--database <path>] deactivate <email>`:
    Deactivate the user with the given email.

To run these utilities:

```sh
# With uv
uvx --with owe owe-dump --output records.csv
uvx --with owe owe-users --database owe.db list

# With pip
pip install owe
owe-dump --output records.csv
owe-users --database owe.db list
```

## License

This project is licensed under the MIT License.
See the [LICENSE](LICENSE) file for details.
