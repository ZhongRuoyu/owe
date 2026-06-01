#!/usr/bin/env python3

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import iou.database as db
from iou.config import DATABASE


def create_user(email: str, name: str) -> int:
  try:
    db.add_user(DATABASE, email, name)
  except sqlite3.Error as error:
    print(f"Error: {error}", file=sys.stderr)
    return 1

  print(email)
  return 0


def cmd_list_users() -> int:
  users = db.get_users(DATABASE)

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


def cmd_set_active(email: str, *, active: bool) -> int:
  try:
    count = db.set_user_active(DATABASE, email, active=active)
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
    prog="iou-users.py",
    description="Manage users in the IOU bill splitter database.",
  )

  sub = parser.add_subparsers(dest="command", metavar="COMMAND")
  sub.required = True

  create_parser = sub.add_parser("create-user", help="add a new user")
  create_parser.add_argument("email", help="user's email address")
  create_parser.add_argument("name", help="user's unique display name")

  sub.add_parser("list-users", help="list all users")

  activate_parser = sub.add_parser(
    "activate-user", help="activate a user by email"
  )
  activate_parser.add_argument("email", help="email of the user to activate")

  deactivate_parser = sub.add_parser(
    "deactivate-user", help="deactivate a user by email"
  )
  deactivate_parser.add_argument(
    "email", help="email of the user to deactivate"
  )

  return parser


def main() -> int:
  parser = build_parser()
  args = parser.parse_args()

  match args.command:
    case "create-user":
      return create_user(args.email, args.name)
    case "list-users":
      return cmd_list_users()
    case "activate-user":
      return cmd_set_active(args.email, active=True)
    case "deactivate-user":
      return cmd_set_active(args.email, active=False)
    case _:
      parser.print_help()
      return 1


if __name__ == "__main__":
  sys.exit(main())
