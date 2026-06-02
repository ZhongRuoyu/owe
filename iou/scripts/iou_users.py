#!/usr/bin/env python3

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import iou.database as db
from iou.config import DATABASE


def create_user(database: Path, email: str, name: str) -> int:
  try:
    db.add_user(database, email, name)
  except sqlite3.Error as error:
    print(f"Error: {error}", file=sys.stderr)
    return 1

  print(email)
  return 0


def list_users(database: Path) -> int:
  users = db.get_users(database)
  if not users:
    print("No users found.")
    return 0

  col_email = max(len("EMAIL"), *(len(user.email) for user in users))
  col_name = max(len("NAME"), *(len(user.name) for user in users))
  col_status = max(
    len("STATUS"),
    (
      len("inactive")
      if any(not user.active for user in users)
      else len("active")
    ),
  )

  header = (
    f"{'EMAIL':<{col_email}}  {'NAME':<{col_name}}  {'STATUS':<{col_status}}"
  )
  rule = "-" * len(header)
  print(header)
  print(rule)
  for user in users:
    email = user.email
    name = user.name
    status = "active" if user.active else "inactive"
    print(f"{email:<{col_email}}  {name:<{col_name}}  {status:<{col_status}}")

  return 0


def set_active(database: Path, email: str, *, active: bool) -> int:
  try:
    count = db.set_user_active(database, email, active=active)
  except sqlite3.Error as error:
    print(f"Error: {error}", file=sys.stderr)
    return 1

  if count == 0:
    print("Error: User not found", file=sys.stderr)
    return 1

  print(email)
  return 0


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    prog="iou-users",
    description="Manage users in the IOU bill splitter database.",
  )

  sub = parser.add_subparsers(dest="command", metavar="COMMAND")
  sub.required = True

  create_parser = sub.add_parser("create", help="add a new user")
  create_parser.add_argument("email", help="user's email address")
  create_parser.add_argument("name", help="user's unique display name")

  sub.add_parser("list", help="list all users")

  activate_parser = sub.add_parser("activate", help="activate a user by email")
  activate_parser.add_argument("email", help="email of the user to activate")

  deactivate_parser = sub.add_parser(
    "deactivate", help="deactivate a user by email"
  )
  deactivate_parser.add_argument(
    "email", help="email of the user to deactivate"
  )

  return parser


def main() -> int:
  parser = build_parser()
  args = parser.parse_args()

  database = DATABASE
  if not database.exists():
    print(f"Error: Database file {database} not found")
    return 1

  match args.command:
    case "create":
      return create_user(database, args.email, args.name)
    case "list":
      return list_users(database)
    case "activate":
      return set_active(database, args.email, active=True)
    case "deactivate":
      return set_active(database, args.email, active=False)
    case _:
      parser.print_help()
      return 1


if __name__ == "__main__":
  sys.exit(main())
