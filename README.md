# Owe

Owe is a simple web application for splitting bills and tracking who owes whom
how much.

## Overview

Owe lets a group of users record debts and payments between each other.
The Summary tab shows the minimum set of transactions needed to settle all
outstanding balances, and provides a one-click Settle button for each.

Core concepts:

- Users - participants identified by string ID.
- Records - individual transactions of type `DEBT` (someone owes money) or
  `PAYMENT` (money has been physically transferred).
  Records can be cancelled (invalidated) if entered by mistake.
- Summary - the net balances across all active records, reduced to the minimum
  number of settlement transactions using
  [a simple greedy algorithm](https://stackoverflow.com/a/15723286).

## Requirements

Owe runs on Python 3.10 or later.
It uses SQLite for data storage, so no additional database setup is required.

For development, [uv](https://github.com/astral-sh/uv) is recommended but
pip can also be used.

## Setup

Owe is available on PyPI as [`owe`](https://pypi.org/project/owe/), and as a
Homebrew formula `zhongruoyu/tap/owe`.
You can get started as follows:

```sh
# With uv
uv tool install owe

# With pip
pip install owe

# With Homebrew
brew install zhongruoyu/tap/owe
```

Docker images are available on Docker Hub as
[`zhongruoyu/owe`](https://hub.docker.com/r/zhongruoyu/owe),
and on GitHub Container Registry as
[`ghcr.io/zhongruoyu/owe`](https://ghcr.io/zhongruoyu/owe).
The `latest` and named `v<version>` tags track the stable releases,
and the `main` tag tracks the latest commit on the main branch.
You may run Owe with Docker as follows:

```sh
docker run --rm -v "$PWD/owe.db":/owe.db zhongruoyu/owe owe record list
```

This Docker command runs the `owe record list` command to list all records in
the default database file `owe.db`.
Read on for more details on using the command-line interface and running the web
server.

## Command-line interface

Owe provides a command-line utility, `owe`, for managing users and records from
the command line.
Use it as follows:

- `owe [--database <path>] user list [--active] [--format <format>]`:
  List all users, or only active users if `--active` is specified.
- `owe [--database <path>] user add <id> <name>`:
  Add a user with the given ID and name.
- `owe [--database <path>] user <activate|deactivate> <id>`:
  Activate or deactivate the user with the given ID.
- `owe [--database <path>] record list [--active] [--format <format>]`:
  List all records, or only active records if `--active` is specified.
- `owe [--database <path>] record add [options...] [--format <format>]`:
  Add a record with the specified options and list the created records.
  Options:
  - `--type <DEBT|PAYMENT>`: Type of the record (required).
  - `--lender <id>`: ID of the lender (required).
  - `--borrower <id>`: ID of the borrower (required).
    Pass multiple `--borrower` for multiple borrowers.
  - `--amount <amount>`: Total amount (will be split evenly among borrowers)
    (required).
  - `--created-by <id>`: ID of the user creating the record (required).
  - `--remarks <remarks>`: Optional remarks for the record.
- `owe [--database <path>] record <activate|cancel> [--id <id> ...]`:
  Update the status of records with the given IDs to active or inactive.
- `owe [--database <path>] record summary [--format <format>]`:
  Show the summary of settlements.

The `--database` option allows you to choose the SQLite database file;
if not specified, it defaults to `owe.db` in the current directory.
`--format` can be set to `table` (default) for more human-readable output,
or `json` or `csv` for more machine-friendly output.

## Web server

Owe also includes a server in the `owe.app` module, which serves the same
functionality over a REST API, with an optional web user interface for managing
records and users.
To get started, you can run the server with uv and an ASGI server like
[Uvicorn](https://uvicorn.dev/), as follows:

```sh
uvx --with owe uvicorn --factory owe.app:create_app
```

Or if you prefer pip:

```sh
pip install owe uvicorn
uvicorn --factory owe.app:create_app
```

Note that the server does not handle authentication or authorization by itself,
so it is strongly recommended to run it in a trusted environment (e.g. behind a
reverse proxy with access control or in a trusted local network) to prevent
unauthorized access.

### Telegram notifications

Owe also supports sending notifications on record creation and alteration to a
Telegram chat.
To enable this, a Telegram bot must be created and added to the target chat, and
the bot token and chat ID must be set in the environment, as described in the
next section.

### Environment variables

The application can be configured with the following environment variables:

- `OWE_URL_PREFIX`: URL prefix for all endpoints (e.g. `/owe`).
  Default: unset.
- `OWE_API_ONLY`: If set to a non-empty value (e.g. `true`), the server will
  serve the API at the specified URL prefix without the web user interface;
  if unset, the server will serve a web user interface at the URL prefix, and
  the API will be available under the `/api` subpath of the URL prefix.
  Default: unset (i.e. serve the web UI).
- `OWE_LOG_LEVEL`: Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`,
  `CRITICAL`).
  Default: `INFO`.
- `OWE_DATABASE`: Path to the SQLite database file.
  Default: `owe.db`.
- `OWE_CURRENCY`: ISO 4217 currency code displayed in the UI.
  Default: `USD`.
- `OWE_REQUEST_ID_HEADER`: HTTP header to trust for the authenticated user's ID,
  to be used as the creator of records.
  When run behind Cloudflare Access, this can be set to
  `cf-access-authenticated-user-email` so that the application can identify the
  user by their email address.
  When unset, the remote IP address will be used to identify the user instead.
  Default: unset.
- `OWE_TRUST_PROXY`: Whether to trust the `X-Forwarded-For` header for the
  remote IP address.
  This should be set to a non-empty value (e.g., `true`) when running behind a
  reverse proxy that sets this header, and unset otherwise, to prevent IP
  spoofing.
  Default: unset (i.e. do not trust the header).
- `OWE_TELEGRAM_BOT_TOKEN`: Telegram bot token for notifications.
  Default: unset.
- `OWE_TELEGRAM_CHAT_ID`: Telegram chat ID for notifications.
  Default: unset.

### API Endpoints

The server exposes the following API endpoints:

- `GET /api/config`: Get application configuration (e.g. currency).
- `GET /api/users`: List all users.
- `GET /api/records`: List all active and inactive records.
- `POST /api/records`: Create a new record.
  Request body should be JSON with the following fields:
  - `type`: "DEBT" or "PAYMENT"
  - `lender`: ID of the lender
  - `borrowers`: list of IDs of the borrowers
  - `amount`: total amount (will be split evenly among borrowers)
  - `remarks`: optional remarks for the record
- `PATCH /api/records/status`: Update the status of records.
  Request body should be JSON with the following fields:
  - `ids`: list of record IDs to update
  - `active`: boolean indicating whether the records should be active or
    inactive
- `GET /api/summary`:
  Get the minimum set of settlement transactions.

For API endpoints that create or modify records, the creator of the record is
determined from the `OWE_REQUEST_ID_HEADER` header if set, or from the remote
IP address otherwise.

### Running the web server with Docker

The Docker image includes the Uvicorn ASGI server, which you can use to run the
application in production:

```sh
docker run -d \
  -p 8000:8000 \
  -v "$PWD/owe.db":/owe.db \
  -e OWE_CURRENCY=USD \
  zhongruoyu/owe \
  uvicorn --factory owe.app:create_app --host 0.0.0.0 --port 8000 --workers 4
```

## License

This project is licensed under the MIT License.
See the [LICENSE](LICENSE) file for details.
