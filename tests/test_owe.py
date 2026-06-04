import datetime as dt
import unittest
from unittest.mock import Mock

from owe.owe import Owe
from owe.record import AggregatedRecord, Record
from owe.user import User


def make_record(record_id: int) -> Record:
  """Create a deterministic sample record for tests."""
  return Record(
    id=record_id,
    type="DEBT",
    lender="lender@example.com",
    borrower=f"borrower-{record_id}@example.com",
    amount=100,
    created_by="creator@example.com",
    created_at=dt.datetime.now(tz=dt.timezone.utc),
    remarks=None,
  )


class OweTests(unittest.TestCase):
  def setUp(self) -> None:
    """Create an Owe service with a mocked database dependency."""
    self.database = Mock()
    self.owe = Owe(self.database)

  def test_get_users_returns_all_users_by_default(self) -> None:
    """Ensure user lookup delegates to the database without a filter."""
    users = [
      User(email="one@example.com", name="One", active=True),
      User(email="two@example.com", name="Two", active=False),
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
      User(email="user@example.com", name="User", active=True),
    ]
    self.database.get_users.return_value = users

    result = self.owe.get_users(active_only=True)

    assert result == users
    self.database.get_users.assert_called_once_with(active_only=True)

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
      type="DEBT",
      lender="lender@example.com",
      borrowers=["borrower-1@example.com", "borrower-2@example.com"],
      amount=101,
      created_by="creator@example.com",
      remarks="Dinner",
    )

    inserted_records = self.owe.add_records(record)

    self.database.add_records.assert_called_once_with(inserted_records)
    assert [r.amount for r in inserted_records] == [51, 51]
    assert [r.borrower for r in inserted_records] == [
      "borrower-1@example.com",
      "borrower-2@example.com",
    ]

  def test_set_records_active_updates_database(self) -> None:
    """Ensure set_records_active delegates status updates to the database."""
    self.owe.set_records_active([3, 7], active=False, requester="req")

    self.database.set_records_active.assert_called_once_with(
      [3, 7], active=False
    )

  def test_get_summary_returns_minimal_transactions(self) -> None:
    """Ensure summary computes the expected minimal settlement transfers."""
    balances = {
      "alice@example.com": 80,
      "bob@example.com": 20,
      "carol@example.com": -50,
      "dave@example.com": -30,
      "eve@example.com": -20,
    }
    self.database.get_net_balances.return_value = balances

    summary = self.owe.get_summary()

    assert summary == [
      {"from": "carol@example.com", "to": "alice@example.com", "amount": 50},
      {"from": "dave@example.com", "to": "alice@example.com", "amount": 30},
      {"from": "eve@example.com", "to": "bob@example.com", "amount": 20},
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
