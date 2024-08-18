"""Flask app for IOU API."""

import csv
from datetime import datetime
from itertools import combinations, permutations
import os
import subprocess
from textwrap import dedent
from typing import Any, Optional
from zoneinfo import ZoneInfo

from flask import Flask, request
from flask_cors import CORS
import sqlite3

from dotenv import load_dotenv


class Record:
  """A record of an IOU transaction."""

  id: Optional[int]
  type: str
  lender: str
  borrower: str
  amount: int
  created_by: str
  created_at: datetime
  remarks: Optional[str]
  active: bool

  def __init__(
      self,
      *,
      # pylint: disable-next=redefined-builtin
      id: Optional[int] = None,
      # pylint: disable-next=redefined-builtin
      type: str,
      lender: str,
      borrower: str,
      amount: int,
      created_by: str,
      created_at: datetime,
      remarks: Optional[str] = None,
      active: Optional[bool] = True,
  ) -> None:
    self.id = id
    self.type = type
    self.lender = lender
    self.borrower = borrower
    self.amount = amount
    self.created_by = created_by
    self.created_at = created_at
    self.remarks = remarks
    self.active = bool(active)

  @staticmethod
  def from_csv_row(row: list[str]) -> "Record":
    return Record(
        id=int(row[0]),
        type=row[1],
        lender=row[2],
        borrower=row[3],
        amount=int(float(row[4]) * 100),
        created_by=row[5],
        created_at=datetime.fromisoformat(row[6]),
        remarks=row[7],
        active=bool(row[8]),
    )

  def insert_values(self):
    return (
        self.type,
        self.lender,
        self.borrower,
        self.amount,
        self.created_by,
        int(self.created_at.timestamp() * 1000),
        self.remarks,
    )

  def csv_row(self) -> str:
    return (
        self.id,
        self.type,
        self.lender,
        self.borrower,
        f"{self.amount/100:.2f}",
        self.created_by,
        self.created_at.isoformat(),
        self.remarks,
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
        f"created_at={self.created_at.isoformat()}",
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


load_dotenv()

DATABASE = os.getenv("DATABASE", "iou.db")
BILLING_REPO = os.getenv("BILLING_REPO", None)


def init():
  with sqlite3.connect(DATABASE) as con:
    con.cursor().execute(
        dedent("""
          CREATE TABLE IF NOT EXISTS Users(
            name TEXT PRIMARY KEY
          );
        """)).execute(
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
            """))


init()
app = Flask(__name__)
CORS(app)


def dict_factory(cursor: sqlite3.Cursor, row: list[Any]) -> dict[str, Any]:
  return dict(zip(list(column[0] for column in cursor.description), row))


def ceildiv(a: int, b: int) -> int:
  return -(a // -b)


@app.route("/users")
def get_users() -> list[dict[str, str | int]]:
  with sqlite3.connect(DATABASE) as con:
    con.row_factory = dict_factory
    return con.cursor().execute("SELECT * FROM Users;").fetchall()


@app.route("/records")
def get_records() -> list[dict[str, str | int]]:
  with sqlite3.connect(DATABASE) as con:
    con.row_factory = dict_factory
    records = con.cursor().execute("SELECT * FROM Records;").fetchall()
    return {record["id"]: record for record in records}


@app.route("/summary")
def summary() -> list[dict[str, str | int]]:
  with sqlite3.connect(DATABASE) as con:
    con.row_factory = dict_factory

    users = con.cursor().execute("SELECT * FROM Users;").fetchall()
    payment = {
        pair: 0
        for pair in permutations(list(user["name"] for user in users), 2)
    }

    records = con.cursor().execute(
        dedent("""
          SELECT * FROM Records
          WHERE active = TRUE;
        """)).fetchall()
    for record in records:
      pair = (record["borrower"], record["lender"])
      payment[pair] += record["amount"]

    for pair in combinations(list(user["name"] for user in users), 2):
      reverse_pair = (pair[1], pair[0])
      if payment[pair] < payment[reverse_pair]:
        pair, reverse_pair = reverse_pair, pair
      payment[pair] -= payment[reverse_pair]
      payment.pop(reverse_pair)
      if payment[pair] == 0:
        payment.pop(pair)

    return [{
        "from": pair[0],
        "to": pair[1],
        "amount": amount
    } for pair, amount in payment.items()]


@app.route("/record", methods=["POST"])
def new_record() -> (tuple[dict[str, str | bool], int] | dict[str, str | bool]):
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
      ) for borrower in borrowers if borrower != lender
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
              remarks)
            VALUES(?, ?, ?, ?, ?, ?, ?);
          """), record.insert_values())
      record.id = cur.lastrowid
    con.commit()

  if BILLING_REPO is not None:
    subprocess.run(["git", "fetch", "origin", "main"],
                   cwd=BILLING_REPO,
                   check=True)
    subprocess.run(["git", "reset", "--hard", "origin/main"],
                   cwd=BILLING_REPO,
                   check=True)

    records_csv = f"{BILLING_REPO}/records.csv"

    existing_records = []
    if os.path.exists(records_csv):
      with open(records_csv, "r", encoding="utf-8", newline="") as csv_file:
        reader = csv.reader(csv_file)
        next(reader, None)  # Skip header
        existing_records = [Record.from_csv_row(row) for row in reader]

    for record in records:
      existing_records += [record]
      existing_records.sort(key=lambda r: r.id)
      with open(records_csv, "w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([
            "id", "type", "lender", "borrower", "amount", "created_by",
            "created_at", "remarks", "active"
        ])
        for record in existing_records:
          writer.writerow(record.csv_row())

      subprocess.run(["git", "add", records_csv], cwd=BILLING_REPO, check=True)
      subprocess.run(["git", "commit", "-m",
                      record.commit_message()],
                     cwd=BILLING_REPO,
                     check=True)

    subprocess.run(["git", "push", "origin"], cwd=BILLING_REPO, check=True)

  return {"success": True}
