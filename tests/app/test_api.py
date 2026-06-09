import asyncio
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import status

import owe.app.api as api_module
from owe import (
  DatabaseError,
  Owe,
  Record,
  RecordType,
  SqliteDatabase,
  User,
)
from owe.app.config import Config
from owe.app.telegram_announcer import TelegramAnnouncer

BASE_URL = "http://testserver"
DEFAULT_CLIENT = ("127.0.0.1", 123)
MISSING_RECORD_ID = 999


@dataclass(slots=True)
class APIHarness:
  """Services bound to the API app for one test."""

  database: SqliteDatabase
  owe_service: Owe


class SpyTelegramAnnouncer(TelegramAnnouncer):
  """Telegram announcer test double that records scheduled calls."""

  record_announcements: list[tuple[list[Record], list[User]]]
  status_announcements: list[tuple[list[Record], list[User], str, bool]]

  def __init__(self) -> None:
    self.record_announcements = []
    self.status_announcements = []

  async def announce_records(
    self,
    records: list[Record],
    users: list[User],
  ) -> None:
    """Record new-record announcements instead of posting to Telegram."""
    self.record_announcements.append((records, users))

  async def announce_record_status_change(
    self,
    records: list[Record],
    users: list[User],
    requester: str,
    *,
    active: bool,
  ) -> None:
    """Record status-change announcements instead of posting to Telegram."""
    self.status_announcements.append((records, users, requester, active))


def configure_api(
  database_path: Path,
  *,
  currency: str = "USD",
  request_id_header: str | None = None,
  trust_proxy: bool = False,
  announcer: TelegramAnnouncer | None = None,
) -> APIHarness:
  """Configure the API app with a fresh test database."""
  database = SqliteDatabase(database_path, create=True)
  database.init()
  database.add_user(User(id="alice", name="Alice"))
  database.add_user(User(id="bob", name="Bob"))
  database.add_user(User(id="carol", name="Carol"))
  database.add_user(User(id="dave", name="Dave", active=False))

  config = Config(
    url_prefix="",
    api_only=False,
    log_level="INFO",
    database_path=database_path,
    currency=currency,
    request_id_header=request_id_header,
    trust_proxy=trust_proxy,
    telegram_bot_token=None,
    telegram_chat_id=None,
  )
  owe_service = Owe(database)
  setattr(api_module.api.state, api_module.CONFIG_STATE_KEY, config)
  setattr(api_module.api.state, api_module.OWE_SERVICE_STATE_KEY, owe_service)
  setattr(
    api_module.api.state, api_module.TELEGRAM_ANNOUNCER_STATE_KEY, announcer
  )
  return APIHarness(database=database, owe_service=owe_service)


async def async_request(
  method: str,
  path: str,
  *,
  json_body: dict[str, Any] | None = None,
  headers: dict[str, str] | None = None,
  client: tuple[str, int] = DEFAULT_CLIENT,
) -> httpx.Response:
  """Send a request to the API ASGI app."""
  transport = httpx.ASGITransport(app=api_module.api, client=client)
  async with httpx.AsyncClient(
    transport=transport,
    base_url=BASE_URL,
  ) as async_client:
    return await async_client.request(
      method,
      path,
      json=json_body,
      headers=headers,
    )


def request(
  method: str,
  path: str,
  *,
  json_body: dict[str, Any] | None = None,
  headers: dict[str, str] | None = None,
  client: tuple[str, int] = DEFAULT_CLIENT,
) -> httpx.Response:
  """Send a synchronous test request to the API app."""
  return asyncio.run(
    async_request(
      method,
      path,
      json_body=json_body,
      headers=headers,
      client=client,
    )
  )


def record_body(
  *,
  lender: str = "alice",
  borrowers: list[str] | None = None,
  amount: int = 100,
) -> dict[str, Any]:
  """Return a valid add-record request body with overridable fields."""
  return {
    "type": RecordType.DEBT.value,
    "lender": lender,
    "borrowers": borrowers or ["bob"],
    "amount": amount,
    "remarks": "Dinner",
  }


def make_record(
  *,
  lender: str = "alice",
  borrower: str = "bob",
  amount: int = 100,
  active: bool = True,
) -> Record:
  """Create a deterministic record for API tests."""
  return Record(
    type=RecordType.DEBT,
    lender=lender,
    borrower=borrower,
    amount=amount,
    created_by="alice",
    created_at=dt.datetime(2026, 6, 8, 12, 30, tzinfo=dt.timezone.utc),
    remarks=None,
    active=active,
  )


def response_body(response: httpx.Response) -> dict[str, object]:
  """Return a JSON response body with a precise static type."""
  return cast("dict[str, object]", response.json())


def test_get_config_returns_client_config(database_path: Path) -> None:
  """Ensure the config endpoint returns client-facing settings."""
  configure_api(database_path, currency="SGD")

  response = request("GET", "/config")

  assert response.status_code == status.HTTP_200_OK
  assert response_body(response) == {"currency": "SGD"}


