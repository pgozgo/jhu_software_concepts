'''Test app setup and GET /analysis (served at /).

a. Verify analysis, pull-data, and update-analysis routes are registered.
b. Verify a 200 response, both buttons, Analysis text, and an Answer label.
'''
import os
import runpy
from unittest import TestCase

import pytest
from flask import Flask

import app.app as flask_app_module


# Return fixed query rows for Flask analysis-page requests.
class FakeCursor:
    # Initialize the result rows consumed by the app queries.
    def __init__(self):
        self.fetchone_rows = [(12.5,), (3.5, 320.0, 160.0, 4.0)]
        self.fetchall_rows = [("Stanford University", 2)]

    # Accept SQL statements without contacting PostgreSQL.
    def execute(self, query, parameters=None):
        return None

    # Return the next single-row analysis result.
    def fetchone(self):
        return self.fetchone_rows.pop(0)

    # Return the university aggregate result.
    def fetchall(self):
        return self.fetchall_rows

    # Support use as a cursor context manager.
    def __enter__(self):
        return self

    # Leave cursor context without suppressing exceptions.
    def __exit__(self, exception_type, exception, traceback):
        return False


# Supply a cursor object when the app opens a fake database connection.
class FakeConnection:
    # Create an independent result cursor for this connection.
    def __init__(self):
        self.fake_cursor = FakeCursor()

    # Return the fake cursor used by the app's context manager.
    def cursor(self):
        return self.fake_cursor

    # Support use as a connection context manager.
    def __enter__(self):
        return self

    # Leave connection context without suppressing exceptions.
    def __exit__(self, exception_type, exception, traceback):
        return False


# Track database access while returning fake query connections.
class FakeDatabase:
    # Initialize a connection counter for route assertions.
    def __init__(self):
        self.connection_calls = 0

    # Open a fake connection instead of a real PostgreSQL connection.
    def connect(self, *args, **kwargs):
        self.connection_calls += 1
        return FakeConnection()


# Group page tests with a fake PostgreSQL connection.
@pytest.mark.web
class TestAnalysisPage(TestCase):
    # Configure the Flask client and predictable SQL result rows.
    def setUp(self):
        self.original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "postgresql://test/test"
        self.original_connect = flask_app_module.psycopg.connect
        self.database = FakeDatabase()
        flask_app_module.psycopg.connect = self.database.connect
        self.original_pull_process = flask_app_module._pull_process
        flask_app_module._pull_process = None
        flask_app_module.app.config.update(TESTING=True)
        self.client = flask_app_module.app.test_client()

    # Restore app and environment dependencies after each page test.
    def tearDown(self):
        flask_app_module.psycopg.connect = self.original_connect
        flask_app_module._pull_process = self.original_pull_process
        if self.original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.original_database_url

    # Verify the routes and page components required by the assignment.
    def test_analysis_page(self):
        # This checks that all three URL paths are registered with Flask.
        routes = {rule.rule for rule in flask_app_module.app.url_map.iter_rules()}

        # This request exercises the registered GET / analysis route.
        response = self.client.get("/")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue({"/", "/pull-data", "/update-analysis"}.issubset(routes))
        self.assertIn("Applicant analysis", page)
        self.assertIn("Pull Data", page)
        self.assertIn("Update Analysis", page)
        self.assertIn("Question 10", page)
        self.assertIn("Question 11", page)
        self.assertIn("Answer:", page)

    # Verify analysis labels and percentage precision in the rendered page.
    def test_analysis_labels_and_percent(self):
        page = self.client.get("/").get_data(as_text=True)

        self.assertIn("Answer:", page)
        self.assertIn("12.50%", page)

    # Check the analysis route rejects a missing database URL.
    def test_analysis_requires_database_url(self):
        os.environ.pop("DATABASE_URL", None)
        with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
            self.client.get("/")

    # Exercise the Flask application's guarded command-line startup.
    def test_app_script_entry_point(self):
        original_run = Flask.run
        calls = []

        # Capture app.run arguments instead of starting a server.
        def record_run(application, **kwargs):
            calls.append(kwargs)

        Flask.run = record_run
        try:
            runpy.run_path(flask_app_module.__file__, run_name="__main__")
        finally:
            Flask.run = original_run

        self.assertEqual(calls, [{"host": "0.0.0.0", "port": 8080}])