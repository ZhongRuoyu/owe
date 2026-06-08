import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from .money import CENTS_PER_UNIT, amount_to_cents


class RecordType(str, Enum):
  DEBT = "DEBT"
  PAYMENT = "PAYMENT"


@dataclass(slots=True)
class Record:
  """A record representing a single transaction between two users."""

  type: RecordType
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
    """Return values matching the records insert statement order."""
    return (
      self.type.value,
      self.lender,
      self.borrower,
      self.amount,
      self.created_by,
      int(self.created_at.timestamp() * 1000),
      self.remarks,
      self.active,
    )

  @staticmethod
  def from_database_row(row: dict[str, Any]) -> "Record":
    """Create a ``Record`` from a database row mapping."""
    created_at = dt.datetime.fromtimestamp(
      row["created_at"] / 1000, tz=dt.timezone.utc
    )
    return Record(
      id=row["id"],
      type=RecordType(row["type"]),
      lender=row["lender"],
      borrower=row["borrower"],
      amount=row["amount"],
      created_by=row["created_by"],
      created_at=created_at,
      remarks=row["remarks"],
      active=bool(row["active"]),
    )

  @staticmethod
  def csv_header() -> tuple[str, str, str, str, str, str, str, str, str]:
    """Return the CSV header used for record export."""
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
  def from_csv_row(row: list[str]) -> "Record":
    """Create a ``Record`` from a CSV row."""
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
      type=RecordType(record_type),
      lender=lender,
      borrower=borrower,
      amount=amount_to_cents(amount),
      created_by=created_by,
      created_at=dt.datetime.fromisoformat(created_at),
      remarks=remarks,
      active=bool(int(active)),
    )

  def to_csv_row(self) -> tuple[int, str, str, str, str, str, str, str, int]:
    """Return values matching the ``csv_header`` CSV export order."""
    return (
      self.id or 0,
      self.type.value,
      self.lender,
      self.borrower,
      f"{Decimal(self.amount) / CENTS_PER_UNIT:.2f}",
      self.created_by,
      self.created_at.isoformat(timespec="milliseconds"),
      self.remarks or "",
      int(self.active),
    )

  def to_dict(self) -> dict[str, Any]:
    """Return a JSON-serializable representation of the record."""
    return {
      "id": self.id,
      "type": self.type.value,
      "lender": self.lender,
      "borrower": self.borrower,
      "amount": self.amount,
      "created_by": self.created_by,
      "created_at": int(self.created_at.timestamp() * 1000),
      "remarks": self.remarks,
      "active": self.active,
    }


@dataclass(slots=True)
class AggregatedRecord:
  """
  An aggregated record representing a single transaction that involves possibly
  multiple users.
  """

  type: RecordType
  lender: str
  borrowers: list[str]
  amount: int
  created_by: str
  remarks: str | None

  def to_records(self) -> list[Record]:
    """Split an aggregated record into per-borrower ``Record`` entries."""
    each_amount = self._ceildiv(self.amount, len(self.borrowers))
    created_at = dt.datetime.now(tz=dt.timezone.utc)
    return [
      Record(
        type=self.type,
        lender=self.lender,
        borrower=borrower,
        amount=each_amount,
        created_by=self.created_by,
        created_at=created_at,
        remarks=self.remarks,
      )
      for borrower in self.borrowers
      if borrower != self.lender
    ]

  @staticmethod
  def _ceildiv(a: int, b: int) -> int:
    """Divide ``a`` by ``b`` and round up."""
    return int(-(a // -b))
