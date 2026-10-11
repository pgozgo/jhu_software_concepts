"""Run the Flask application on the container interface."""

from web.app.app import app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
