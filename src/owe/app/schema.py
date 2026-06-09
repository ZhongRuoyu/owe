import datetime as dt
from typing import Annotated, Any, TypeVar

from pydantic import (
  BaseModel,
  Field,
  StrictBool,
  StrictInt,
  StrictStr,
  ValidationError,
)

from owe import Record as OweRecord
from owe import RecordType
from owe import SummaryTransaction as OweSummaryTransaction
from owe import User as OweUser

ModelT = TypeVar("ModelT", bound=BaseModel)


class User(BaseModel):
  """A user in the Owe system."""

  id: str
  name: str
  active: bool

  @staticmethod
  def from_owe_user(user: OweUser) -> "User":
    """Create an API user model from an Owe user."""
    return User(
      id=user.id,
      name=user.name,
      active=user.active,
    )


class Record(BaseModel):
  """A record in the Owe system."""

  id: int | None
  type: RecordType
  lender: str
  borrower: str
  amount: int
  created_by: str
  created_at: dt.datetime
  remarks: str | None
  active: bool

  @staticmethod
  def from_owe_record(record: OweRecord) -> "Record":
    """Create an API record model from an Owe record."""
    return Record(
      id=record.id,
      type=record.type,
      lender=record.lender,
      borrower=record.borrower,
      amount=record.amount,
      created_by=record.created_by,
      created_at=record.created_at,
      remarks=record.remarks,
      active=record.active,
    )


class SummaryTransaction(BaseModel):
  """A transaction in the summary response."""

  from_user: str = Field(..., serialization_alias="from")
  to_user: str = Field(..., serialization_alias="to")
  amount: int

  @staticmethod
  def from_owe_summary_transaction(
    transaction: OweSummaryTransaction,
  ) -> "SummaryTransaction":
    """
    Create an API summary transaction model from an Owe summary transaction.
    """
    return SummaryTransaction(
      from_user=transaction.from_user,
      to_user=transaction.to_user,
      amount=transaction.amount,
    )


class AppConfig(BaseModel):
  """Subset of app config values to expose via the API."""

  currency: str


class ErrorResponse(BaseModel):
  """Generic error response model."""

  success: bool = False
  error: str


class GetConfigResponse(AppConfig):
  """Response for fetching app config values."""


class GetUsersResponse(BaseModel):
  """Response for fetching active users."""

  success: bool
  users: list[User]


class GetRecordsResponse(BaseModel):
  """Response for fetching records."""

  success: bool
  records: list[Record]


class AddRecordsRequest(BaseModel):
  """Request for creating records from an aggregated record."""

  type: RecordType
  lender: StrictStr
  borrowers: Annotated[list[StrictStr], Field(min_length=1)]
  amount: Annotated[StrictInt, Field(gt=0)]
  remarks: StrictStr | None


class AddRecordsResponse(BaseModel):
  """Response for creating records from an aggregated record."""

  success: bool
  records: list[Record]


class SetRecordsActiveRequest(BaseModel):
  """Request for batch record-status updates."""

  ids: Annotated[list[StrictInt], Field(min_length=1)]
  active: StrictBool


class SetRecordsActiveResponse(BaseModel):
  """Response for batch record-status updates."""

  success: bool


class GetSummaryResponse(BaseModel):
  """Response for fetching summary data."""

  success: bool
  summary: list[SummaryTransaction]


def parse(
  request: dict[str, Any],
  model: type[ModelT],
) -> tuple[ModelT | None, str | None]:
  """Parse and validate a JSON request body with a Pydantic model."""
  try:
    return model.model_validate(request), None
  except ValidationError as error:
    return None, _validation_error_message(error)


def _validation_error_message(error: ValidationError) -> str:
  """Return a short human-readable message for a Pydantic error."""
  first_error = error.errors()[0]
  field = ".".join(str(item) for item in first_error["loc"])
  message = str(first_error["msg"])
  if not field:
    return message
  return f"Invalid {field}: {message}"
