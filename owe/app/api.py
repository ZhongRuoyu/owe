import logging
from html import escape

from fastapi import (
  BackgroundTasks,
  FastAPI,
  Request,
  Response,
  status,
)
from fastapi.responses import JSONResponse

from owe import AggregatedRecord, DatabaseError, Owe, RecordType, SqliteDatabase

from .config import Config
from .schema import (
  AddRecordsRequest,
  AddRecordsResponse,
  ErrorResponse,
  GetConfigResponse,
  GetRecordsResponse,
  GetSummaryResponse,
  GetUsersResponse,
  Record,
  SetRecordsActiveRequest,
  SetRecordsActiveResponse,
  SummaryTransaction,
  User,
)
from .telegram_announcer import TelegramAnnouncer

CONFIG_STATE_KEY = "config"
OWE_SERVICE_STATE_KEY = "owe_service"
TELEGRAM_ANNOUNCER_STATE_KEY = "telegram_announcer"

logger = logging.getLogger(__name__)


class AppServiceTypeError(TypeError):
  """Raised when an app-level service has an unexpected type."""


class APIError(Exception):
  """Raised for expected API errors with a specific HTTP status code."""

  status_code: int
  message: str

  def __init__(
    self,
    message: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
  ) -> None:
    super().__init__(message)
    self.message = message
    self.status_code = status_code


