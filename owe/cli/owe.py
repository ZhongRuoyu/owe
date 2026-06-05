import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

from owe.owe import Owe, SummaryTransaction
from owe.record import AggregatedRecord, Record, RecordType
from owe.user import User


def print_table(header: list[str], rows: list[list[str]]) -> None:
  """Print a fixed-width table with the given header and rows."""
  col_widths = [len(column) for column in header]
  for row in rows:
    for i, cell in enumerate(row):
      col_widths[i] = max(col_widths[i], len(cell))

  header_line = "  ".join(
    f"{column:<{col_widths[i]}}" for i, column in enumerate(header)
  )
  rule_line = "-" * len(header_line)
  print(header_line)
  print(rule_line)
  for row in rows:
    print("  ".join(f"{cell:<{col_widths[i]}}" for i, cell in enumerate(row)))


def print_users(users: list[User], *, output_format: str) -> None:
  """Print a list of users in a fixed-width table or JSON format."""
  match output_format:
    case "table":
      print_table(
        header=["EMAIL", "NAME", "STATUS"],
        rows=[
          [
            user.email,
            user.name,
            "active" if user.active else "inactive",
          ]
          for user in users
        ],
      )
    case "json":
      print(json.dumps([user.to_dict() for user in users], indent=2))
    case "csv":
      writer = csv.writer(sys.stdout)
      writer.writerow(User.csv_header())
      for user in users:
        writer.writerow(user.to_csv_row())


def print_records(records: list[Record], *, output_format: str) -> None:
  """Print a list of records in a fixed-width table or JSON format."""
  match output_format:
    case "table":
      print_table(
        header=[
          "ID",
          "TYPE",
          "LENDER",
          "BORROWER",
          "AMOUNT",
          "CREATED BY",
          "CREATED AT",
          "REMARKS",
          "ACTIVE",
        ],
        rows=[
          [
            str(record.id),
            record.type.value,
            record.lender,
            record.borrower,
            str(record.amount),
            record.created_by,
            record.created_at.isoformat(timespec="milliseconds"),
            record.remarks or "",
            "active" if record.active else "inactive",
          ]
          for record in records
        ],
      )
    case "json":
      print(json.dumps([record.to_dict() for record in records], indent=2))
      return
    case "csv":
      writer = csv.writer(sys.stdout)
      writer.writerow(Record.csv_header())
      for record in records:
        writer.writerow(record.to_csv_row())


def print_summary(
  summary: list[SummaryTransaction],
  *,
  output_format: str,
) -> None:
  """
  Print a list of summary transactions in a fixed-width table or JSON format.
  """
  match output_format:
    case "table":
      print_table(
        header=["FROM", "TO", "AMOUNT"],
        rows=[
          [
            transaction.from_user,
            transaction.to_user,
            str(transaction.amount),
          ]
          for transaction in summary
        ],
      )
    case "json":
      print(
        json.dumps([transaction.to_dict() for transaction in summary], indent=2)
      )
      return


def list_users(owe: Owe, *, active_only: bool, output_format: str) -> int:
  """Print all users in a fixed-width table."""
  users = owe.get_users(active_only=active_only)
  if not users:
    print("No users found.")
    return 0

  print_users(users, output_format=output_format)
  return 0


def add_user(owe: Owe, email: str, name: str) -> int:
  """Add a user and print the new user's email on success."""
  user = User(email, name)
  try:
    owe.add_user(user)
  except sqlite3.Error as error:
    print(f"Error: {error}", file=sys.stderr)
    return 1

  print(user.email)
  return 0


def set_user_active(owe: Owe, email: str, *, active: bool) -> int:
  """Set a user's active status and print the email on success."""
  try:
    count = owe.set_user_active(email, active=active)
  except sqlite3.Error as error:
    print(f"Error: {error}", file=sys.stderr)
    return 1

  if count == 0:
    print("Error: User not found", file=sys.stderr)
    return 1

  print(email)
  return 0


