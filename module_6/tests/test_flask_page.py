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
from query_limits import MAX_QUERY_LIMIT, clamp_query_limit


# Return fixed query rows for Flask analysis-page requests.
class FakeCursor:
    # Initialize the result rows consumed by the app queries.
    def __init__(self):
        self.fetchone_rows = [(12.5,), (3.5, 320.0, 160.0, 4.0)]
        self.fetchall_rows = [("Stanford University", 2)]
        self.statements = []

    # Accept SQL statements without contacting PostgreSQL.
    def execute(self, query, parameters=None):
        self.statements.append((query, parameters))

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
        self.connection_args = []
        self.connections = []

    # Open a fake connection instead of a real PostgreSQL connection.
    def connect(self, *args, **kwargs):
        self.connection_calls += 1
        self.connection_args.append((args, kwargs))
        connection = FakeConnection()
        self.connections.append(connection)
        return connection


# Return deterministic template data and record the configured database URL.
class FakeAnalysisQuery:
    # Initialize the list of database URLs passed to the query service.
    def __init__(self):
        self.database_urls = []
        self.limits = []

    # Return the analysis values consumed by index().
    def __call__(self, database_url, limit=1):
        self.database_urls.append(database_url)
        self.limits.append(limit)
        return {
            "percent_international": 12.5,
            "q10_university_counts": [("Stanford University", 2)],
            "q11_averages": (3.5, 320.0, 160.0, 4.0),
        }


# Group page tests with a fake PostgreSQL connection.
@pytest.mark.web
class TestAnalysisPage(TestCase):
    # Configure the Flask client and predictable SQL result rows.
    def setUp(self):
        self.analysis_query = FakeAnalysisQuery()
        self.application = flask_app_module.create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_URL": "postgresql://test/test",
            "ANALYSIS_QUERY": self.analysis_query,
        })
        self.client = self.application.test_client()

    # Verify the factory creates an independent app with config overrides.
    def test_factory_config_override(self):
        self.assertIsNot(self.application, flask_app_module.app)
        self.assertEqual(self.application.config["DATABASE_URL"], "postgresql://test/test")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.analysis_query.database_urls, ["postgresql://test/test"])
        self.assertEqual(self.analysis_query.limits, [1])

    # Exercise the default pull launcher without starting a real subprocess.
    def test_default_pull_runner(self):
        calls = []
        process = type("Process", (), {"poll": lambda self: 0})()
        original_popen = flask_app_module.subprocess.Popen

        # Record the command and return a completed process substitute.
        def fake_popen(command, env):
            calls.append((command, env))
            return process

        flask_app_module.subprocess.Popen = fake_popen
        try:
            response = self.client.post("/pull-data")
        finally:
            flask_app_module.subprocess.Popen = original_popen

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json(), {"ok": True})
        self.assertEqual(calls[0][0], [
            flask_app_module.sys.executable,
            flask_app_module.PULL_DATA_SCRIPT,
        ])

    # Verify the default query service connects using the factory's database URL.
    def test_default_query_uses_configured_database(self):
        database = FakeDatabase()
        original_connect = flask_app_module.psycopg.connect
        flask_app_module.psycopg.connect = database.connect
        application = flask_app_module.create_app({
            "TESTING": True,
            "DATABASE_URL": "postgresql://override/test",
        })
        try:
            response = application.test_client().get("/")
            analysis = flask_app_module.run_analysis_queries("postgresql://override/test")
        finally:
            flask_app_module.psycopg.connect = original_connect

        self.assertEqual(response.status_code, 200)
        self.assertEqual(database.connection_args[0][0][0], "postgresql://override/test")
        self.assertIs(application.config["ANALYSIS_QUERY"], flask_app_module.run_analysis_queries)
        self.assertEqual(
            set(analysis),
            {"percent_international", "q10_university_counts", "q11_averages"},
        )
        first_connection_statements = database.connections[0].fake_cursor.statements
        select_queries = [
            (query, parameters)
            for query, parameters in first_connection_statements
            if "SELECT" in query.upper()
        ]
        limited_queries = [
            (query, parameters)
            for query, parameters in first_connection_statements
            if "LIMIT %s" in query
        ]
        self.assertEqual(len(select_queries), 3)
        self.assertTrue(all("LIMIT" in query.upper() for query, _ in select_queries))
        self.assertEqual(limited_queries[0][1][-1], 1)

    # Verify the routes and page components required by the assignment.
    def test_analysis_page(self):
        # This checks that all three URL paths are registered with Flask.
        routes = {rule.rule for rule in self.application.url_map.iter_rules()}

        # This request exercises the assignment's GET /analysis route.
        response = self.client.get("/analysis")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue({"/", "/analysis", "/pull-data", "/update-analysis"}.issubset(routes))
        self.assertIn("Analysis", page)
        self.assertIn("Pull Data", page)
        self.assertIn("Update Analysis", page)
        self.assertIn('data-testid="pull-data-btn"', page)
        self.assertIn('data-testid="update-analysis-btn"', page)
        self.assertIn("Question 10", page)
        self.assertIn("Question 11", page)
        self.assertIn('name="limit"', page)
        self.assertIn('max="100"', page)
        self.assertIn("Answer:", page)
        self.assertEqual(page.count("Answer:"), 6)

    # Verify analysis labels and percentage precision in the rendered page.
    def test_analysis_labels_and_percent(self):
        page = self.client.get("/analysis").get_data(as_text=True)

        self.assertIn("Answer:", page)
        self.assertIn("12.50%", page)

    # Clamp user limits to the supported range and reject malformed values.
    def test_result_limit_validation(self):
        self.assertEqual(clamp_query_limit(None), 1)
        self.assertEqual(clamp_query_limit("0"), 1)
        self.assertEqual(clamp_query_limit(str(MAX_QUERY_LIMIT + 1)), MAX_QUERY_LIMIT)
        self.assertEqual(clamp_query_limit("25"), 25)
        with self.assertRaises(ValueError):
            clamp_query_limit("not-a-number")
        with self.assertRaises(ValueError):
            clamp_query_limit(True)
        with self.assertRaises(ValueError):
            clamp_query_limit(1.5)

    def test_requested_result_limit_is_clamped(self):
        response = self.client.get("/analysis?limit=1000")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.analysis_query.limits, [MAX_QUERY_LIMIT])
        self.assertIn(f'value="{MAX_QUERY_LIMIT}"', response.get_data(as_text=True))

    def test_invalid_result_limit_is_rejected(self):
        response = self.client.get("/analysis?limit=all")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.analysis_query.limits, [])

    # Check the analysis route rejects a missing database URL.
    def test_analysis_requires_database_url(self):
        application = flask_app_module.create_app({
            "TESTING": True,
            "DATABASE_URL": None,
            "ANALYSIS_QUERY": self.analysis_query,
        })
        with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
            application.test_client().get("/")

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