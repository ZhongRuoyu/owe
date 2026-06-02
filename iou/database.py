import sqlite3
from pathlib import Path
from textwrap import dedent
from typing import Any

from iou.record import Record
from iou.user import User


def dict_factory(
  cursor: sqlite3.Cursor,
  row: tuple[Any, ...],
) -> dict[str, Any]:
  """Convert a SQLite row tuple into a dict keyed by column name."""
  return dict(
    zip(
      [column[0] for column in cursor.description],
      row,
      strict=True,
    )
  )


def init(database: Path) -> None:
  """Create database tables and views if they do not already exist."""
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
    ).execute(
      dedent("""
        CREATE VIEW IF NOT EXISTS UserBalances AS
        WITH Deltas AS (
          SELECT
            lender AS user,
            amount AS delta
          FROM Records
          WHERE active = TRUE

          UNION ALL

          SELECT
            borrower AS user,
            -amount AS delta
          FROM Records
          WHERE active = TRUE
        )
        SELECT
          user,
          SUM(delta) AS balance
        FROM Deltas
        GROUP BY user;
      """)
    )


def get_users(database: Path, *, active_only: bool = False) -> list[User]:
  """Fetch users from the database ordered by display name."""
  with sqlite3.connect(database) as con:
    con.row_factory = dict_factory
    cur = con.cursor()
    query = "SELECT * FROM Users"
    if active_only:
      query += " WHERE active = TRUE"
    query += " ORDER BY name;"
    rows = cur.execute(query).fetchall()
  return [User.from_db_row(row) for row in rows]


def add_user(database: Path, user: User) -> None:
  """Insert a user row into the database."""
  with sqlite3.connect(database) as con:
    cur = con.cursor()
    cur.execute(
      "INSERT INTO Users(email, name, active) VALUES(?, ?, ?);",
      user.to_insert_values(),
    )


def set_user_active(database: Path, email: str, *, active: bool) -> int:
  """Set a user's active flag and return the number of updated rows."""
  with sqlite3.connect(database) as con:
    cur = con.cursor()
    cur.execute(
      "UPDATE Users SET active = ? WHERE email = ?;",
      (active, email),
    )
    return cur.rowcount


def get_records(database: Path, *, active_only: bool = False) -> list[Record]:
  """Fetch records from the database ordered by ID."""
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
  """Insert records and populate generated IDs on each record object."""
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
) -> int:
  """Set the active flag for record IDs and return affected row count."""
  with sqlite3.connect(database) as con:
    cur = con.cursor()
    cur.executemany(
      "UPDATE Records SET active = ? WHERE id = ?;",
      [(active, record_id) for record_id in ids],
    )
    return cur.rowcount


def get_net_balances(database: Path) -> dict[str, int]:
  """Return per-user net balances computed from active records."""
  with sqlite3.connect(database) as con:
    cur = con.cursor()
    cur.row_factory = dict_factory
    rows = cur.execute("SELECT * FROM UserBalances;").fetchall()
  return {row["user"]: row["balance"] for row in rows}
