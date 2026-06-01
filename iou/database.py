import sqlite3
from textwrap import dedent
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from pathlib import Path

from iou.record import Record
from iou.user import User


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


def init(database: Path) -> None:
  with sqlite3.connect(database) as con:
    con.cursor().execute(
      dedent("""
        CREATE TABLE IF NOT EXISTS Users(
          email  TEXT PRIMARY KEY,
          name   TEXT UNIQUE NOT NULL,
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
          CHECK(type IN ('DEBT', 'PAYMENT')),
          FOREIGN KEY(lender) REFERENCES Users(email),
          FOREIGN KEY(borrower) REFERENCES Users(email),
          CHECK(lender != borrower),
          CHECK(amount > 0)
        );
      """)
    )


def get_users(database: Path, *, active_only: bool = False) -> list[User]:
  with sqlite3.connect(database) as con:
    con.row_factory = dict_factory
    cur = con.cursor()
    query = "SELECT * FROM Users"
    if active_only:
      query += " WHERE active = TRUE"
    query += " ORDER BY name;"
    rows = cur.execute(query).fetchall()
    return [User.from_db_row(row) for row in rows]


def get_records(database: Path, *, active_only: bool = False) -> list[Record]:
  with sqlite3.connect(database) as con:
    con.row_factory = dict_factory
    cur = con.cursor()
    query = "SELECT * FROM Records"
    if active_only:
      query += " WHERE active = TRUE"
    query += " ORDER BY id;"
    rows = cur.execute(query).fetchall()
    return [Record.from_db_row(row) for row in rows]


def add_records(database: Path, records: list[Record]) -> None:
  with sqlite3.connect(database) as con:
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


def set_records_active(
  database: Path,
  ids: list[int],
  *,
  active: bool,
) -> None:
  with sqlite3.connect(database) as con:
    cur = con.cursor()
    cur.executemany(
      "UPDATE Records SET active = ? WHERE id = ?;",
      [(active, record_id) for record_id in ids],
    )
