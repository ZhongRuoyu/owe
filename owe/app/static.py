from pathlib import Path

from flask import Blueprint, Response

STATIC_DIR = Path(__file__).resolve().parent / "static"

static = Blueprint(
  "owe",
  __name__,
  url_prefix="",
  static_folder=STATIC_DIR,
  static_url_path="",
)


@static.after_request
def add_csp(response: Response) -> Response:
  """Attach a strict content security policy to outgoing responses."""
  response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "script-src 'self' https://cdnjs.cloudflare.com; "
    "style-src 'self' https://cdnjs.cloudflare.com; "
    "img-src 'self' data:; "
  )
  return response


@static.route("/")
def index() -> Response:
  """Serve the single-page application entry point."""
  return static.send_static_file("index.html")