def list_records(owe: Owe, *, active_only: bool, output_format: str) -> int:
  """Print all records in a fixed-width table."""
  records = owe.get_records(active_only=active_only)
  if not records:
    print("No records found.")
    return 0

  print_records(records, output_format=output_format)
  return 0


def add_records(  # noqa: PLR0913
  owe: Owe,
  *,
  record_type: str,
  lender: str,
  borrowers: list[str],
  amount: float,
  created_by: str,
  remarks: str | None = None,
  output_format: str,
) -> int:
  """Add a new aggregated record, and print the created records on success."""
  aggregated_record = AggregatedRecord(
    type=RecordType(record_type),
    lender=lender,
    borrowers=borrowers,
    amount=int(amount * 100),
    created_by=created_by,
    remarks=remarks,
  )
  try:
    records = owe.add_records(aggregated_record)
  except sqlite3.Error as error:
    print(f"Error: {error}", file=sys.stderr)
    return 1

  print_records(records, output_format=output_format)
  return 0


def set_record_active(owe: Owe, ids: list[int], *, active: bool) -> int:
  """Activate or cancel records by IDs, and print the IDs on success."""
  try:
    owe.set_records_active(ids, active=active)
  except sqlite3.Error as error:
    print(f"Error: {error}", file=sys.stderr)
    return 1

  for record_id in ids:
    print(record_id)
  return 0


def show_summary(owe: Owe, *, output_format: str) -> int:
  """Print the summary of transactions in a fixed-width table or JSON format."""
  summary = owe.get_summary()
  if not summary:
    print("No transactions found.")
    return 0

  print_summary(summary, output_format=output_format)
  return 0


def build_parser() -> argparse.ArgumentParser:
  """Build the command-line parser for ``owe``."""
  parser = argparse.ArgumentParser(
    prog="owe",
    description="Bill splitter and tracker.",
  )
  parser.add_argument(
    "--database",
    type=Path,
    default=Path("owe.db"),
    help="path to the SQLite database file (default: owe.db)",
  )
  command = parser.add_subparsers(
    dest="command",
    metavar="COMMAND",
    required=True,
  )

  user_parser = command.add_parser(
    "user",
    help="manage users",
    description="Manage users in the Owe database.",
  )
  user_command = user_parser.add_subparsers(
    dest="user_command",
    metavar="USER_COMMAND",
    required=True,
  )

  user_list_parser = user_command.add_parser(
    "list",
    help="list all users",
  )
  user_list_parser.add_argument(
    "--active",
    help="list active users only",
    action="store_true",
  )
  user_list_parser.add_argument(
    "--format",
    help="output format for listing users",
    choices=["table", "json"],
    default="table",
  )
  user_add_parser = user_command.add_parser(
    "add",
    help="add a new user",
  )
  user_add_parser.add_argument(
    "email",
    help="user's email address",
  )
  user_add_parser.add_argument(
    "name",
    help="user's unique display name",
  )
  user_activate_parser = user_command.add_parser(
    "activate",
    help="activate a user by email",
  )
  user_activate_parser.add_argument(
    "email",
    help="email of the user to activate",
  )
  user_deactivate_parser = user_command.add_parser(
    "deactivate",
    help="deactivate a user by email",
  )
  user_deactivate_parser.add_argument(
    "email",
    help="email of the user to deactivate",
  )

  record_parser = command.add_parser(
    "record",
    help="manage records",
    description="Manage records in the Owe database.",
  )
  record_command = record_parser.add_subparsers(
    dest="record_command",
    metavar="RECORD_COMMAND",
    required=True,
  )

  record_list_parser = record_command.add_parser(
    "list",
    help="list all records",
  )
  record_list_parser.add_argument(
    "--active",
    help="list active records only",
    action="store_true",
  )
  record_list_parser.add_argument(
    "--format",
    help="output format for listing records",
    choices=["table", "json", "csv"],
    default="table",
  )
  record_add_parser = record_command.add_parser(
    "add",
    help="add new records from an aggregated record",
  )
  record_add_parser.add_argument(
    "--type",
    help="type of the aggregated record",
    choices=[record_type.value for record_type in RecordType],
    required=True,
  )
  record_add_parser.add_argument(
    "--lender",
    help="email of the lender",
    required=True,
  )
  record_add_parser.add_argument(
    "--borrower",
    help="email of the borrower (repeat for multiple borrowers)",
    required=True,
    metavar="BORROWER",
    dest="borrowers",
    action="append",
  )
  record_add_parser.add_argument(
    "--amount",
    help="total amount",
    type=float,
    required=True,
  )
  record_add_parser.add_argument(
    "--created-by",
    help="email of the user who created the record",
    required=True,
  )
  record_add_parser.add_argument(
    "--remarks",
    help="remarks for the record",
  )
  record_add_parser.add_argument(
    "--format",
    help="output format for created records",
    choices=["table", "json", "csv"],
    default="table",
  )
  record_activate_parser = record_command.add_parser(
    "activate",
    help="activate a record by ID",
  )
  record_activate_parser.add_argument(
    "--id",
    help="ID of the record to activate (repeat for multiple records)",
    required=True,
    metavar="ID",
    dest="ids",
    action="append",
  )
  record_cancel_parser = record_command.add_parser(
    "cancel",
    help="cancel a record by ID",
  )
  record_cancel_parser.add_argument(
    "--id",
    help="ID of the record to cancel (repeat for multiple records)",
    required=True,
    metavar="ID",
    dest="ids",
    action="append",
  )
  record_summary_parser = record_command.add_parser(
    "summary",
    help="show the summary of transactions",
  )
  record_summary_parser.add_argument(
    "--format",
    help="output format for summary transactions",
    choices=["table", "json"],
    default="table",
  )

  database_parser = command.add_parser(
    "database",
    help="manage the database",
    description="Manage the Owe database.",
  )
  database_command = database_parser.add_subparsers(
    dest="database_command",
    metavar="DATABASE_COMMAND",
    required=True,
  )

  database_init_parser = database_command.add_parser(  # noqa: F841
    "init",
    help="initialize the database, creating tables if they do not exist",
  )

  return parser


