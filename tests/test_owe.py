import datetime as dt
import unittest
from unittest.mock import Mock

from owe import (
  AggregatedRecord,
  Owe,
  Record,
  RecordType,
  SummaryTransaction,
  User,
)


def make_record(record_id: int) -> Record:
  """Create a deterministic sample record for tests."""
  return Record(
    id=record_id,
    type=RecordType.DEBT,
    lender="lender",
    borrower=f"borrower-{record_id}",
    amount=100,
    created_by="creator",
    created_at=dt.datetime.now(tz=dt.timezone.utc),
    remarks=None,
  )


class OweTests(unittest.TestCase):
  def setUp(self) -> None:
    """Create an Owe service with a mocked database backend."""
    self.database = Mock()
    self.owe = Owe(self.database)

  def test_get_users_returns_all_users_by_default(self) -> None:
    """Ensure user lookup delegates to the database without a filter."""
    users = [
      User(id="one", name="One", active=True),
      User(id="two", name="Two", active=False),
    ]
    self.database.get_users.return_value = users

    result = self.owe.get_users()

    assert result == users
    self.database.get_users.assert_called_once_with(active_only=False)

  def test_get_users_returns_active_users_when_active_only(self) -> None:
    """
    Ensure active-user lookup calls the database with ``active_only=True``.
    """
    users = [
      User(id="user", name="User", active=True),
    ]
    self.database.get_users.return_value = users

    result = self.owe.get_users(active_only=True)

    assert result == users
    self.database.get_users.assert_called_once_with(active_only=True)

  def test_add_user_inserts_user_into_database(self) -> None:
    """Ensure add_user delegates user insertion to the database."""
    user = User(id="new", name="New User")

    self.owe.add_user(user)

    self.database.add_user.assert_called_once_with(user)

  def test_set_user_active_updates_database_and_returns_row_count(
    self,
  ) -> None:
    """Ensure set_user_active forwards arguments and returns row count."""
    self.database.set_user_active.return_value = 1

    count = self.owe.set_user_active(
      "user",
      active=False,
    )

    assert count == 1
    self.database.set_user_active.assert_called_once_with(
      "user",
      active=False,
    )

  def test_get_records_returns_records_from_database(self) -> None:
    """
    Ensure record lookup delegates to the database and returns rows unchanged.
    """
    records = [make_record(1)]
    self.database.get_records.return_value = records

    result = self.owe.get_records()

    assert result == records
    self.database.get_records.assert_called_once_with(active_only=False)

  def test_get_records_by_ids_returns_selected_records(self) -> None:
    """
    Ensure selected-record lookup filters by ID while preserving database order.
    """
    all_records = [make_record(1), make_record(2), make_record(4)]
    self.database.get_records.return_value = all_records

    selected = self.owe.get_records_by_ids([4, 1])

    assert selected == [all_records[0], all_records[2]]
    self.database.get_records.assert_called_once_with(active_only=False)

  def test_add_records_inserts_records(self) -> None:
    """Ensure add_records inserts split records and returns them."""
    record = AggregatedRecord(
      type=RecordType.DEBT,
      lender="lender",
      borrowers=["borrower-1", "borrower-2"],
      amount=101,
      created_by="creator",
      remarks="Dinner",
    )

    inserted_records = self.owe.add_records(record)

    self.database.add_records.assert_called_once_with(inserted_records)
    assert [r.amount for r in inserted_records] == [51, 51]
    assert [r.borrower for r in inserted_records] == [
      "borrower-1",
      "borrower-2",
    ]

  def test_set_records_active_updates_database(self) -> None:
    """Ensure set_records_active delegates status updates to the database."""
    self.owe.set_records_active([3, 7], active=False)

    self.database.set_records_active.assert_called_once_with(
      [3, 7], active=False
    )

  def test_get_summary_returns_minimal_transactions(self) -> None:
    """Ensure summary computes the expected minimal settlement transfers."""
    balances = {
      "alice": 80,
      "bob": 20,
      "carol": -50,
      "dave": -30,
      "eve": -20,
    }
    self.database.get_net_balances.return_value = balances

    summary = self.owe.get_summary()

    assert summary == [
      SummaryTransaction(
        from_user="carol",
        to_user="alice",
        amount=50,
      ),
      SummaryTransaction(
        from_user="dave",
        to_user="alice",
        amount=30,
      ),
      SummaryTransaction(
        from_user="eve",
        to_user="bob",
        amount=20,
      ),
    ]
    self.database.get_net_balances.assert_called_once_with()

  def test_get_summary_returns_empty_for_balanced_book(self) -> None:
    """Ensure summary is empty when no balances are outstanding."""
    self.database.get_net_balances.return_value = {}

    summary = self.owe.get_summary()

    assert summary == []
    self.database.get_net_balances.assert_called_once_with()


if __name__ == "__main__":
  unittest.main()
