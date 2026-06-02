import logging
import sqlite3
from html import escape
from pathlib import Path
from typing import Any, cast

from flask import Blueprint, Flask, Response, current_app, request

import iou.database as db
import iou.iou as service
from iou.config import AppConfigItems
from iou.record import AggregatedRecord

API_PREFIX = "/api"
STATIC_DIR = Path(__file__).resolve().parent / "static"

logger = logging.getLogger(__name__)


def app_config() -> AppConfigItems:
  """Return typed app config values for the current request context."""
  return cast("AppConfigItems", current_app.config)


def init(app: Flask) -> None:
  """Initialize logging and database schema for the app."""
  config = cast("AppConfigItems", app.config)
  logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=getattr(logging, config["LOG_LEVEL"], logging.INFO),
  )
  db.init(config["DATABASE"])


def get_requester() -> str:
  """Return requester identity from configured header or remote address."""
  request_email_header = app_config()["REQUEST_EMAIL_HEADER"]
  if request_email_header:
    email = request.headers.get(request_email_header)
    if email:
      return email
  return request.remote_addr or "unknown"


app = Blueprint(
  "iou",
  __name__,
  url_prefix="",
  static_folder=STATIC_DIR,
  static_url_path="",
)


@app.after_request
def add_csp(response: Response) -> Response:
  """Attach a strict content security policy to outgoing responses."""
  response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "script-src 'self' https://cdnjs.cloudflare.com; "
    "style-src 'self' https://cdnjs.cloudflare.com; "
    "img-src 'self' data:; "
  )
  return response


@app.route("/")
def index() -> Response:
  """Serve the single-page application entry point."""
  return app.send_static_file("index.html")


api = Blueprint("api", __name__, url_prefix=API_PREFIX)
app.register_blueprint(api)


@api.route("/config")
def get_config() -> dict[str, Any]:
  """Return client-facing configuration values."""
  return {"currency": app_config()["CURRENCY"]}


@api.route("/users")
def get_users() -> list[dict[str, Any]]:
  """Return active users for UI selection."""
  users = db.get_users(app_config()["DATABASE"], active_only=True)
  return [user.asdict() for user in users]


@api.route("/records")
def get_records() -> dict[str, dict[str, Any]]:
  """Return all records keyed by record ID as strings."""
  records = db.get_records(app_config()["DATABASE"])
  return {str(record.id): record.asdict() for record in records}


def validate_add_records_request(  # noqa: PLR0911
  req: dict[str, Any],
  valid_emails: set[str],
) -> tuple[bool, str]:
  """Validate the add-record request body and referenced user emails."""
  for key in ["type", "lender", "borrowers", "amount", "remarks"]:
    if key not in req:
      return False, f"Missing field: {key}"

  req_type = req["type"]
  if not isinstance(req_type, str) or req_type not in {"DEBT", "PAYMENT"}:
    return False, 'type must be either "DEBT" or "PAYMENT"'

  lender = req["lender"]
  if not isinstance(lender, str):
    return False, "lender must be a string"

  borrowers = req["borrowers"]
  if (
    not isinstance(borrowers, list)
    or not borrowers
    or not all(isinstance(borrower, str) for borrower in borrowers)
  ):
    return False, "borrowers must be a non-empty list of strings"

  amount = req["amount"]
  if not isinstance(amount, (int, float)) or amount <= 0:
    return False, "amount must be a positive number"

  remarks = req["remarks"]
  if not isinstance(remarks, str) and remarks is not None:
    return False, "remarks must be a string or null"

  if lender not in valid_emails:
    return False, f"Unknown lender: {escape(lender)}"

  if unknown_borrowers := set(borrowers) - valid_emails:
    borrowers_str = escape(
      # https://github.com/astral-sh/ty/issues/521
      ", ".join(email for email in unknown_borrowers),  # ty:ignore[no-matching-overload]
    )
    return False, f"Unknown borrower(s): {borrowers_str}"

  return True, ""


@api.route("/records", methods=["POST"])
def add_records() -> tuple[dict[str, Any], int]:
  """Create an aggregated record and persist its split entries."""
  req = request.get_json()
  if not req:
    return {"success": False, "error": "Request body must be JSON"}, 400

  users = db.get_users(app_config()["DATABASE"], active_only=True)
  valid_emails = {u.email for u in users}
  valid, error = validate_add_records_request(req, valid_emails)
  if not valid:
    return {"success": False, "error": error}, 400

  record = AggregatedRecord(
    type=req["type"],
    lender=req["lender"],
    borrowers=req["borrowers"],
    amount=req["amount"],
    created_by=get_requester(),
    remarks=req["remarks"],
  )
  try:
    service.add_records(record)
  except sqlite3.Error:
    logger.exception("Database error in add_records")
    return {"success": False, "error": "Database error"}, 500

  return {"success": True}, 200


@api.route("/records/status", methods=["PATCH"])
def set_records_active() -> tuple[dict[str, Any], int]:
  """Update the active flag for a batch of records."""
  req = request.get_json()
  if not req:
    return {"success": False, "error": "Request body must be JSON"}, 400

  ids = req.get("ids", [])
  active = req.get("active")
  if not ids or not all(isinstance(i, int) for i in ids):
    return {
      "success": False,
      "error": "ids must be a non-empty list of integers",
    }, 400
  if not isinstance(active, bool):
    return {"success": False, "error": "active must be a boolean"}, 400

  try:
    service.set_records_active(
      ids,
      active=active,
      requester=get_requester(),
    )
  except sqlite3.Error:
    logger.exception("Database error in set_records_active")
    return {"success": False, "error": "Database error"}, 500

  return {"success": True}, 200


@api.route("/summary")
def summary() -> list[service.SummaryTransaction]:
  """Return settlement transactions computed from net balances."""
  return service.get_summary()
