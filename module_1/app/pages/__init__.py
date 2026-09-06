from flask import Flask
from app.pages import pages

def create_app():
    app = Flask(__name__, template_folder="../templates", static_folder="../static") # Flask constructor
    app.register_blueprint(pages.bp)  # Register the pages blueprint

    return app