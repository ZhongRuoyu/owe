from logging import Logger

import requests

from owe.record import Record
from owe.user import User

TELEGRAM_DEFAULT_SEND_TIMEOUT = 15


class TelegramAnnouncer:
  """Send Owe notifications to a Telegram chat."""

  _bot_token: str
  _chat_id: str
  _currency: str
  _logger: Logger | None
  _send_timeout: int

  def __init__(
    self,
    *,
    bot_token: str,
    chat_id: str,
    currency: str,
    logger: Logger | None = None,
    send_timeout: int = TELEGRAM_DEFAULT_SEND_TIMEOUT,
  ) -> None:
    """Initialize the announcer with required Telegram settings."""
    self._bot_token = bot_token
    self._chat_id = chat_id
    self._currency = currency
    self._logger = logger
    self._send_timeout = send_timeout

  def announce_records(self, records: list[Record], users: list[User]) -> None:
    """Build and send a new-record announcement to Telegram."""
    self._post_message(self._format_records(records, users))

  def announce_record_status_change(
    self,
    records: list[Record],
    users: list[User],
    requester: str,
    *,
    active: bool,
  ) -> None:
    """Build and send a record-status announcement to Telegram."""
    self._post_message(
      self._format_record_status_change(
        records,
        users,
        requester,
        active=active,
      )
    )

  def _format_records(self, records: list[Record], users: list[User]) -> str:
    """Format grouped new-record notifications for Telegram."""
    users_by_email = {user.email: user for user in users}

    records_by_creator: dict[str, list[Record]] = {}
    for record in records:
      records_by_creator.setdefault(record.created_by, []).append(record)
    records_by_creator = dict(sorted(records_by_creator.items()))

    messages = []
    for creator, creator_records in records_by_creator.items():
      creator_name = self._try_get_user_name(creator, users_by_email)
      record_count = len(creator_records)
      records_word = "record" if record_count == 1 else "records"
      message = (
        f"{record_count} new Owe {records_word} added by {creator_name}:\n"
      )
      for record in creator_records:
        message += f"- {self._record_message(record, users_by_email)}\n"
      messages.append(message)
    return "\n\n".join(messages)

  def _format_record_status_change(
    self,
    records: list[Record],
    users: list[User],
    requester: str,
    *,
    active: bool,
  ) -> str:
    """Format record status update notifications for Telegram."""
    users_by_email = {user.email: user for user in users}

    requester_name = self._try_get_user_name(requester, users_by_email)
    record_count = len(records)
    records_word = "record" if record_count == 1 else "records"
    action = "activated" if active else "canceled"
    message = (
      f"{record_count} Owe {records_word} {action} by {requester_name}:\n"
    )
    for record in records:
      message += f"- {self._record_message(record, users_by_email)}\n"
    return message

  def _post_message(self, message: str) -> None:
    """Send a message to a Telegram chat and log failures."""
    try:
      response = requests.post(
        f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
        json={"chat_id": self._chat_id, "text": message},
        timeout=self._send_timeout,
      )
      response.raise_for_status()
    except requests.RequestException:
      if self._logger:
        self._logger.exception("Telegram notification failed")

  def _record_message(
    self,
    record: Record,
    users_by_email: dict[str, User],
  ) -> str:
    """Format one record as a human-readable notification line."""
    lender = self._try_get_user_name(record.lender, users_by_email)
    borrower = self._try_get_user_name(record.borrower, users_by_email)
    amount = record.amount / 100
    message = (
      f"[{record.type.value}] {lender} -> {borrower}: "
      f"{self._currency} {amount:.2f}"
    )
    if record.remarks:
      message += f" ({record.remarks})"
    return message

  @staticmethod
  def _try_get_user_name(email: str, users_by_email: dict[str, User]) -> str:
    """Resolve a user email to display name, falling back to the email."""
    if email in users_by_email:
      return users_by_email[email].name
    return email
