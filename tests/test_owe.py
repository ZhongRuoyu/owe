import datetime as dt
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask

from owe import owe
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
    """Create and push an app context with test config values."""
    self.app = Flask(__name__)
    self.app.config.update(
      {
        "LOG_LEVEL": "INFO",
        "DATABASE": Path("test-owe.db"),
        "CURRENCY": "USD",
        "REQUEST_EMAIL_HEADER": None,
        "TELEGRAM_BOT_TOKEN": None,
        "TELEGRAM_CHAT_ID": None,
      }
    )
    self.ctx = self.app.app_context()
    self.ctx.push()

  def tearDown(self) -> None:
    """Pop the app context created for each test."""
    self.ctx.pop()

  def test_get_active_users_uses_active_filter(self) -> None:
    """
    Ensure active-user lookup calls the database with ``active_only=True``.
    """
    users = [
      User(email="user@example.com", name="User", active=True),
    ]
    with patch.object(
      owe.database, "get_users", return_value=users
    ) as get_users:
      result = owe.get_active_users()

    assert result == users
    get_users.assert_called_once_with(
      self.app.config["DATABASE"],
      active_only=True,
    )

  def test_get_records_returns_records_from_db(self) -> None:
    """
    Ensure record lookup delegates to the database and returns rows unchanged.
    """
    records = [make_record(1)]
    with patch.object(
      owe.database,
      "get_records",
      return_value=records,
    ) as get_records:
      result = owe.get_records()

    assert result == records
    get_records.assert_called_once_with(self.app.config["DATABASE"])

  def test_add_records_inserts_records_without_telegram(self) -> None:
    """Ensure add_records inserts split records without notifications."""
    record = AggregatedRecord(
      type="DEBT",
      lender="lender@example.com",
      borrowers=["borrower-1@example.com", "borrower-2@example.com"],
      amount=101,
      created_by="creator@example.com",
      remarks="Dinner",
    )

    with (
      patch.object(owe.database, "add_records") as add_records,
      patch.object(owe.threading, "Thread") as thread,
    ):
      owe.add_records(record)

    add_records.assert_called_once()
    assert add_records.call_args.args[0] == self.app.config["DATABASE"]
    inserted_records = add_records.call_args.args[1]
    assert [r.amount for r in inserted_records] == [51, 51]
    assert [r.borrower for r in inserted_records] == [
      "borrower-1@example.com",
      "borrower-2@example.com",
    ]
    thread.assert_not_called()

  def test_add_records_starts_telegram_thread_when_configured(self) -> None:
    """Ensure add_records triggers Telegram notifications when configured."""
    records = [make_record(1), make_record(2)]
    users = [User(email="user@example.com", name="User", active=True)]
    aggregated = Mock()
    aggregated.to_records.return_value = records
    aggregated.type = "PAYMENT"
    aggregated.created_by = "creator@example.com"

    thread_instance = Mock()
    with (
      patch.object(owe.database, "add_records") as add_records,
      patch.object(
        owe,
        "get_active_users",
        return_value=users,
      ) as get_active_users,
      patch.object(
        owe.threading,
        "Thread",
        return_value=thread_instance,
      ) as thread,
    ):
      self.app.config["TELEGRAM_BOT_TOKEN"] = "token"  # noqa: S105
      self.app.config["TELEGRAM_CHAT_ID"] = "chat"
      owe.add_records(aggregated)

    add_records.assert_called_once_with(self.app.config["DATABASE"], records)
    get_active_users.assert_called_once_with()
    thread.assert_called_once_with(
      target=owe.announce_records,
      args=(
        records,
        self.app.config["CURRENCY"],
        users,
        "token",
        "chat",
      ),
      daemon=False,
    )
    thread_instance.start.assert_called_once_with()

  def test_set_records_active_updates_db_without_telegram(self) -> None:
    """
    Ensure set_records_active updates the database without Telegram config.
    """
    with (
      patch.object(owe.database, "set_records_active") as set_records_active,
      patch.object(owe.threading, "Thread") as thread,
    ):
      owe.set_records_active([3, 7], active=False, requester="req")

    set_records_active.assert_called_once_with(
      self.app.config["DATABASE"],
      [3, 7],
      active=False,
    )
    thread.assert_not_called()

  def test_set_records_active_notifies_with_selected_records(self) -> None:
    """Ensure set_records_active notifies only selected records."""
    all_records = [make_record(1), make_record(2), make_record(4)]
    users = [User(email="user@example.com", name="User", active=True)]
    thread_instance = Mock()

    with (
      patch.object(owe.database, "set_records_active") as set_records_active,
      patch.object(owe, "get_records", return_value=all_records),
      patch.object(owe.database, "get_users", return_value=users),
      patch.object(
        owe.threading,
        "Thread",
        return_value=thread_instance,
      ) as thread,
    ):
      self.app.config["TELEGRAM_BOT_TOKEN"] = "token"  # noqa: S105
      self.app.config["TELEGRAM_CHAT_ID"] = "chat"
      owe.set_records_active([4, 1], active=True, requester="requester")

    set_records_active.assert_called_once_with(
      self.app.config["DATABASE"],
      [4, 1],
      active=True,
    )
    selected_records = [all_records[0], all_records[2]]
    thread.assert_called_once_with(
      target=owe.announce_record_status_change,
      args=(
        selected_records,
        self.app.config["CURRENCY"],
        users,
        "requester",
        "token",
        "chat",
      ),
      kwargs={"active": True},
      daemon=False,
    )
    thread_instance.start.assert_called_once_with()

  def test_get_summary_returns_minimal_transactions(self) -> None:
    """Ensure summary computes the expected minimal settlement transfers."""
    balances = {
      "alice@example.com": 80,
      "bob@example.com": 20,
      "carol@example.com": -50,
      "dave@example.com": -30,
      "eve@example.com": -20,
    }
    with patch.object(
      owe.database,
      "get_net_balances",
      return_value=balances,
    ) as get_net_balances:
      summary = owe.get_summary()

    assert summary == [
      {"from": "carol@example.com", "to": "alice@example.com", "amount": 50},
      {"from": "dave@example.com", "to": "alice@example.com", "amount": 30},
      {"from": "eve@example.com", "to": "bob@example.com", "amount": 20},
    ]
    get_net_balances.assert_called_once_with(self.app.config["DATABASE"])

  def test_get_summary_returns_empty_for_balanced_book(self) -> None:
    """Ensure summary is empty when no balances are outstanding."""
    with patch.object(owe.database, "get_net_balances", return_value={}):
      summary = owe.get_summary()

    assert summary == []


if __name__ == "__main__":
  unittest.main()
