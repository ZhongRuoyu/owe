import datetime as dt
from pathlib import Path

import pytest

from owe import (
  DatabaseConnectionError,
  DatabaseIntegrityError,
  Record,
  RecordNotFoundError,
  RecordType,
  SqliteDatabase,
  User,
  UserAlreadyExistsError,
  UserNotFoundError,
)


def create_database(database_path: Path) -> SqliteDatabase:
  """Create and initialize a test database."""
  database = SqliteDatabase(database_path, create=True)
  database.init()
  return database


def add_users(database: SqliteDatabase) -> None:
  """Insert a deterministic set of users."""
  database.add_user(User(id="alice", name="Alice"))
  database.add_user(User(id="bob", name="Bob"))
  database.add_user(User(id="carol", name="Carol"))


def make_record(
  *,
  lender: str = "alice",
  borrower: str = "bob",
  amount: int = 100,
  active: bool = True,
  remarks: str | None = "Dinner",
) -> Record:
  """Create a deterministic record for database tests."""
  created_at = dt.datetime(2026, 6, 8, 12, 30, tzinfo=dt.timezone.utc)
  return Record(
    type=RecordType.DEBT,
    lender=lender,
    borrower=borrower,
    amount=amount,
    created_by="alice",
    created_at=created_at,
    remarks=remarks,
    active=active,
  )


def test_init_creates_empty_database(database_path: Path) -> None:
  """Ensure schema initialization creates readable empty tables."""
  database = create_database(database_path)

  assert database.get_users() == []
  assert database.get_records() == []
  assert database.get_net_balances() == {}


def test_open_missing_database_without_create_fails(
  database_path: Path,
) -> None:
  """Ensure read-write mode does not create missing database files."""
  database = SqliteDatabase(database_path, create=False)

  with pytest.raises(DatabaseConnectionError):
    database.get_users()


def test_add_and_get_users_orders_by_name(database_path: Path) -> None:
  """Ensure users are persisted and ordered by display name."""
  database = create_database(database_path)
  database.add_user(User(id="charlie", name="Charlie"))
  database.add_user(User(id="alice", name="Alice"))
  database.add_user(User(id="bob", name="Bob", active=False))

  users = database.get_users()

  assert [user.id for user in users] == ["alice", "bob", "charlie"]
  assert [user.name for user in users] == ["Alice", "Bob", "Charlie"]
  assert [user.id for user in database.get_users(active_only=True)] == [
    "alice",
    "charlie",
  ]


def test_add_user_rejects_duplicate_id_or_name(database_path: Path) -> None:
  """Ensure user uniqueness constraints are surfaced as domain errors."""
  database = create_database(database_path)
  database.add_user(User(id="alice", name="Alice"))

  with pytest.raises(UserAlreadyExistsError):
    database.add_user(User(id="alice", name="Other Alice"))
  with pytest.raises(UserAlreadyExistsError):
    database.add_user(User(id="other-alice", name="Alice"))


def test_set_user_active_updates_and_rejects_missing_user(
  database_path: Path,
) -> None:
  """Ensure user activation updates rows and reports missing users."""
  database = create_database(database_path)
  database.add_user(User(id="alice", name="Alice"))
  expected_count = 1

  assert database.set_user_active("alice", active=False) == expected_count
  assert database.get_users()[0] == User(id="alice", name="Alice", active=False)
  assert database.set_user_active("alice", active=True) == expected_count
  assert database.get_users(active_only=True) == [
    User(id="alice", name="Alice"),
  ]
  with pytest.raises(UserNotFoundError):
    database.set_user_active("missing", active=True)


def test_add_records_assigns_ids_and_round_trips_fields(
  database_path: Path,
) -> None:
  """Ensure records are inserted with generated IDs and preserved fields."""
  database = create_database(database_path)
  add_users(database)
  expected_first_record_id = 1
  expected_second_record_id = 2
  dinner_amount = 100
  taxi_amount = 30
  created_at = dt.datetime(2026, 6, 8, 12, 30, tzinfo=dt.timezone.utc)
  records = [
    make_record(amount=dinner_amount),
    make_record(
      lender="bob",
      borrower="carol",
      amount=taxi_amount,
      remarks=None,
    ),
  ]

  database.add_records(records)

  assert [record.id for record in records] == [
    expected_first_record_id,
    expected_second_record_id,
  ]
  persisted = database.get_records()
  assert len(persisted) == expected_second_record_id
  assert persisted[0] == Record(
    id=expected_first_record_id,
    type=RecordType.DEBT,
    lender="alice",
    borrower="bob",
    amount=dinner_amount,
    created_by="alice",
    created_at=created_at,
    remarks="Dinner",
    active=True,
  )
  assert persisted[1].remarks is None


