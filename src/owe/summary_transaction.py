from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SummaryTransaction:
  from_user: str
  to_user: str
  amount: int

  @staticmethod
  def csv_header() -> tuple[str, str, str]:
    """Return the CSV header used for summary transaction export."""
    return (
      "from",
      "to",
      "amount",
    )

  @staticmethod
  def from_csv_row(row: list[str]) -> "SummaryTransaction":
    """Create a ``SummaryTransaction`` from a CSV row."""
    from_user, to_user, amount = row
    return SummaryTransaction(
      from_user=from_user,
      to_user=to_user,
      amount=int(amount),
    )

  def to_csv_row(self) -> tuple[str, str, int]:
    """Return values matching the ``csv_header`` CSV export order."""
    return (
      self.from_user,
      self.to_user,
      self.amount,
    )

  def to_dict(self) -> dict[str, Any]:
    """Return a JSON-serializable representation of the summary transaction."""
    return {
      "from": self.from_user,
      "to": self.to_user,
      "amount": self.amount,
    }
