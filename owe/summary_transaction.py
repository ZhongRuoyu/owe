from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SummaryTransaction:
  from_user: str
  to_user: str
  amount: int

  def to_dict(self) -> dict[str, Any]:
    """Return a JSON-serializable representation of the summary transaction."""
    return {
      "from": self.from_user,
      "to": self.to_user,
      "amount": self.amount,
    }
