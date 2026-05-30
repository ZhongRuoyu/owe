from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class User:
  """A user in the IOU system."""

  name: str
  active: bool = True

  @staticmethod
  def from_db_row(row: dict[str, Any]) -> User:
    return User(
      name=row["name"],
      active=bool(row["active"]),
    )

  def asdict(self) -> dict[str, Any]:
    return {
      "name": self.name,
      "active": self.active,
    }
