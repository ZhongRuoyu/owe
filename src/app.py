"""Flask app for IOU API."""

import csv
import os
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Any
from zoneinfo import ZoneInfo

from flask import Flask, Response, request
from flask_cors import CORS


@dataclass(slots=True)
class Record:
  """A record of an IOU transaction."""

  type: str
  lender: str
  borrower: str
  amount: int
  created_by: str
  created_at: datetime
  remarks: str | None = None
  active: bool = True
  id: int | None = None

  def to_insert_values(
    self,
  ) -> tuple[str, str, str, int, str, int, str | None, bool]:
    return (
      self.type,
      self.lender,
      self.borrower,
      self.amount,
      self.created_by,
      int(self.created_at.timestamp() * 1000),
      self.remarks,
      self.active,
    )

  @staticmethod
  def csv_header() -> tuple[str, str, str, str, str, str, str, str, str]:
    return (
      "id",
      "type",
      "lender",
      "borrower",
      "amount",
      "created_by",
      "created_at",
      "remarks",
      "active",
    )

  @staticmethod
  def from_csv_row(row: list[str]) -> Record:
    (
      record_id,
      record_type,
      lender,
      borrower,
      amount,
      created_by,
      created_at,
      remarks,
      active,
    ) = row
    return Record(
      id=int(record_id),
      type=record_type,
      lender=lender,
      borrower=borrower,
      amount=int(float(amount) * 100),
      created_by=created_by,
      created_at=datetime.fromisoformat(created_at),
      remarks=remarks,
      active=bool(int(active)),
    )

  def to_csv_row(self) -> tuple[int, str, str, str, str, str, str, str, int]:
    return (
      self.id or 0,
      self.type,
      self.lender,
      self.borrower,
      f"{self.amount / 100:.2f}",
      self.created_by,
      self.created_at.isoformat(timespec="milliseconds"),
      self.remarks or "",
      int(self.active),
    )

  def __repr__(self) -> str:
    fields = [
      f"id={self.id}",
      f"type={self.type}",
      f"lender={self.lender}",
      f"borrower={self.borrower}",
      f"amount={self.amount}",
      f"created_by={self.created_by}",
      f"created_at={self.created_at.isoformat(timespec='milliseconds')}",
      f"remarks={self.remarks}",
      f"active={int(self.active)}",
    ]
    fields_str = ", ".join(fields)
    return f"Record({fields_str})"

  def commit_message(self) -> str:
    amount = self.amount / 100
    message = f"{self.lender} -> {self.borrower}: ${amount:.2f}"
    if self.remarks:
      message += f" ({self.remarks})"
    return message


DATABASE = os.getenv("DATABASE", "iou.db")
BILLING_REPO = os.getenv("BILLING_REPO", None)
GIT = os.getenv("GIT", "git")
API_PREFIX = "/api"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def init() -> None:
  with sqlite3.connect(DATABASE) as con:
    con.cursor().execute(
      dedent("""
        CREATE TABLE IF NOT EXISTS Users(
          name   TEXT PRIMARY KEY,
          active BOOLEAN DEFAULT TRUE
        );
      """)
    ).execute(
      dedent("""
        CREATE TABLE IF NOT EXISTS Records(
          id         INTEGER PRIMARY KEY AUTOINCREMENT,
          type       TEXT NOT NULL,
          lender     TEXT NOT NULL,
          borrower   TEXT NOT NULL,
          amount     INTEGER NOT NULL,
          created_by TEXT NOT NULL,
          created_at INTEGER NOT NULL,
          remarks    TEXT,
          active     BOOLEAN DEFAULT TRUE,
          FOREIGN KEY(lender) REFERENCES Users(name),
          FOREIGN KEY(borrower) REFERENCES Users(name),
          FOREIGN KEY(created_by) REFERENCES Users(name),
          CHECK(lender != borrower),
          CHECK(amount > 0)
        );
      """)
    )


init()
app = Flask(
  __name__,
  static_folder=str(STATIC_DIR),
  static_url_path="",
)
CORS(app)


def dict_factory(
  cursor: sqlite3.Cursor,
  row: tuple[Any, ...],
) -> dict[str, Any]:
  return dict(
    zip(
      [column[0] for column in cursor.description],
      row,
      strict=True,
    )
  )


def ceildiv(a: int, b: int) -> int:
  return -(a // -b)


def git(args: list[str], *, cwd: Path) -> None:
  # `args` are fixed command segments from this module and are not shell input.
  subprocess.run([GIT, *args], cwd=str(cwd), check=True)  # noqa: S603


@app.route("/")
def index() -> Response:
  return app.send_static_file("index.html")


@app.route(f"{API_PREFIX}/users")
def get_users() -> list[dict[str, Any]]:
  with sqlite3.connect(DATABASE) as con:
    con.row_factory = dict_factory
    return con.cursor().execute("SELECT * FROM Users;").fetchall()


@app.route(f"{API_PREFIX}/records")
def get_records() -> dict[str, dict[str, Any]]:
  with sqlite3.connect(DATABASE) as con:
    con.row_factory = dict_factory
    records = con.cursor().execute("SELECT * FROM Records;").fetchall()
    return {str(record["id"]): record for record in records}


@app.route(f"{API_PREFIX}/summary")
def summary() -> list[dict[str, Any]]:
  with sqlite3.connect(DATABASE) as con:
    con.row_factory = dict_factory

    users = con.cursor().execute("SELECT * FROM Users;").fetchall()
    net_balance = {user["name"]: 0 for user in users}

    records = (
      con.cursor()
      .execute(
        dedent("""
          SELECT * FROM Records
          WHERE active = TRUE;
        """)
      )
      .fetchall()
    )

    for record in records:
      net_balance[record["lender"]] += record["amount"]
      net_balance[record["borrower"]] -= record["amount"]
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


@app.route(f"{API_PREFIX}/record", methods=["POST"])
def new_record() -> tuple[dict[str, Any], int] | dict[str, Any]:
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
      created_at=datetime.now(tz=ZoneInfo("Asia/Singapore")),
      remarks=req["remarks"],
    )
    for borrower in borrowers
    if borrower != lender
  ]

  with sqlite3.connect(DATABASE) as con:
    con.row_factory = dict_factory
    cur = con.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")
    for record in records:
      cur.execute(
        dedent("""
          INSERT INTO Records(
            type,
            lender,
            borrower,
            amount,
            created_by,
            created_at,
            remarks,
            active
          )
          VALUES(?, ?, ?, ?, ?, ?, ?, ?);
        """),
        record.to_insert_values(),
      )
      record.id = cur.lastrowid
    con.commit()

  if BILLING_REPO is not None:
    billing_repo = Path(BILLING_REPO)
    git(["fetch", "origin", "main"], cwd=billing_repo)
    git(["checkout", "-B", "main", "origin/main"], cwd=billing_repo)

    records_csv = billing_repo / "records.csv"

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

      git(["add", str(records_csv)], cwd=billing_repo)
      git(["commit", "-m", record.commit_message()], cwd=billing_repo)

    git(["push", "origin"], cwd=billing_repo)

  return {"success": True}
