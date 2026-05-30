#!/usr/bin/env python3

import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import iou.database as db
from iou.config import DATABASE
from iou.record import Record

RECORDS = os.getenv("RECORDS", "records.csv")


def dump_records(records: list[Record], output: Path) -> None:
  with output.open("w", encoding="utf-8", newline="") as csv_file:
    writer = csv.writer(csv_file)
    writer.writerow(Record.csv_header())
    for record in records:
      writer.writerow(record.to_csv_row())


def main() -> int:
  database = Path(DATABASE)
  output = Path(RECORDS)

  if not database.exists():
    print(f"Error: Database file {DATABASE} not found")
    return 1

  records = db.get_records(database)
  dump_records(records, output)
  print(f"Successfully dumped {len(records)} records to {output}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
