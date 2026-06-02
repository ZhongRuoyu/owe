import datetime as dt
import logging
import sqlite3
import threading
from html import escape
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, request

import iou.database as db
from iou.config import (
  CURRENCY,
  DATABASE,
  LOG_LEVEL,
  REQUEST_EMAIL_HEADER,
  TELEGRAM_BOT_TOKEN,
  TELEGRAM_CHAT_ID,
)
from iou.record import Record
from iou.telegram import announce_record_status_change, announce_records

API_PREFIX = "/api"
STATIC_DIR = Path(__file__).resolve().parent / "static"

logger = logging.getLogger(__name__)


def init() -> None:
  logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO),
  )
  db.init(DATABASE)


def ceildiv(a: int, b: int) -> int:
  return -(a // -b)


def get_requester() -> str:
  if REQUEST_EMAIL_HEADER:
    email = request.headers.get(REQUEST_EMAIL_HEADER)
    if email:
      return email
  return request.remote_addr or "unknown"


blueprint = Blueprint(
  "iou",
  __name__,
  url_prefix="",
  static_folder=STATIC_DIR,
  static_url_path="",
)


@blueprint.after_request
def add_csp(response: Response) -> Response:
  response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "script-src 'self' https://cdnjs.cloudflare.com; "
    "style-src 'self' https://cdnjs.cloudflare.com; "
    "img-src 'self' data:; "
  )
  return response


@blueprint.route("/")
def index() -> Response:
  return blueprint.send_static_file("index.html")


api = Blueprint("api", __name__, url_prefix=API_PREFIX)
blueprint.register_blueprint(api)


@api.route("/config")
def get_config() -> dict[str, Any]:
  return {"currency": CURRENCY}


@api.route("/users")
def get_users() -> list[dict[str, Any]]:
  users = db.get_users(DATABASE, active_only=True)
  return [user.asdict() for user in users]


@api.route("/records")
def get_records() -> dict[str, dict[str, Any]]:
  records = db.get_records(DATABASE)
  return {str(record.id): record.asdict() for record in records}


def validate_add_records_request(  # noqa: PLR0911
  req: dict[str, Any],
  valid_emails: set[str],
) -> tuple[bool, str]:
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
  req = request.get_json()
  if not req:
    return {"success": False, "error": "Request body must be JSON"}, 400

  users = db.get_users(DATABASE, active_only=True)
  valid_emails = {u.email for u in users}
  valid, error = validate_add_records_request(req, valid_emails)
  if not valid:
    return {"success": False, "error": error}, 400

  req_type = req["type"]
  lender = req["lender"]
  borrowers = req["borrowers"]
  each_amount = ceildiv(req["amount"], len(borrowers))
  created_by = get_requester()
  created_at = dt.datetime.now(tz=dt.timezone.utc)
  remarks = req["remarks"]
  records = [
    Record(
      type=req_type,
      lender=lender,
      borrower=borrower,
      amount=each_amount,
      created_by=created_by,
      created_at=created_at,
      remarks=remarks,
    )
    for borrower in borrowers
    if borrower != lender
  ]

  try:
    db.add_records(DATABASE, records)
  except sqlite3.Error:
    logger.exception("Database error in add_records")
    return {"success": False, "error": "Database error"}, 500
  logger.info(
    "Added %d record(s) of type %s by %s",
    len(records),
    req_type,
    created_by,
  )

  if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    threading.Thread(
      target=announce_records,
      args=(records, CURRENCY, users, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID),
      daemon=False,
    ).start()

  return {"success": True}, 200


@api.route("/records/status", methods=["PATCH"])
def set_records_active() -> tuple[dict[str, Any], int]:
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
    db.set_records_active(DATABASE, ids, active=active)
  except sqlite3.Error:
    logger.exception("Database error in set_records_active")
    return {"success": False, "error": "Database error"}, 500
  action = "activated" if active else "canceled"
  requester = get_requester()
  logger.info("%d records %s by %s", len(ids), action, requester)

  if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    records = [r for r in db.get_records(DATABASE) if r.id in set(ids)]
    users = db.get_users(DATABASE)
    threading.Thread(
      target=announce_record_status_change,
      args=(
        records,
        CURRENCY,
        users,
        requester,
        TELEGRAM_BOT_TOKEN,
        TELEGRAM_CHAT_ID,
      ),
      kwargs={
        "active": active,
      },
      daemon=False,
    ).start()

  return {"success": True}, 200


@api.route("/summary")
def summary() -> list[dict[str, Any]]:
  net_balances = db.get_net_balances(DATABASE)
  creditors = [
    (user, balance) for user, balance in net_balances.items() if balance > 0
  ]
  debtors = [
    (user, -balance) for user, balance in net_balances.items() if balance < 0
  ]
  creditors.sort(key=lambda x: x[1], reverse=True)
  debtors.sort(key=lambda x: x[1], reverse=True)

  transactions = []
  creditor_idx = 0
  debtor_idx = 0
  while creditor_idx < len(creditors) and debtor_idx < len(debtors):
    creditor_user, credit_amount = creditors[creditor_idx]
    debtor_user, debt_amount = debtors[debtor_idx]

    transfer_amount = min(credit_amount, debt_amount)
    if transfer_amount > 0:
      transactions.append(
        {"from": debtor_user, "to": creditor_user, "amount": transfer_amount}
      )
    creditors[creditor_idx] = (creditor_user, credit_amount - transfer_amount)
    debtors[debtor_idx] = (debtor_user, debt_amount - transfer_amount)

    if creditors[creditor_idx][1] == 0:
      creditor_idx += 1
    if debtors[debtor_idx][1] == 0:
      debtor_idx += 1

  return transactions