def test_get_users_returns_active_users_only(database_path: Path) -> None:
  """Ensure inactive users are hidden from API user lookup."""
  configure_api(database_path)

  response = request("GET", "/users")

  body = response_body(response)
  assert response.status_code == status.HTTP_200_OK
  assert body["success"] is True
  assert body["users"] == [
    {"id": "alice", "name": "Alice", "active": True},
    {"id": "bob", "name": "Bob", "active": True},
    {"id": "carol", "name": "Carol", "active": True},
  ]


def test_get_records_returns_active_and_inactive_records(
  database_path: Path,
) -> None:
  """Ensure record lookup returns the complete audit trail."""
  harness = configure_api(database_path)
  records = [
    make_record(active=True),
    make_record(lender="bob", borrower="carol", amount=40, active=False),
  ]
  harness.database.add_records(records)

  response = request("GET", "/records")

  body = response_body(response)
  response_records = cast("list[dict[str, object]]", body["records"])
  assert response.status_code == status.HTTP_200_OK
  assert body["success"] is True
  assert [record["id"] for record in response_records] == [1, 2]
  assert [record["active"] for record in response_records] == [True, False]
  assert [record["amount"] for record in response_records] == [100, 40]


def test_add_records_creates_split_records_with_request_header_identity(
  database_path: Path,
) -> None:
  """Ensure record creation validates users, splits, and stores creator."""
  configure_api(database_path, request_id_header="X-Owe-User")

  response = request(
    "POST",
    "/records",
    json_body=record_body(
      borrowers=["alice", "bob", "carol"],
      amount=101,
    ),
    headers={"X-Owe-User": "creator@example.com"},
  )

  body = response_body(response)
  response_records = cast("list[dict[str, object]]", body["records"])
  assert response.status_code == status.HTTP_200_OK
  assert body["success"] is True
  assert [record["borrower"] for record in response_records] == [
    "bob",
    "carol",
  ]
  assert [record["amount"] for record in response_records] == [34, 34]
  assert {record["created_by"] for record in response_records} == {
    "creator@example.com"
  }


def test_add_records_uses_trusted_proxy_ip_when_configured(
  database_path: Path,
) -> None:
  """Ensure requester identity can come from the first forwarded IP."""
  configure_api(database_path, trust_proxy=True)

  response = request(
    "POST",
    "/records",
    json_body=record_body(),
    headers={"X-Forwarded-For": "198.51.100.7, 10.0.0.1"},
  )

  body = response_body(response)
  response_records = cast("list[dict[str, object]]", body["records"])
  assert response.status_code == status.HTTP_200_OK
  assert response_records[0]["created_by"] == "198.51.100.7"


def test_add_records_falls_back_to_remote_address(
  database_path: Path,
) -> None:
  """Ensure requester identity falls back to the ASGI client host."""
  configure_api(database_path)

  response = request(
    "POST",
    "/records",
    json_body=record_body(),
    client=("203.0.113.9", 456),
  )

  body = response_body(response)
  response_records = cast("list[dict[str, object]]", body["records"])
  assert response.status_code == status.HTTP_200_OK
  assert response_records[0]["created_by"] == "203.0.113.9"


def test_add_records_rejects_unknown_lender(database_path: Path) -> None:
  """Ensure records cannot be created for an unknown lender."""
  configure_api(database_path)

  response = request(
    "POST",
    "/records",
    json_body=record_body(lender="missing"),
  )

  assert response.status_code == status.HTTP_400_BAD_REQUEST
  assert response_body(response) == {
    "success": False,
    "error": "Unknown lender: missing",
  }


def test_add_records_rejects_inactive_borrower(database_path: Path) -> None:
  """Ensure inactive users are rejected as add-record participants."""
  configure_api(database_path)

  response = request(
    "POST",
    "/records",
    json_body=record_body(borrowers=["dave"]),
  )

  assert response.status_code == status.HTTP_400_BAD_REQUEST
  assert response_body(response) == {
    "success": False,
    "error": "Unknown borrower(s): dave",
  }


def test_add_records_rejects_duplicate_borrowers(
  database_path: Path,
) -> None:
  """Ensure duplicate borrower IDs return a client error."""
  configure_api(database_path)

  response = request(
    "POST",
    "/records",
    json_body=record_body(borrowers=["bob", "bob"]),
  )

  assert response.status_code == status.HTTP_400_BAD_REQUEST
  assert response_body(response) == {
    "success": False,
    "error": "Borrowers must be unique",
  }


def test_add_records_rejects_lender_only_borrowers(
  database_path: Path,
) -> None:
  """Ensure borrower lists that produce no records return a client error."""
  configure_api(database_path)

  response = request(
    "POST",
    "/records",
    json_body=record_body(borrowers=["alice"]),
  )

  assert response.status_code == status.HTTP_400_BAD_REQUEST
  assert response_body(response) == {
    "success": False,
    "error": "At least one borrower must differ from the lender",
  }


