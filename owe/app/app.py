from flask import Flask
from flask_cors import CORS

from .api import api, init
from .config import load_env_config
from .static import static


def create_app(
  *,
  url_prefix: str | None = None,
  api_only: bool = False,
) -> Flask:
  """Create and configure the Flask application instance."""
  app = Flask(__name__, static_folder=None)
  app.config.update(load_env_config())
  init(app)
  if api_only:
    app.register_blueprint(api, url_prefix=url_prefix)
    CORS(app)
  else:
    app.register_blueprint(static, url_prefix=url_prefix)
    app.register_blueprint(api, url_prefix=f"{url_prefix or ''}/api")
  return app
