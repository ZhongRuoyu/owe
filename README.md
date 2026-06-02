# IOU

IOU ("I Owe You") is a simple web application for splitting bills and tracking
who owes whom how much.

## Overview

IOU lets a group of users record debts and payments between each other.
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

- Python 3.10 or later
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- (Optional) A Telegram bot token and chat ID for record notifications.

## Setup

You can get started with uv:

```sh
# Sync dependencies
uv sync
# Run the development server
uv run flask --app iou run
# Or run the production server with gunicorn
uv run gunicorn "iou:create_app()"
```

Or if you prefer pip:

```sh
# Create a virtual environment
python3 -m venv .venv
# Activate the virtual environment
source .venv/bin/activate
# Install dependencies
pip install .
# Run the development server
flask --app iou run
# Or run the production server with gunicorn
gunicorn "iou:create_app()"
```

### Environment variables

The application can be configured with the following environment variables:

- `LOG_LEVEL`: Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`,
  `CRITICAL`).
  Default: `INFO`.
- `DATABASE`: Path to the SQLite database file.
  Default: `iou.db`.
- `CURRENCY`: ISO 4217 currency code displayed in the UI.
  Default: `USD`.
- `REQUEST_EMAIL_HEADER`: HTTP header to trust for the authenticated user's
  email, to be used as the creator of records.
  When run behind Cloudflare Access, this can be set to
  `cf-access-authenticated-user-email` so that the application can identify the
  user by their email address.
  When unset, the remote IP address will be used to identify the user instead.
  Default: unset.
- `TELEGRAM_BOT_TOKEN`: Telegram bot token for notifications.
  Default: unset.
- `TELEGRAM_CHAT_ID`: Telegram chat ID for notifications.
  Default: unset.

## Docker

Docker images are available on Docker Hub as
[`zhongruoyu/iou`](https://hub.docker.com/r/zhongruoyu/iou),
and on GitHub Container Registry as
[`ghcr.io/zhongruoyu/iou`](https://ghcr.io/zhongruoyu/iou).
The `main` tag tracks the latest commit on the main branch.

You may run the application with Docker as follows:

```sh
docker run -p 8000:8000 \
  -v /path/to/data:/data \
  -e DATABASE=/data/iou.db \
  -e CURRENCY=USD \
  zhongruoyu/iou:main --bind "0.0.0.0:8000"
```

The container image runs gunicorn and accepts its command-line arguments, so you
can customize the server configuration (e.g. `--bind` for socket binding) using
standard gunicorn options; run with `--help` for details.

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

- `iou-dump`: Dump all records in the database as CSV.
  Control the database path with the `DATABASE` environment variable,
  and the output file with the `RECORDS` environment variable (default:
  `records.csv`).
- `iou-users`: Manage users from the command line.
  Usage:
  - `iou-users create <email> <name>`: Add a user with the given email and name.
  - `iou-users list`: List all users.
  - `iou-users activate <email>`: Activate the user with the given email.
  - `iou-users deactivate <email>`: Deactivate the user with the given email.

To run these utilities:

```sh
# With uv
uv run iou-dump
uv run iou-users list

# With pip, after `pip install .`
iou-dump
iou-users list
```

## License

This project is licensed under the MIT License.
See the [LICENSE](LICENSE) file for details.