def test_add_records_rejects_invalid_schema(database_path: Path) -> None:
  """Ensure FastAPI rejects malformed add-record payloads before handling."""
  configure_api(database_path)

  response = request(
    "POST",
    "/records",
    json_body={
      "type": RecordType.DEBT.value,
      "lender": "alice",
      "borrowers": ["bob"],
      "amount": "100",
      "remarks": None,
    },
  )

  assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_add_records_announces_created_records(database_path: Path) -> None:
  """Ensure configured Telegram announcements receive created records."""
  announcer = SpyTelegramAnnouncer()
  configure_api(database_path, announcer=announcer)

  response = request(
    "POST",
    "/records",
    json_body=record_body(borrowers=["bob", "carol"]),
  )

  assert response.status_code == status.HTTP_200_OK
  assert len(announcer.record_announcements) == 1
  records, users = announcer.record_announcements[0]
  assert [record.borrower for record in records] == ["bob", "carol"]
  assert [user.id for user in users] == ["alice", "bob", "carol"]


def test_set_records_active_updates_existing_records(
  database_path: Path,
) -> None:
  """Ensure status updates apply to existing record IDs."""
  harness = configure_api(database_path)
  harness.database.add_records([make_record(), make_record(amount=40)])

  response = request(
    "PATCH",
    "/records/status",
    json_body={
      "ids": [1, 2],
      "active": False,
    },
  )

  assert response.status_code == status.HTTP_200_OK
  assert response_body(response) == {"success": True}
  assert [record.active for record in harness.database.get_records()] == [
    False,
    False,
  ]


def test_set_records_active_rejects_missing_ids_and_rolls_back(
  database_path: Path,
) -> None:
  """Ensure missing record IDs return 404 and do not partially update."""
  harness = configure_api(database_path)
  harness.database.add_records([make_record()])

  response = request(
    "PATCH",
    "/records/status",
    json_body={
      "ids": [1, MISSING_RECORD_ID],
      "active": False,
    },
  )

  assert response.status_code == status.HTTP_404_NOT_FOUND
  assert response_body(response) == {
    "success": False,
    "error": "One or more records were not found",
  }
  assert harness.database.get_records()[0].active is True


def test_set_records_active_rejects_invalid_schema(
  database_path: Path,
) -> None:
  """Ensure FastAPI rejects malformed status-update payloads."""
  configure_api(database_path)

  response = request(
    "PATCH",
    "/records/status",
    json_body={
      "ids": [],
      "active": False,
    },
  )

  assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_set_records_active_announces_status_change(
  database_path: Path,
) -> None:
  """Ensure configured Telegram announcements receive status changes."""
  announcer = SpyTelegramAnnouncer()
  harness = configure_api(
    database_path,
    request_id_header="X-Owe-User",
    announcer=announcer,
  )
  harness.database.add_records([make_record()])

  response = request(
    "PATCH",
    "/records/status",
    json_body={
      "ids": [1],
      "active": False,
    },
    headers={"X-Owe-User": "auditor@example.com"},
  )

  assert response.status_code == status.HTTP_200_OK
  assert len(announcer.status_announcements) == 1
  records, users, requester, active = announcer.status_announcements[0]
  assert [record.id for record in records] == [1]
  assert [user.id for user in users] == ["alice", "bob", "carol", "dave"]
  assert requester == "auditor@example.com"
  assert active is False


def test_get_summary_returns_alias_keys(database_path: Path) -> None:
  """Ensure summaries serialize settlement direction with API field aliases."""
  harness = configure_api(database_path)
  harness.database.add_records(
    [
      make_record(amount=100),
      make_record(lender="bob", borrower="carol", amount=40),
    ]
  )

  response = request("GET", "/summary")

  assert response.status_code == status.HTTP_200_OK
  assert response_body(response) == {
    "success": True,
    "summary": [
      {"from": "bob", "to": "alice", "amount": 60},
      {"from": "carol", "to": "alice", "amount": 40},
    ],
  }


@pytest.mark.parametrize(
  ("path", "method_name"),
  [
    ("/users", "get_users"),
    ("/records", "get_records"),
    ("/summary", "get_summary"),
  ],
)
def test_database_errors_return_generic_500(
  monkeypatch: pytest.MonkeyPatch,
  database_path: Path,
  path: str,
  method_name: str,
) -> None:
  """Ensure database failures are hidden behind a generic API error."""
  harness = configure_api(database_path)

  def raise_database_error(**_kwargs: object) -> object:
    msg = "boom"
    raise DatabaseError(msg)

  monkeypatch.setattr(harness.owe_service, method_name, raise_database_error)

  response = request("GET", path)

  assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
  assert response_body(response) == {
    "success": False,
    "error": "Database error",
  }