def test_add_records_rolls_back_on_constraint_violation(
  database_path: Path,
) -> None:
  """Ensure invalid record batches do not partially insert."""
  database = create_database(database_path)
  database.add_user(User(id="alice", name="Alice"))
  records = [
    make_record(lender="alice", borrower="missing"),
    make_record(lender="alice", borrower="alice"),
  ]

  with pytest.raises(DatabaseIntegrityError):
    database.add_records(records)

  assert database.get_records() == []
  assert all(record.id is None for record in records)


def test_get_records_filters_active_records(database_path: Path) -> None:
  """Ensure inactive records are returned only when requested."""
  database = create_database(database_path)
  add_users(database)
  expected_first_record_id = 1
  expected_second_record_id = 2
  records = [
    make_record(active=True),
    make_record(lender="bob", borrower="carol", active=False),
  ]
  database.add_records(records)

  assert [record.id for record in database.get_records()] == [
    expected_first_record_id,
    expected_second_record_id,
  ]
  assert [record.id for record in database.get_records(active_only=True)] == [
    expected_first_record_id,
  ]


def test_set_records_active_updates_batch(database_path: Path) -> None:
  """Ensure batch record status updates return affected row counts."""
  database = create_database(database_path)
  add_users(database)
  first_record_id = 1
  second_record_id = 2
  expected_count = 2
  records = [
    make_record(active=True),
    make_record(lender="bob", borrower="carol", active=True),
  ]
  database.add_records(records)

  updated_count = database.set_records_active(
    [first_record_id, second_record_id],
    active=False,
  )
  assert updated_count == expected_count
  assert [record.active for record in database.get_records()] == [False, False]
  assert database.set_records_active([first_record_id], active=True) == 1
  assert [record.id for record in database.get_records(active_only=True)] == [
    first_record_id,
  ]


def test_set_records_active_rejects_missing_ids_and_rolls_back(
  database_path: Path,
) -> None:
  """Ensure missing record IDs reject the whole status update."""
  database = create_database(database_path)
  add_users(database)
  first_record_id = 1
  missing_record_id = 3
  database.add_records([make_record()])

  with pytest.raises(RecordNotFoundError):
    database.set_records_active(
      [first_record_id, missing_record_id],
      active=False,
    )

  assert database.get_records()[0].active is True


def test_get_net_balances_uses_active_records_only(database_path: Path) -> None:
  """Ensure balances include only active records."""
  database = create_database(database_path)
  add_users(database)
  dinner_amount = 100
  taxi_amount = 30
  ignored_amount = 999
  expected_alice_balance = 100
  expected_bob_balance = -70
  expected_carol_balance = -30
  database.add_records(
    [
      make_record(amount=dinner_amount),
      make_record(lender="bob", borrower="carol", amount=taxi_amount),
      make_record(
        lender="carol",
        borrower="alice",
        amount=ignored_amount,
        active=False,
      ),
    ]
  )

  assert database.get_net_balances() == {
    "alice": expected_alice_balance,
    "bob": expected_bob_balance,
    "carol": expected_carol_balance,
  }


def test_database_persists_rows_across_instances(database_path: Path) -> None:
  """Ensure data can be read through a new database instance."""
  database = create_database(database_path)
  add_users(database)
  expected_record_count = 1
  database.add_records([make_record()])

  reopened_database = SqliteDatabase(database_path, create=False)

  assert reopened_database.get_users(active_only=True) == [
    User(id="alice", name="Alice"),
    User(id="bob", name="Bob"),
    User(id="carol", name="Carol"),
  ]
  assert len(reopened_database.get_records()) == expected_record_count
