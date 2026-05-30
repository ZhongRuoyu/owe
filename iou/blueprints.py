import csv
import datetime as dt
import subprocess
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, render_template, request

import iou.database as db
from iou.config import BILLING_REPO, CURRENCY, DATABASE, GIT
from iou.record import Record

API_PREFIX = "/api"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def init() -> None:
  db.init(DATABASE)


def ceildiv(a: int, b: int) -> int:
  return -(a // -b)


def git(args: list[str], *, cwd: Path) -> None:
  # `args` are fixed command segments from this module and are not shell input.
  subprocess.run([GIT, *args], cwd=cwd, check=True)  # noqa: S603


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
def main_js() -> str:
  return render_template("main.js", currency=CURRENCY)


api = Blueprint("api", __name__, url_prefix=API_PREFIX)
blueprint.register_blueprint(api)


@api.route("/users")
def get_users() -> list[dict[str, Any]]:
  users = db.get_users(DATABASE)
  return [user.asdict() for user in users]


@api.route("/records")
def get_records() -> dict[str, dict[str, Any]]:
  records = db.get_records(DATABASE)
  return {str(record.id): record.asdict() for record in records}


@api.route("/records", methods=["POST"])
def add_records() -> tuple[dict[str, Any], int]:
  req = request.get_json()
  for key in ["type", "lender", "borrowers", "amount", "created_by", "remarks"]:
    if key not in req:
      return {"success": False, "error": f"Missing field: {key}"}, 400

  lender = req["lender"]
  borrowers = req["borrowers"]
  records = [
    Record(
      type=req["type"],
      lender=lender,
      borrower=borrower,
      amount=ceildiv(req["amount"], len(borrowers)),
      created_by=req["created_by"],
      created_at=dt.datetime.now(tz=dt.UTC),
      remarks=req["remarks"],
    )
    for borrower in borrowers
    if borrower != lender
  ]

  db.add_records(DATABASE, records)

  if BILLING_REPO:
    git(["fetch", "origin", "main"], cwd=BILLING_REPO)
    git(["checkout", "-B", "main", "origin/main"], cwd=BILLING_REPO)

    records_csv = BILLING_REPO / "records.csv"

    existing_records: list[Record] = []
    if records_csv.exists():
      with records_csv.open(encoding="utf-8", newline="") as csv_file:
        reader = csv.reader(csv_file)
        next(reader, None)  # Skip header
        existing_records = [Record.from_csv_row(row) for row in reader]

    for record in records:
      existing_records.append(record)
      existing_records.sort(key=lambda r: r.id)
      with records_csv.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(Record.csv_header())
        for existing_record in existing_records:
          writer.writerow(existing_record.to_csv_row())

      git(["add", str(records_csv)], cwd=BILLING_REPO)
      git(["commit", "-m", record.commit_message(CURRENCY)], cwd=BILLING_REPO)

    git(["push", "origin"], cwd=BILLING_REPO)

  return {"success": True}, 200


@api.route("/summary")
def summary() -> list[dict[str, Any]]:
  users = db.get_users(DATABASE)
  records = db.get_records(DATABASE, active_only=True)

  net_balance = {user.name: 0 for user in users}
  for record in records:
    net_balance[record.lender] += record.amount
    net_balance[record.borrower] -= record.amount
  creditors = [
    (name, balance) for name, balance in net_balance.items() if balance > 0
  ]
  debtors = [
    (name, -balance) for name, balance in net_balance.items() if balance < 0
  ]
  creditors.sort(key=lambda x: x[1], reverse=True)
  debtors.sort(key=lambda x: x[1], reverse=True)

  transactions = []
  creditor_idx = 0
  debtor_idx = 0
  while creditor_idx < len(creditors) and debtor_idx < len(debtors):
    creditor_name, credit_amount = creditors[creditor_idx]
    debtor_name, debt_amount = debtors[debtor_idx]

    transfer_amount = min(credit_amount, debt_amount)
    if transfer_amount > 0:
      transactions.append(
        {"from": debtor_name, "to": creditor_name, "amount": transfer_amount}
      )
    creditors[creditor_idx] = (creditor_name, credit_amount - transfer_amount)
    debtors[debtor_idx] = (debtor_name, debt_amount - transfer_amount)

    if creditors[creditor_idx][1] == 0:
      creditor_idx += 1
    if debtors[debtor_idx][1] == 0:
      debtor_idx += 1

  return transactions
