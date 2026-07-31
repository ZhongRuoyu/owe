# Copyright (c) 2024 - 2026 Ruoyu Zhong
# SPDX-License-Identifier: MIT

import csv
import io
import json
import sys
from pathlib import Path
from typing import cast

import pytest

from owe import RecordType
from owe.cli import owe as cli


def run_cli(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  database_path: Path,
  *args: str,
) -> tuple[int, str, str]:
  """Run the CLI entry point against a test database."""
  monkeypatch.setattr(
    sys,
    "argv",
    ["owe", "--database", str(database_path), *args],
  )
  exit_code = cli.main()
  captured = capsys.readouterr()
  return exit_code, captured.out, captured.err


def init_database(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  database_path: Path,
) -> None:
  """Initialize a CLI test database."""
  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "database",
    "init",
  )

  assert exit_code == 0
  assert stdout == ""
  assert stderr == ""


def add_user(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  database_path: Path,
  user_id: str,
  name: str,
) -> None:
  """Add one user through the CLI."""
  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "user",
    "add",
    user_id,
    name,
  )

  assert exit_code == 0
  assert stdout == f"{user_id}\n"
  assert stderr == ""


def add_standard_users(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  database_path: Path,
) -> None:
  """Add the standard users used by record CLI tests."""
  add_user(monkeypatch, capsys, database_path, "alice", "Alice")
  add_user(monkeypatch, capsys, database_path, "bob", "Bob")
  add_user(monkeypatch, capsys, database_path, "carol", "Carol")


def load_json(stdout: str) -> list[dict[str, object]]:
  """Load JSON CLI output."""
  return cast("list[dict[str, object]]", json.loads(stdout))


def test_user_command_requires_initialized_database(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  database_path: Path,
) -> None:
  """Ensure user commands fail clearly before database initialization."""
  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "user",
    "list",
    "--format",
    "json",
  )

  assert exit_code == 1
  assert stdout == ""
  assert "Failed to connect to the database" in stderr


def test_database_init_creates_empty_database(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  database_path: Path,
) -> None:
  """Ensure database init allows subsequent commands to read empty tables."""
  init_database(monkeypatch, capsys, database_path)

  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "user",
    "list",
    "--format",
    "json",
  )

  assert exit_code == 0
  assert load_json(stdout) == []
  assert stderr == ""


def test_user_add_list_deactivate_and_activate(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  database_path: Path,
) -> None:
  """Ensure user lifecycle commands persist and filter users."""
  init_database(monkeypatch, capsys, database_path)
  add_user(monkeypatch, capsys, database_path, "charlie", "Charlie")
  add_user(monkeypatch, capsys, database_path, "alice", "Alice")

  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "user",
    "deactivate",
    "charlie",
  )
  assert exit_code == 0
  assert stdout == "charlie\n"
  assert stderr == ""

  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "user",
    "list",
    "--active",
    "--format",
    "json",
  )
  assert exit_code == 0
  assert load_json(stdout) == [
    {"id": "alice", "name": "Alice", "active": True},
  ]
  assert stderr == ""

  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "user",
    "activate",
    "charlie",
  )
  assert exit_code == 0
  assert stdout == "charlie\n"
  assert stderr == ""

  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "user",
    "list",
    "--format",
    "json",
  )
  assert exit_code == 0
  assert [user["id"] for user in load_json(stdout)] == ["alice", "charlie"]
  assert stderr == ""


def test_user_add_duplicate_reports_error(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  database_path: Path,
) -> None:
  """Ensure duplicate users return a nonzero status and stderr message."""
  init_database(monkeypatch, capsys, database_path)
  add_user(monkeypatch, capsys, database_path, "alice", "Alice")

  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "user",
    "add",
    "alice",
    "Other Alice",
  )

  assert exit_code == 1
  assert stdout == ""
  assert "same ID or name already exists" in stderr


def test_record_add_outputs_split_records_as_json(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  database_path: Path,
) -> None:
  """Ensure record add splits aggregate records and returns created rows."""
  init_database(monkeypatch, capsys, database_path)
  add_standard_users(monkeypatch, capsys, database_path)
  expected_first_record_id = 1
  expected_second_record_id = 2
  expected_split_amount = 50

  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "record",
    "add",
    "--type",
    RecordType.DEBT.value,
    "--lender",
    "alice",
    "--borrower",
    "bob",
    "--borrower",
    "carol",
    "--amount",
    "1.00",
    "--created-by",
    "alice",
    "--remarks",
    "Dinner",
    "--format",
    "json",
  )

  records = load_json(stdout)
  assert exit_code == 0
  assert stderr == ""
  assert [record["id"] for record in records] == [
    expected_first_record_id,
    expected_second_record_id,
  ]
  assert [record["borrower"] for record in records] == ["bob", "carol"]
  assert [record["amount"] for record in records] == [
    expected_split_amount,
    expected_split_amount,
  ]
  assert all(record["remarks"] == "Dinner" for record in records)