def handle_user_command(owe: Owe, args: argparse.Namespace) -> int:
  """Handle the "user" subcommand and its subcommands."""
  result = None
  match args.user_command:
    case "list":
      result = list_users(
        owe,
        active_only=args.active,
        output_format=args.format,
      )
    case "add":
      result = add_user(owe, args.email, args.name)
    case "activate":
      result = set_user_active(owe, args.email, active=True)
    case "deactivate":
      result = set_user_active(owe, args.email, active=False)
  if result is not None:
    return result
  return 1


def handle_record_command(owe: Owe, args: argparse.Namespace) -> int:
  """Handle the "record" subcommand and its subcommands."""
  result = None
  match args.record_command:
    case "list":
      result = list_records(
        owe,
        active_only=args.active,
        output_format=args.format,
      )
    case "add":
      result = add_records(
        owe,
        record_type=args.type,
        lender=args.lender,
        borrowers=args.borrowers,
        amount=args.amount,
        created_by=args.created_by,
        remarks=args.remarks,
        output_format=args.format,
      )
    case "activate":
      result = set_record_active(owe, args.ids, active=True)
    case "cancel":
      result = set_record_active(owe, args.ids, active=False)
    case "summary":
      result = show_summary(owe, output_format=args.format)
  if result is not None:
    return result
  return 1


def handle_database_command(args: argparse.Namespace) -> int:
  """Handle the "database" subcommand and its subcommands."""
  result = None
  match args.database_command:
    case "init":
      owe = Owe(args.database, create_database=True)
      owe.init()
      result = 0
  if result is not None:
    return result
  return 1


def main() -> int:
  """Run the ``owe`` command-line entry point."""
  parser = build_parser()
  args = parser.parse_args()

  result = None
  match args.command:
    case "user":
      owe = Owe(args.database, create_database=False)
      result = handle_user_command(owe, args)
    case "record":
      owe = Owe(args.database, create_database=False)
      result = handle_record_command(owe, args)
    case "database":
      result = handle_database_command(args)
  if result is not None:
    return result
  return 1


if __name__ == "__main__":
  sys.exit(main())
