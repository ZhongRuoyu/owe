import logging

import requests

from .record import Record
from .user import User

logger = logging.getLogger(__name__)


def try_get_user_name(email: str, users_by_email: dict[str, User]) -> str:
  """Resolve a user email to display name, falling back to the email."""
  if email in users_by_email:
    return users_by_email[email].name
  return email


def record_message(
  record: Record,
  currency: str,
  users_by_email: dict[str, User],
) -> str:
  """Format a single record as a human-readable notification line."""
  lender = try_get_user_name(record.lender, users_by_email)
  borrower = try_get_user_name(record.borrower, users_by_email)
  amount = record.amount / 100
  message = f"[{record.type}] {lender} -> {borrower}: {currency} {amount:.2f}"
  if record.remarks:
    message += f" ({record.remarks})"
  return message


def format_records(
  records: list[Record],
  currency: str,
  users: list[User],
) -> str:
  """Format grouped new-record notifications for Telegram."""
  users_by_email = {user.email: user for user in users}

  records_by_creator: dict[str, list[Record]] = {}
  for record in records:
    records_by_creator.setdefault(record.created_by, []).append(record)
  records_by_creator = dict(sorted(records_by_creator.items()))

  messages = []
  for creator, creator_records in records_by_creator.items():
    creator_name = try_get_user_name(creator, users_by_email)
    record_count = len(creator_records)
    records_word = "record" if record_count == 1 else "records"
    message = (
      f"{record_count} new Owe {records_word} added by {creator_name}:\n"
    )
    for record in creator_records:
      message += f"- {record_message(record, currency, users_by_email)}\n"
    messages.append(message)
  return "\n\n".join(messages)


def format_record_status_change(
  records: list[Record],
  currency: str,
  users: list[User],
  requester: str,
  *,
  active: bool,
) -> str:
  """Format record status update notifications for Telegram."""
  users_by_email = {user.email: user for user in users}

  requester_name = try_get_user_name(requester, users_by_email)
  record_count = len(records)
  records_word = "record" if record_count == 1 else "records"
  action = "activated" if active else "canceled"
  message = f"{record_count} Owe {records_word} {action} by {requester_name}:\n"
  for record in records:
    message += f"- {record_message(record, currency, users_by_email)}\n"
  return message


def post_message(bot_token: str, chat_id: str, message: str) -> None:
  """Send a message to a Telegram chat and log failures."""
  try:
    response = requests.post(
      f"https://api.telegram.org/bot{bot_token}/sendMessage",
      json={"chat_id": chat_id, "text": message},
      timeout=10,
    )
    response.raise_for_status()
  except requests.RequestException:
    logger.exception("Telegram notification failed")


def announce_records(
  records: list[Record],
  currency: str,
  users: list[User],
  bot_token: str,
  chat_id: str,
) -> None:
  """Build and send a new-record announcement to Telegram."""
  post_message(bot_token, chat_id, format_records(records, currency, users))


def announce_record_status_change(  # noqa: PLR0913
  records: list[Record],
  currency: str,
  users: list[User],
  requester: str,
  bot_token: str,
  chat_id: str,
  *,
  active: bool,
) -> None:
  """Build and send a record-status announcement to Telegram."""
  post_message(
    bot_token,
    chat_id,
    format_record_status_change(
      records, currency, users, requester, active=active
    ),
  )