def test_record_list_csv_outputs_created_records(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  database_path: Path,
) -> None:
  """Ensure record CSV output includes expected persisted fields."""
  init_database(monkeypatch, capsys, database_path)
  add_standard_users(monkeypatch, capsys, database_path)
  expected_record_id = 1
  run_cli(
    monkeypatch,
    capsys,
    database_path,
    "record",
    "add",
    "--type",
    RecordType.DEBT.value,
    "--lender",
    "alice",
    "--borrower",
    "bob",
    "--amount",
    "1.00",
    "--created-by",
    "alice",
    "--format",
    "json",
  )

  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "record",
    "list",
    "--format",
    "csv",
  )

  rows = list(csv.DictReader(io.StringIO(stdout)))
  assert exit_code == 0
  assert stderr == ""
  assert rows == [
    {
      "id": str(expected_record_id),
      "type": RecordType.DEBT.value,
      "lender": "alice",
      "borrower": "bob",
      "amount": "1.00",
      "created_by": "alice",
      "created_at": rows[0]["created_at"],
      "remarks": "",
      "active": "1",
    },
  ]


def test_record_cancel_and_activate_filter_active_records(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  database_path: Path,
) -> None:
  """Ensure record status commands update active filtering."""
  init_database(monkeypatch, capsys, database_path)
  add_standard_users(monkeypatch, capsys, database_path)
  expected_record_id = 1
  run_cli(
    monkeypatch,
    capsys,
    database_path,
    "record",
    "add",
    "--type",
    RecordType.DEBT.value,
    "--lender",
    "alice",
    "--borrower",
    "bob",
    "--amount",
    "1.00",
    "--created-by",
    "alice",
    "--format",
    "json",
  )

  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "record",
    "cancel",
    "--id",
    str(expected_record_id),
  )
  assert exit_code == 0
  assert stdout == f"{expected_record_id}\n"
  assert stderr == ""

  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "record",
    "list",
    "--active",
    "--format",
    "json",
  )
  assert exit_code == 0
  assert load_json(stdout) == []
  assert stderr == ""

  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "record",
    "activate",
    "--id",
    str(expected_record_id),
  )
  assert exit_code == 0
  assert stdout == f"{expected_record_id}\n"
  assert stderr == ""


def test_record_summary_outputs_settlement_json(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  database_path: Path,
) -> None:
  """Ensure summary command prints settlement transactions."""
  init_database(monkeypatch, capsys, database_path)
  add_standard_users(monkeypatch, capsys, database_path)
  expected_bob_summary_amount = 60
  expected_carol_summary_amount = 40
  run_cli(
    monkeypatch,
    capsys,
    database_path,
    "record",
    "add",
    "--type",
    RecordType.DEBT.value,
    "--lender",
    "alice",
    "--borrower",
    "bob",
    "--amount",
    "1.00",
    "--created-by",
    "alice",
    "--format",
    "json",
  )
  run_cli(
    monkeypatch,
    capsys,
    database_path,
    "record",
    "add",
    "--type",
    RecordType.DEBT.value,
    "--lender",
    "bob",
    "--borrower",
    "carol",
    "--amount",
    "0.40",
    "--created-by",
    "bob",
    "--format",
    "json",
  )

  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "record",
    "summary",
    "--format",
    "json",
  )

  assert exit_code == 0
  assert load_json(stdout) == [
    {"from": "bob", "to": "alice", "amount": expected_bob_summary_amount},
    {
      "from": "carol",
      "to": "alice",
      "amount": expected_carol_summary_amount,
    },
  ]
  assert stderr == ""


def test_record_add_unknown_user_reports_constraint_error(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  database_path: Path,
) -> None:
  """Ensure record add surfaces database constraint failures."""
  init_database(monkeypatch, capsys, database_path)
  add_user(monkeypatch, capsys, database_path, "alice", "Alice")

  exit_code, stdout, stderr = run_cli(
    monkeypatch,
    capsys,
    database_path,
    "record",
    "add",
    "--type",
    RecordType.DEBT.value,
    "--lender",
    "alice",
    "--borrower",
    "missing",
    "--amount",
    "1.00",
    "--created-by",
    "alice",
  )

  assert exit_code == 1
  assert stdout == ""
  assert "constraint violation" in stderr


def test_print_table_pads_columns(capsys: pytest.CaptureFixture[str]) -> None:
  """Ensure table printing pads rows to the widest cell in each column."""
  cli.print_table(
    ["ID", "NAME"],
    [
      ["a", "Alice"],
      ["charlie", "Charlie"],
    ],
  )

  captured = capsys.readouterr()
  assert captured.out.splitlines() == [
    "ID       NAME   ",
    "----------------",
    "a        Alice  ",
    "charlie  Charlie",
  ]
