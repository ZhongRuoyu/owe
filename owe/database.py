import sqlite3
from abc import ABC, abstractmethod
from contextlib import closing
from pathlib import Path
from textwrap import dedent
from typing import Any
from urllib.request import pathname2url

from .record import Record, RecordType
from .user import User

SQLITE_DEFAULT_CONNECT_TIMEOUT = 5
SQLITE_DEFAULT_BUSY_TIMEOUT_MS = 5000


class DatabaseError(Exception):
  """Base exception type for Owe database errors."""


class DatabaseConnectionError(DatabaseError):
  """An exception raised when a database connection cannot be established."""


class DatabaseInitializationError(DatabaseError):
  """An exception raised when the database cannot be initialized."""


class DatabaseConfigurationError(DatabaseError):
  """An exception raised when the database cannot be configured."""


class DatabaseIntegrityError(DatabaseError):
  """An exception raised when a database integrity constraint is violated."""


class UserAlreadyExistsError(DatabaseIntegrityError):
  """An exception raised when a user already exists in the database."""


class UserNotFoundError(DatabaseIntegrityError):
  """An exception raised when a user is not found in the database."""


class Database(ABC):
  """Abstract database backend for managing users and records."""

  @abstractmethod
  def init(self) -> None:
    """Create database tables and views if they do not already exist."""

  @abstractmethod
  def get_users(self, *, active_only: bool = False) -> list[User]:
    """Fetch users from the database ordered by display name."""

  @abstractmethod
  def add_user(self, user: User) -> None:
    """Insert a user row into the database."""

  @abstractmethod
  def set_user_active(self, user_id: str, *, active: bool) -> int:
    """Set a user's active flag and return the number of updated rows."""

  @abstractmethod
  def get_records(self, *, active_only: bool = False) -> list[Record]:
    """Fetch records from the database ordered by ID."""

  @abstractmethod
  def add_records(self, records: list[Record]) -> None:
    """Insert records and populate generated IDs on each record object."""

  @abstractmethod
  def set_records_active(self, ids: list[int], *, active: bool) -> int:
    """Set the active flag for record IDs and return affected row count."""

  @abstractmethod
  def get_net_balances(self) -> dict[str, int]:
    """Return per-user net balances computed from active records."""


class SqliteDatabase(Database):
  """An SQLite database backend for managing users and records."""

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
    with closing(self._connect()) as conn, conn:
      try:
        conn.cursor().execute(
          dedent("""
            CREATE TABLE IF NOT EXISTS Users(
              id     TEXT PRIMARY KEY,
              name   TEXT UNIQUE NOT NULL,
              active BOOLEAN DEFAULT TRUE
            );
          """)
        ).execute(
          dedent(f"""
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
              CHECK(type IN ({", ".join(f"'{t.value}'" for t in RecordType)})),
              FOREIGN KEY(lender) REFERENCES Users(id),
              FOREIGN KEY(borrower) REFERENCES Users(id),
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
      except sqlite3.Error as error:
        msg = f"Failed to initialize the database at {self._uri}: {error}"
        raise DatabaseInitializationError(msg) from error

  def get_users(self, *, active_only: bool = False) -> list[User]:
    """Fetch users from the database ordered by display name."""
    with closing(self._connect()) as conn, conn:
      try:
        cur = conn.cursor()
        query = "SELECT * FROM Users"
        if active_only:
          query += " WHERE active = TRUE"
        query += " ORDER BY name;"
        rows = cur.execute(query).fetchall()
      except sqlite3.Error as error:
        msg = f"Failed to fetch users: {error}"
        raise DatabaseError(msg) from error
    return [User.from_database_row(row) for row in rows]

  def add_user(self, user: User) -> None:
    """Insert a user row into the database."""
    with closing(self._connect()) as conn, conn:
      try:
        cur = conn.cursor()
        cur.execute(
          "INSERT INTO Users(id, name, active) VALUES(?, ?, ?);",
          user.to_insert_values(),
        )
      except sqlite3.IntegrityError as error:
        msg = "User with the same ID or name already exists"
        raise UserAlreadyExistsError(msg) from error
      except sqlite3.Error as error:
        msg = f"Failed to add user: {error}"
        raise DatabaseError(msg) from error

  def set_user_active(self, user_id: str, *, active: bool) -> int:
    """Set a user's active flag and return the number of updated rows."""
    with closing(self._connect()) as conn, conn:
      try:
        cur = conn.cursor()
        cur.execute(
          "UPDATE Users SET active = ? WHERE id = ?;",
          (active, user_id),
        )
      except sqlite3.Error as error:
        msg = f"Failed to update user: {error}"
        raise DatabaseError(msg) from error
      if cur.rowcount == 0:
        msg = f"No user found with ID {user_id}"
        raise UserNotFoundError(msg)
      return cur.rowcount

  def get_records(self, *, active_only: bool = False) -> list[Record]:
    """Fetch records from the database ordered by ID."""
    with closing(self._connect()) as conn, conn:
      try:
        cur = conn.cursor()
        query = "SELECT * FROM Records"
        if active_only:
          query += " WHERE active = TRUE"
        query += " ORDER BY id;"
        rows = cur.execute(query).fetchall()
      except sqlite3.Error as error:
        msg = f"Failed to fetch records: {error}"
        raise DatabaseError(msg) from error
    return [Record.from_database_row(row) for row in rows]

  def add_records(self, records: list[Record]) -> None:
    """Insert records and populate generated IDs on each record object."""
    with closing(self._connect()) as conn, conn:
      try:
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
      except sqlite3.IntegrityError as error:
        msg = f"Failed to add records due to constraint violation: {error}"
        raise DatabaseIntegrityError(msg) from error
      except sqlite3.Error as error:
        msg = f"Failed to add records: {error}"
        raise DatabaseError(msg) from error

  def set_records_active(self, ids: list[int], *, active: bool) -> int:
    """Set the active flag for record IDs and return affected row count."""
    with closing(self._connect()) as conn, conn:
      try:
        cur = conn.cursor()
        cur.executemany(
          "UPDATE Records SET active = ? WHERE id = ?;",
          [(active, record_id) for record_id in ids],
        )
      except sqlite3.Error as error:
        msg = f"Failed to update records: {error}"
        raise DatabaseError(msg) from error
      return cur.rowcount

  def get_net_balances(self) -> dict[str, int]:
    """Return per-user net balances computed from active records."""
    with closing(self._connect()) as conn, conn:
      try:
        cur = conn.cursor()
        rows = cur.execute("SELECT * FROM UserBalances;").fetchall()
      except sqlite3.Error as error:
        msg = f"Failed to fetch net balances: {error}"
        raise DatabaseError(msg) from error
    return {row["user"]: row["balance"] for row in rows}

  def _connect(self) -> sqlite3.Connection:
    """Create an SQLite connection configured for integrity and contention."""
    try:
      conn = sqlite3.connect(self._uri, uri=True, timeout=self._connect_timeout)
    except sqlite3.Error as error:
      msg = f"Failed to connect to the database at {self._uri}: {error}"
      raise DatabaseConnectionError(msg) from error
    try:
      conn.execute("PRAGMA foreign_keys = ON;")
      conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms};")
    except sqlite3.Error as error:
      msg = f"Failed to configure the database at {self._uri}: {error}"
      raise DatabaseConfigurationError(msg) from error
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
