#!/usr/bin/env python3

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import iou.database as db
from iou.record import Record


def dump_records(records: list[Record], output: Path) -> None:
  with output.open("w", encoding="utf-8", newline="") as csv_file:
    writer = csv.writer(csv_file)
    writer.writerow(Record.csv_header())
    for record in records:
      writer.writerow(record.to_csv_row())


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    prog="iou-dump",
    description="Dump records from the IOU database as CSV.",
  )
  parser.add_argument(
    "--database",
    type=Path,
    default=Path("iou.db"),
    help="path to the SQLite database file (default: iou.db)",
  )
  parser.add_argument(
    "--output",
    type=Path,
    default=Path("records.csv"),
    help="path to output CSV file (default: records.csv)",
  )
  return parser


def main() -> int:
  parser = build_parser()
  args = parser.parse_args()

  database = args.database
  output = args.output

  if not database.exists():
    print(f"Error: Database file {database} not found")
    return 1

  records = db.get_records(database)
  dump_records(records, output)
  print(f"Successfully dumped {len(records)} records to {output}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
