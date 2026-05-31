import logging
from typing import TYPE_CHECKING

import requests

import iou.database as db
from iou.config import DATABASE

if TYPE_CHECKING:
  from iou.record import Record
  from iou.user import User

logger = logging.getLogger(__name__)


def try_get_user_name(email: str, users_by_email: dict[str, User]) -> str:
  if email in users_by_email:
    return users_by_email[email].name
  return email


def record_message(
  record: Record,
  currency: str,
  users_by_email: dict[str, User],
) -> str:
  lender = try_get_user_name(record.lender, users_by_email)
  borrower = try_get_user_name(record.borrower, users_by_email)
  amount = record.amount / 100
  message = f"{lender} -> {borrower}: {currency} {amount:.2f}"
  if record.remarks:
    message += f" ({record.remarks})"
  return message


def format_records(records: list[Record], currency: str) -> str:
  users = db.get_users(DATABASE)
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
      f"{record_count} new IOU {records_word} added by {creator_name}:\n"
    )
    for record in creator_records:
      message += f"- {record_message(record, currency, users_by_email)}\n"
    messages.append(message)
  return "\n\n".join(messages)


def announce_records(
  records: list[Record],
  currency: str,
  bot_token: str,
  chat_id: str,
) -> None:
  message = format_records(records, currency)
  try:
    response = requests.post(
      f"https://api.telegram.org/bot{bot_token}/sendMessage",
      json={"chat_id": chat_id, "text": message},
      timeout=10,
    )
    response.raise_for_status()
  except requests.RequestException:
    logger.exception("Telegram notification failed")
