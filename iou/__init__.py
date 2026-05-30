from flask import Flask
from flask_cors import CORS

from iou.blueprints import blueprint, init

init()
app = Flask(__name__)
app.register_blueprint(blueprint)
CORS(app)
