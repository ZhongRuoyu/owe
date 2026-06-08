from logging import Logger

from .database import Database
from .record import AggregatedRecord, Record
from .summary_transaction import SummaryTransaction
from .user import User


class Owe:
  """
  The Owe bill splitter and tracker interface for retrieving and managing its
  users, records, and summaries.
  """

  _database: Database
  _logger: Logger | None

  def __init__(
    self,
    database: Database,
    *,
    logger: Logger | None = None,
  ) -> None:
    """Initialize the service with a database dependency."""
    self._database = database
    self._logger = logger

  def get_users(self, *, active_only: bool = False) -> list[User]:
    """Return users, optionally filtered to active users."""
    return self._database.get_users(active_only=active_only)

  def add_user(self, user: User) -> None:
    """Add a user to the database."""
    self._database.add_user(user)
    if self._logger:
      self._logger.info("User %s with name %s added", user.id, user.name)

  def set_user_active(self, user_id: str, *, active: bool) -> int:
    """Set a user's active status."""
    result = self._database.set_user_active(user_id, active=active)
    if self._logger:
      status = "activated" if active else "deactivated"
      self._logger.info("User %s %s", user_id, status)
    return result

  def get_records(self, *, active_only: bool = False) -> list[Record]:
    """Return records, optionally filtered to active records."""
    return self._database.get_records(active_only=active_only)

  def get_records_by_ids(self, ids: list[int]) -> list[Record]:
    """Return records whose ID appears in ``ids``."""
    record_ids = set(ids)
    return [record for record in self.get_records() if record.id in record_ids]

  def add_records(self, record: AggregatedRecord) -> list[Record]:
    """Create and persist split records from one aggregated record."""
    records = record.to_records()
    self._database.add_records(records)
    if self._logger:
      self._logger.info(
        "%d record(s) of type %s added by %s",
        len(records),
        record.type.value,
        record.created_by,
      )
    return records

  def set_records_active(
    self,
    ids: list[int],
    *,
    active: bool,
  ) -> None:
    """Activate or cancel records for the selected IDs."""
    self._database.set_records_active(ids, active=active)
    action = "activated" if active else "canceled"
    if self._logger:
      self._logger.info("%d records %s", len(ids), action)

  def get_summary(self) -> list[SummaryTransaction]:
    """Return a minimized transfer plan from current balances."""
    net_balances = self._database.get_net_balances()
    creditors = [
      (user, balance) for user, balance in net_balances.items() if balance > 0
    ]
    debtors = [
      (user, -balance) for user, balance in net_balances.items() if balance < 0
    ]
    creditors.sort(key=lambda x: x[1], reverse=True)
    debtors.sort(key=lambda x: x[1], reverse=True)

    transactions: list[SummaryTransaction] = []
    creditor_idx = 0
    debtor_idx = 0
    while creditor_idx < len(creditors) and debtor_idx < len(debtors):
      creditor_user, credit_amount = creditors[creditor_idx]
      debtor_user, debt_amount = debtors[debtor_idx]

      transfer_amount = min(credit_amount, debt_amount)
      if transfer_amount > 0:
        transactions.append(
          SummaryTransaction(
            from_user=debtor_user,
            to_user=creditor_user,
            amount=transfer_amount,
          )
        )
      new_credit_amount = credit_amount - transfer_amount
      new_debt_amount = debt_amount - transfer_amount
      creditors[creditor_idx] = (creditor_user, new_credit_amount)
      debtors[debtor_idx] = (debtor_user, new_debt_amount)

      if new_credit_amount == 0:
        creditor_idx += 1
      if new_debt_amount == 0:
        debtor_idx += 1

    return transactions
