from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class User:
  """A user in the Owe system."""

  id: str
  name: str
  active: bool = True

  def to_insert_values(
    self,
  ) -> tuple[str, str, bool]:
    """Return values matching the users insert statement order."""
    return (
      self.id,
      self.name,
      self.active,
    )

  @staticmethod
  def from_database_row(row: dict[str, Any]) -> "User":
    """Create a ``User`` from a database row mapping."""
    return User(
      id=row["id"],
      name=row["name"],
      active=bool(row["active"]),
    )

  @staticmethod
  def csv_header() -> tuple[str, str, str]:
    """Return the CSV header used for user export."""
    return (
      "id",
      "name",
      "active",
    )

  @staticmethod
  def from_csv_row(row: list[str]) -> "User":
    """Create a ``User`` from a CSV row."""
    user_id, name, active = row
    return User(id=user_id, name=name, active=bool(int(active)))

  def to_csv_row(self) -> tuple[str, str, int]:
    """Return values matching the ``csv_header`` CSV export order."""
    return (
      self.id,
      self.name,
      int(self.active),
    )

  def to_dict(self) -> dict[str, Any]:
    """Return a JSON-serializable representation of the user."""
    return {
      "id": self.id,
      "name": self.name,
      "active": self.active,
    }
