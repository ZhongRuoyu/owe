import sqlite3
from pathlib import Path
from textwrap import dedent
from typing import Any
from urllib.request import pathname2url

from .record import Record
from .user import User

SQLITE_DEFAULT_CONNECT_TIMEOUT = 5
SQLITE_DEFAULT_BUSY_TIMEOUT_MS = 5000


class Database:
  """An SQLite database for managing users and records."""

  _uri: str
  _connect_timeout: float
  _busy_timeout_ms: int

  def __init__(
    self,
    path: Path,
    *,
    create: bool,
    connect_timeout: float = SQLITE_DEFAULT_CONNECT_TIMEOUT,
    busy_timeout_ms: int = SQLITE_DEFAULT_BUSY_TIMEOUT_MS,
  ) -> None:
    """Initialize the SQLite database with a database file path."""
    file = pathname2url(str(path))
    mode = "rwc" if create else "rw"
    self._uri = f"file:{file}?mode={mode}"
    self._connect_timeout = connect_timeout
    self._busy_timeout_ms = busy_timeout_ms

  def init(self) -> None:
    """Create database tables and views if they do not already exist."""
    with self._connect() as conn:
      conn.cursor().execute(
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

  def get_users(self, *, active_only: bool = False) -> list[User]:
    """Fetch users from the database ordered by display name."""
    with self._connect() as conn:
      cur = conn.cursor()
      query = "SELECT * FROM Users"
      if active_only:
        query += " WHERE active = TRUE"
      query += " ORDER BY name;"
      rows = cur.execute(query).fetchall()
    return [User.from_database_row(row) for row in rows]

  def add_user(self, user: User) -> None:
    """Insert a user row into the database."""
    with self._connect() as conn:
      cur = conn.cursor()
      cur.execute(
        "INSERT INTO Users(email, name, active) VALUES(?, ?, ?);",
        user.to_insert_values(),
      )

  def set_user_active(self, email: str, *, active: bool) -> int:
    """Set a user's active flag and return the number of updated rows."""
    with self._connect() as conn:
      cur = conn.cursor()
      cur.execute(
        "UPDATE Users SET active = ? WHERE email = ?;",
        (active, email),
      )
      return cur.rowcount

  def get_records(self, *, active_only: bool = False) -> list[Record]:
    """Fetch records from the database ordered by ID."""
    with self._connect() as conn:
      cur = conn.cursor()
      query = "SELECT * FROM Records"
      if active_only:
        query += " WHERE active = TRUE"
      query += " ORDER BY id;"
      rows = cur.execute(query).fetchall()
    return [Record.from_database_row(row) for row in rows]

  def add_records(self, records: list[Record]) -> None:
    """Insert records and populate generated IDs on each record object."""
    with self._connect() as conn:
      cur = conn.cursor()
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

  def set_records_active(self, ids: list[int], *, active: bool) -> int:
    """Set the active flag for record IDs and return affected row count."""
    with self._connect() as conn:
      cur = conn.cursor()
      cur.executemany(
        "UPDATE Records SET active = ? WHERE id = ?;",
        [(active, record_id) for record_id in ids],
      )
      return cur.rowcount

  def get_net_balances(self) -> dict[str, int]:
    """Return per-user net balances computed from active records."""
    with self._connect() as conn:
      cur = conn.cursor()
      rows = cur.execute("SELECT * FROM UserBalances;").fetchall()
    return {row["user"]: row["balance"] for row in rows}

  def _connect(self) -> sqlite3.Connection:
    """Create an SQLite connection configured for integrity and contention."""
    conn = sqlite3.connect(self._uri, uri=True, timeout=self._connect_timeout)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms};")
    conn.row_factory = self._dict_factory
    return conn

  @staticmethod
  def _dict_factory(
    cursor: sqlite3.Cursor,
    row: tuple[Any, ...],
  ) -> dict[str, Any]:
    """Convert an SQLite row tuple into a dict keyed by column name."""
    return dict(
      zip(
        [column[0] for column in cursor.description],
        row,
        strict=True,
      )
    )
