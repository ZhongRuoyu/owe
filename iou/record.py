import datetime as dt
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Record:
  """A record of an IOU transaction."""

  type: str
  lender: str
  borrower: str
  amount: int
  created_by: str
  created_at: dt.datetime
  remarks: str | None = None
  active: bool = True
  id: int | None = None

  def to_insert_values(
    self,
  ) -> tuple[str, str, str, int, str, int, str | None, bool]:
    return (
      self.type,
      self.lender,
      self.borrower,
      self.amount,
      self.created_by,
      int(self.created_at.timestamp() * 1000),
      self.remarks,
      self.active,
    )

  @staticmethod
  def from_db_row(row: dict[str, Any]) -> Record:
    return Record(
      id=row["id"],
      type=row["type"],
      lender=row["lender"],
      borrower=row["borrower"],
      amount=row["amount"],
      created_by=row["created_by"],
      created_at=dt.datetime.fromtimestamp(row["created_at"] / 1000, tz=dt.UTC),
      remarks=row["remarks"],
      active=bool(row["active"]),
    )

  @staticmethod
  def csv_header() -> tuple[str, str, str, str, str, str, str, str, str]:
    return (
      "id",
      "type",
      "lender",
      "borrower",
      "amount",
      "created_by",
      "created_at",
      "remarks",
      "active",
    )

  @staticmethod
  def from_csv_row(row: list[str]) -> Record:
    (
      record_id,
      record_type,
      lender,
      borrower,
      amount,
      created_by,
      created_at,
      remarks,
      active,
    ) = row
    return Record(
      id=int(record_id),
      type=record_type,
      lender=lender,
      borrower=borrower,
      amount=int(float(amount) * 100),
      created_by=created_by,
      created_at=dt.datetime.fromisoformat(created_at),
      remarks=remarks,
      active=bool(int(active)),
    )

  def to_csv_row(self) -> tuple[int, str, str, str, str, str, str, str, int]:
    return (
      self.id or 0,
      self.type,
      self.lender,
      self.borrower,
      f"{self.amount / 100:.2f}",
      self.created_by,
      self.created_at.isoformat(timespec="milliseconds"),
      self.remarks or "",
      int(self.active),
    )

  def asdict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "type": self.type,
      "lender": self.lender,
      "borrower": self.borrower,
      "amount": self.amount,
      "created_by": self.created_by,
      "created_at": int(self.created_at.timestamp() * 1000),
      "remarks": self.remarks,
      "active": self.active,
    }
