from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

STATIC_DIR = (Path(__file__).resolve().parent / "static").resolve()


static = FastAPI(
  docs_url=None,
  redoc_url=None,
  openapi_url=None,
)
static.mount("/", StaticFiles(directory=STATIC_DIR, html=True))


@static.middleware("http")
async def dispatch(
  request: Request,
  call_next: RequestResponseEndpoint,
) -> Response:
  """Add a strict content security policy to the outgoing response."""
  response = await call_next(request)
  response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "connect-src 'self' https://cdnjs.cloudflare.com; "
    "script-src 'self' https://cdnjs.cloudflare.com; "
    "style-src 'self' https://cdnjs.cloudflare.com; "
    "img-src 'self' data:; "
  )
  return response
