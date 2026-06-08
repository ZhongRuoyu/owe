import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import api, init
from .config import load_env_config
from .redacting_filter import RedactingFilter
from .static import static


def create_app() -> FastAPI:
  """Create and configure the FastAPI application instance."""
  config = load_env_config()
  logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=getattr(logging, config.log_level, logging.INFO),
  )
  if config.telegram_bot_token:
    redacting_filter = RedactingFilter(config.telegram_bot_token)
    for handler in logging.getLogger().handlers:
      handler.addFilter(redacting_filter)

  app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
  )
  init(api, config)
  if config.api_only:
    app.mount(config.url_prefix, api)
    app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],
      allow_methods=["*"],
      allow_headers=["*"],
    )
  else:
    app.mount(f"{config.url_prefix}/api", api)
    app.mount(config.url_prefix, static)
  return app
