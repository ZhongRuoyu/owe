from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class User:
  """A user in the IOU system."""

  email: str
  name: str
  active: bool = True

  @staticmethod
  def from_db_row(row: dict[str, Any]) -> User:
    return User(
      email=row["email"],
      name=row["name"],
      active=bool(row["active"]),
    )

  def asdict(self) -> dict[str, Any]:
    return {
      "email": self.email,
      "name": self.name,
      "active": self.active,
    }
