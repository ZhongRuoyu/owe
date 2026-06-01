import datetime as dt
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, render_template, request

import iou.database as db
from iou.config import (
  CURRENCY,
  DATABASE,
  REQUEST_EMAIL_HEADER,
  TELEGRAM_BOT_TOKEN,
  TELEGRAM_CHAT_ID,
)
from iou.record import Record
from iou.telegram import announce_records

API_PREFIX = "/api"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

logger = logging.getLogger(__name__)


def init() -> None:
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
  static_folder=str(STATIC_DIR),
  template_folder=str(TEMPLATES_DIR),
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


@blueprint.route("/main.js")
def main_js() -> Response:
  return Response(
    render_template("main.js", currency=CURRENCY),
    mimetype="text/javascript",
  )


api = Blueprint("api", __name__, url_prefix=API_PREFIX)
blueprint.register_blueprint(api)


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
  if req["type"] not in {"DEBT", "PAYMENT"}:
    return False, f"Invalid type: {req['type']}"
  if not isinstance(req["amount"], (int, float)) or req["amount"] <= 0:
    return False, "amount must be a positive number"
  if not isinstance(req["borrowers"], list) or not req["borrowers"]:
    return False, "borrowers must be a non-empty list"
  if req["lender"] not in valid_emails:
    return False, "Unknown lender"
  unknown_borrowers = set(req["borrowers"]) - valid_emails
  if unknown_borrowers:
    return False, f"Unknown borrower(s): {unknown_borrowers}"

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
  created_by = get_requester()
  created_at = dt.datetime.now(tz=dt.UTC)
  records = [
    Record(
      type=req_type,
      lender=lender,
      borrower=borrower,
      amount=ceildiv(req["amount"], len(borrowers)),
      created_by=created_by,
      created_at=created_at,
      remarks=req["remarks"],
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


@api.route("/summary")
def summary() -> list[dict[str, Any]]:
  users = db.get_users(DATABASE)
  records = db.get_records(DATABASE, active_only=True)

  net_balance = {user.email: 0 for user in users}
  for record in records:
    net_balance[record.lender] += record.amount
    net_balance[record.borrower] -= record.amount
  creditors = [
    (email, balance) for email, balance in net_balance.items() if balance > 0
  ]
  debtors = [
    (email, -balance) for email, balance in net_balance.items() if balance < 0
  ]
  creditors.sort(key=lambda x: x[1], reverse=True)
  debtors.sort(key=lambda x: x[1], reverse=True)

  transactions = []
  creditor_idx = 0
  debtor_idx = 0
  while creditor_idx < len(creditors) and debtor_idx < len(debtors):
    creditor_email, credit_amount = creditors[creditor_idx]
    debtor_email, debt_amount = debtors[debtor_idx]

    transfer_amount = min(credit_amount, debt_amount)
    if transfer_amount > 0:
      transactions.append(
        {"from": debtor_email, "to": creditor_email, "amount": transfer_amount}
      )
    creditors[creditor_idx] = (creditor_email, credit_amount - transfer_amount)
    debtors[debtor_idx] = (debtor_email, debt_amount - transfer_amount)

    if creditors[creditor_idx][1] == 0:
      creditor_idx += 1
    if debtors[debtor_idx][1] == 0:
      debtor_idx += 1

  return transactions
