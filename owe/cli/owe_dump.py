#!/usr/bin/env python3

import argparse
import csv
import sys
from pathlib import Path

from owe.database import Database
from owe.record import Record


def dump_records(records: list[Record], output: Path) -> None:
  """Write records to a CSV file at the given output path."""
  with output.open("w", encoding="utf-8", newline="") as csv_file:
    writer = csv.writer(csv_file)
    writer.writerow(Record.csv_header())
    for record in records:
      writer.writerow(record.to_csv_row())


def build_parser() -> argparse.ArgumentParser:
  """Build the command-line parser for ``owe-dump``."""
  parser = argparse.ArgumentParser(
    prog="owe-dump",
    description="Dump records from the Owe database as CSV.",
  )
  parser.add_argument(
    "--database",
    type=Path,
    default=Path("owe.db"),
    help="path to the SQLite database file (default: owe.db)",
  )
  parser.add_argument(
    "--output",
    type=Path,
    default=Path("records.csv"),
    help="path to output CSV file (default: records.csv)",
  )
  return parser


def main() -> int:
  """Run the ``owe-dump`` command-line entry point."""
  parser = build_parser()
  args = parser.parse_args()

  database = Database(args.database, create=False)
  output = args.output

  records = database.get_records()
  dump_records(records, output)
  print(f"Successfully dumped {len(records)} records to {output}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
