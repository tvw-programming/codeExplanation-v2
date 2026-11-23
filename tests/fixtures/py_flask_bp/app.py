from flask import Flask
from blueprints.api import bp

app = Flask(__name__)
app.register_blueprint(bp, url_prefix="/v1")
