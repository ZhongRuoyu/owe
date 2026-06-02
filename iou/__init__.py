from flask import Flask
from flask_cors import CORS

import iou.app


def create_app(
  *,
  url_prefix: str | None = None,
  api_only: bool = False,
) -> Flask:
  iou.app.init()
  app = Flask(__name__, static_folder=None)
  bp = iou.app.api if api_only else iou.app.app
  app.register_blueprint(bp, url_prefix=url_prefix)
  CORS(app)
  return app