class APIDatabaseError(APIError):
  """Raised for expected API errors caused by database issues."""

  def __init__(self, message: str = "Database error") -> None:
    super().__init__(message, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _app_config(request: Request) -> Config:
  """Return the config for the current app instance."""
  config = getattr(request.app.state, CONFIG_STATE_KEY, None)
  if not isinstance(config, Config):
    raise AppServiceTypeError
  return config


def _app_owe(request: Request) -> Owe:
  """Return the Owe service bound to the current app instance."""
  owe_service = getattr(request.app.state, OWE_SERVICE_STATE_KEY, None)
  if not isinstance(owe_service, Owe):
    raise AppServiceTypeError
  return owe_service


def _app_telegram_announcer(request: Request) -> TelegramAnnouncer | None:
  """Return app-level Telegram announcer, or ``None`` when disabled."""
  announcer = getattr(request.app.state, TELEGRAM_ANNOUNCER_STATE_KEY, None)
  if announcer is None:
    return None
  if not isinstance(announcer, TelegramAnnouncer):
    raise AppServiceTypeError
  return announcer


def _get_requester(request: Request) -> str:
  """Return requester identity from configured header or remote address."""
  config = _app_config(request)

  request_email_header = config.request_email_header
  if request_email_header:
    email = request.headers.get(request_email_header)
    if email:
      return email

  trust_proxy = config.trust_proxy
  if trust_proxy:
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for and (ip := x_forwarded_for.split(",")[0].strip()):
      return ip

  if request.client and request.client.host:
    return request.client.host

  return "unknown"


def init(app: FastAPI, config: Config) -> None:
  """Initialize logging, schema, and API-level services."""
  setattr(app.state, CONFIG_STATE_KEY, config)

  database = SqliteDatabase(config.database_path, create=True)
  database.init()
  owe_service = Owe(database, logger=logger)
  setattr(app.state, OWE_SERVICE_STATE_KEY, owe_service)

  bot_token = config.telegram_bot_token
  chat_id = config.telegram_chat_id
  if bot_token and chat_id:
    telegram_announcer = TelegramAnnouncer(
      bot_token=bot_token,
      chat_id=chat_id,
      currency=config.currency,
    )
  else:
    telegram_announcer = None
  setattr(app.state, TELEGRAM_ANNOUNCER_STATE_KEY, telegram_announcer)


api = FastAPI(
  docs_url=None,
  redoc_url=None,
  openapi_url=None,
)


@api.exception_handler(APIError)
async def api_error_handler(_request: Request, error: APIError) -> Response:
  """
  Handle expected API errors by returning the specified status code and message.
  """
  print(f"API error: {error.message} (status code: {error.status_code})")
  return JSONResponse(
    status_code=error.status_code,
    content=ErrorResponse(message=error.message).model_dump(),
  )


@api.get("/config")
async def get_config(request: Request) -> GetConfigResponse:
  """Return client-facing configuration values."""
  return GetConfigResponse(
    currency=_app_config(request).currency,
  )


@api.get("/users")
async def get_users(request: Request) -> GetUsersResponse:
  """Return active users."""
  try:
    users = _app_owe(request).get_users(active_only=True)
  except DatabaseError:
    logger.exception("Database error in get_users")
    raise APIDatabaseError from None
  return GetUsersResponse(
    success=True,
    users=[User.from_owe_user(user) for user in users],
  )


@api.get("/records")
async def get_records(request: Request) -> GetRecordsResponse:
  """Return all records."""
  try:
    records = _app_owe(request).get_records()
  except DatabaseError:
    logger.exception("Database error in get_records")
    raise APIDatabaseError from None
  return GetRecordsResponse(
    success=True,
    records=[Record.from_owe_record(record) for record in records],
  )


def _validate_add_records_request(
  req: AddRecordsRequest,
  valid_emails: set[str],
) -> str | None:
  """Validate add-record user references after model validation."""
  lender = req.lender
  borrowers = req.borrowers

  if lender not in valid_emails:
    return f"Unknown lender: {escape(lender)}"

  if unknown_borrowers := set(borrowers) - valid_emails:
    borrowers_str = escape(
      ", ".join(email for email in unknown_borrowers),
    )
    return f"Unknown borrower(s): {borrowers_str}"

  return None


@api.post("/records")
async def add_records(
  request: Request,
  body: AddRecordsRequest,
  background_tasks: BackgroundTasks,
) -> AddRecordsResponse:
  """Create an aggregated record and persist its split entries."""
  owe_service = _app_owe(request)
  try:
    users = owe_service.get_users(active_only=True)
  except DatabaseError:
    logger.exception("Database error in add_records")
    raise APIDatabaseError from None

  valid_emails = {user.email for user in users}
  error = _validate_add_records_request(body, valid_emails)
  if error is not None:
    raise APIError(error, status.HTTP_400_BAD_REQUEST) from None

  record = AggregatedRecord(
    type=RecordType(body.type),
    lender=body.lender,
    borrowers=body.borrowers,
    amount=body.amount,
    created_by=_get_requester(request),
    remarks=body.remarks,
  )
  try:
    records = owe_service.add_records(record)
  except DatabaseError:
    logger.exception("Database error in add_records")
    raise APIDatabaseError from None

  announcer = _app_telegram_announcer(request)
  if announcer:
    background_tasks.add_task(announcer.announce_records, records, users)

  return AddRecordsResponse(
    success=True,
    records=[Record.from_owe_record(record) for record in records],
  )


@api.patch("/records/status")
async def set_records_active(
  request: Request,
  body: SetRecordsActiveRequest,
  background_tasks: BackgroundTasks,
) -> SetRecordsActiveResponse:
  """Update the active flag for a batch of records."""
  owe_service = _app_owe(request)
  try:
    owe_service.set_records_active(body.ids, active=body.active)
  except DatabaseError:
    logger.exception("Database error in set_records_active")
    raise APIDatabaseError from None

  announcer = _app_telegram_announcer(request)
  if announcer:
    try:
      records = owe_service.get_records_by_ids(body.ids)
      users = owe_service.get_users()
    except DatabaseError:
      logger.exception("Database error in set_records_active")
      raise APIDatabaseError from None

    requester = _get_requester(request)
    background_tasks.add_task(
      announcer.announce_record_status_change,
      records,
      users,
      requester,
      active=body.active,
    )

  return SetRecordsActiveResponse(success=True)


@api.get("/summary")
async def get_summary(request: Request) -> GetSummaryResponse:
  """Return settlement transactions computed from net balances."""
  try:
    result = _app_owe(request).get_summary()
  except DatabaseError:
    logger.exception("Database error in get_summary")
    raise APIDatabaseError from None
  return GetSummaryResponse(
    success=True,
    summary=[
      SummaryTransaction.from_owe_summary_transaction(transaction)
      for transaction in result
    ],
  )
