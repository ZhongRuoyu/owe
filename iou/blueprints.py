import datetime as dt
import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, render_template, request

import iou.database as db
from iou.config import CURRENCY, DATABASE, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
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


blueprint = Blueprint(
  "iou",
  __name__,
  url_prefix="",
  static_folder=str(STATIC_DIR),
  template_folder=str(TEMPLATES_DIR),
)


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


@api.route("/records", methods=["POST"])
def add_records() -> tuple[dict[str, Any], int]:
  req = request.get_json()
  for key in ["type", "lender", "borrowers", "amount", "remarks"]:
    if key not in req:
      return {"success": False, "error": f"Missing field: {key}"}, 400
  if req["type"] not in {"DEBT", "PAYMENT"}:
    return {"success": False, "error": f"Invalid type: {req['type']}"}, 400

  req_type = req["type"]
  lender = req["lender"]
  borrowers = req["borrowers"]
  created_by = (
    request.headers.get("cf-access-authenticated-user-email")
    or request.remote_addr
    or "unknown"
  )
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

  db.add_records(DATABASE, records)
  logger.info(
    "Added %d record(s) of type %s by %s",
    len(records),
    req_type,
    created_by,
  )

  if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    announce_records(records, CURRENCY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

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
