import logging
import sqlite3
import threading
from html import escape
from http import HTTPStatus
from typing import Any, cast

from flask import Blueprint, Flask, current_app, request

from owe.database import SqliteDatabase
from owe.owe import Owe
from owe.record import AggregatedRecord, RecordType

from .config import AppConfigItems
from .schema import AddRecordsRequest, SetRecordsActiveRequest, parse
from .telegram_announcer import TelegramAnnouncer

OWE_SERVICE_EXTENSION_KEY = "owe.service"
TELEGRAM_ANNOUNCER_EXTENSION_KEY = "owe.telegram_announcer"

logger = logging.getLogger(__name__)


class AppServiceTypeError(TypeError):
  """Raised when an app-level service has an unexpected type."""


def _app_config() -> AppConfigItems:
  """Return typed app config values for the current request context."""
  return cast("AppConfigItems", current_app.config)


def _app_owe() -> Owe:
  """Return the Owe service bound to the current Flask app instance."""
  owe_service = current_app.extensions.get(OWE_SERVICE_EXTENSION_KEY)
  if not isinstance(owe_service, Owe):
    raise AppServiceTypeError
  return owe_service


def _app_telegram_announcer() -> TelegramAnnouncer | None:
  """Return app-level Telegram announcer, or ``None`` when disabled."""
  announcer = current_app.extensions.get(TELEGRAM_ANNOUNCER_EXTENSION_KEY)
  if announcer is None:
    return None
  if not isinstance(announcer, TelegramAnnouncer):
    raise AppServiceTypeError
  return announcer


def _get_requester() -> str:
  """Return requester identity from configured header or remote address."""
  request_email_header = _app_config()["REQUEST_EMAIL_HEADER"]
  if request_email_header:
    email = request.headers.get(request_email_header)
    if email:
      return email

  trust_proxy = _app_config()["TRUST_PROXY"]
  if trust_proxy:
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for and (ip := x_forwarded_for.split(",")[0].strip()):
      return ip

  return request.remote_addr or "unknown"


def init(app: Flask) -> None:
  """Initialize logging, schema, and app-level services."""
  config = cast("AppConfigItems", app.config)

  logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=getattr(logging, config["LOG_LEVEL"], logging.INFO),
  )

  database = SqliteDatabase(config["DATABASE"], create=True)
  database.init()
  owe_service = Owe(database, logger=logger)
  app.extensions[OWE_SERVICE_EXTENSION_KEY] = owe_service

  bot_token = config["TELEGRAM_BOT_TOKEN"]
  chat_id = config["TELEGRAM_CHAT_ID"]
  if bot_token and chat_id:
    app.extensions[TELEGRAM_ANNOUNCER_EXTENSION_KEY] = TelegramAnnouncer(
      bot_token=bot_token,
      chat_id=chat_id,
      currency=config["CURRENCY"],
    )
  else:
    app.extensions[TELEGRAM_ANNOUNCER_EXTENSION_KEY] = None


api = Blueprint("api", __name__)


@api.route("/config")
def get_config() -> dict[str, Any]:
  """Return client-facing configuration values."""
  return {"currency": _app_config()["CURRENCY"]}


@api.route("/users")
def get_users() -> list[dict[str, Any]]:
  """Return active users."""
  users = _app_owe().get_users(active_only=True)
  return [user.to_dict() for user in users]


@api.route("/records")
def get_records() -> list[dict[str, Any]]:
  """Return all records."""
  records = _app_owe().get_records()
  return [record.to_dict() for record in records]


def _validate_add_records_request(
  req: AddRecordsRequest,
  valid_emails: set[str],
) -> str | None:
  """Validate add-record user references after model validation."""
  lender = req.lender
  borrowers = req.borrowers

  if lender not in valid_emails:
    return f"Unknown lender: {escape(lender)}"

  if unknown_borrowers := set(borrowers) - valid_emails:
    borrowers_str = escape(
      ", ".join(email for email in unknown_borrowers),
    )
    return f"Unknown borrower(s): {borrowers_str}"

  return None


@api.route("/records", methods=["POST"])
def add_records() -> tuple[dict[str, Any], HTTPStatus]:
  """Create an aggregated record and persist its split entries."""
  req_json = request.get_json(silent=True)
  if req_json is None:
    return {
      "success": False,
      "error": "Request body must be JSON",
    }, HTTPStatus.BAD_REQUEST

  req, error = parse(req_json, AddRecordsRequest)
  if req is None:
    return {"success": False, "error": error}, HTTPStatus.BAD_REQUEST

  owe_service = _app_owe()
  users = owe_service.get_users(active_only=True)
  valid_emails = {user.email for user in users}
  error = _validate_add_records_request(req, valid_emails)
  if error is not None:
    return {"success": False, "error": error}, HTTPStatus.BAD_REQUEST

  record = AggregatedRecord(
    type=RecordType(req.type),
    lender=req.lender,
    borrowers=req.borrowers,
    amount=req.amount,
    created_by=_get_requester(),
    remarks=req.remarks,
  )
  try:
    records = owe_service.add_records(record)
  except sqlite3.Error:
    logger.exception("Database error in add_records")
    return {
      "success": False,
      "error": "Database error",
    }, HTTPStatus.INTERNAL_SERVER_ERROR

  announcer = _app_telegram_announcer()
  if announcer:
    threading.Thread(
      target=announcer.announce_records,
      args=(records, users),
      daemon=False,
    ).start()

  return {"success": True}, HTTPStatus.OK


@api.route("/records/status", methods=["PATCH"])
def set_records_active() -> tuple[dict[str, Any], HTTPStatus]:
  """Update the active flag for a batch of records."""
  owe_service = _app_owe()
  req_json = request.get_json(silent=True)
  if req_json is None:
    return {
      "success": False,
      "error": "Request body must be JSON",
    }, HTTPStatus.BAD_REQUEST

  req, error = parse(req_json, SetRecordsActiveRequest)
  if req is None:
    return {"success": False, "error": error}, HTTPStatus.BAD_REQUEST

  try:
    owe_service.set_records_active(
      req.ids,
      active=req.active,
    )
    announcer = _app_telegram_announcer()
    if announcer:
      records = owe_service.get_records_by_ids(req.ids)
      users = owe_service.get_users()
      requester = _get_requester()
      threading.Thread(
        target=announcer.announce_record_status_change,
        args=(
          records,
          users,
          requester,
        ),
        kwargs={"active": req.active},
        daemon=False,
      ).start()
  except sqlite3.Error:
    logger.exception("Database error in set_records_active")
    return {
      "success": False,
      "error": "Database error",
    }, HTTPStatus.INTERNAL_SERVER_ERROR

  return {"success": True}, HTTPStatus.OK


@api.route("/summary")
def summary() -> list[dict[str, Any]]:
  """Return settlement transactions computed from net balances."""
  summary = _app_owe().get_summary()
  return [transaction.to_dict() for transaction in summary]
