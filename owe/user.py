from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class User:
  """A user in the Owe system."""

  email: str
  name: str
  active: bool = True

  def to_insert_values(
    self,
  ) -> tuple[str, str, bool]:
    """Return values matching the users insert statement order."""
    return (
      self.email,
      self.name,
      self.active,
    )

  @staticmethod
  def from_database_row(row: dict[str, Any]) -> "User":
    """Create a ``User`` from a database row mapping."""
    return User(
      email=row["email"],
      name=row["name"],
      active=bool(row["active"]),
    )

  def to_dict(self) -> dict[str, Any]:
    """Return a JSON-serializable representation of the user."""
    return {
      "email": self.email,
      "name": self.name,
      "active": self.active,
    }
