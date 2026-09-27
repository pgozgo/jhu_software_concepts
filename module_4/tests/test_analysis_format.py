'''Test analysis labels and percentage rounding.

a. Verify rendered answers have labels and percentages have two decimals.
b. Verify ORM and raw SQL analysis functions return their expected values.
'''
import contextlib
import importlib
import io
import os
import runpy
import sys
from unittest import TestCase

import psycopg
import pytest

import app.app as flask_app_module
from test_db_insert import FakeConnection, FakeCursor, FakeDatabase as SourceFakeDatabase
from test_flask_page import FakeDatabase as FlaskFakeDatabase


# Check percentage output through the Flask-rendered analysis page.
@pytest.mark.analysis # Mark this test class as part of the analysis tests
class TestAnalysisFormat(TestCase):
    # Configure fake query results for the page template.
    def setUp(self):
        self.original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "postgresql://test/test"
        self.original_connect = flask_app_module.psycopg.connect
        flask_app_module.psycopg.connect = FlaskFakeDatabase().connect
        self.original_pull_process = flask_app_module._pull_process
        flask_app_module._pull_process = None
        flask_app_module.app.config.update(TESTING=True)
        self.client = flask_app_module.app.test_client()

    # Restore the app connection and environment after the formatting test.
    def tearDown(self):
        flask_app_module.psycopg.connect = self.original_connect
        flask_app_module._pull_process = self.original_pull_process
        if self.original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.original_database_url

    # Verify labels and percentage precision in the actual response.
    def test_percentage_format(self):
        response = self.client.get("/")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Answer:", page)
        self.assertIn("12.50%", page)


# Exercise SQLAlchemy model declarations and ORM query functions.
@pytest.mark.analysis
class TestOrmQueries(TestCase):
    # Load the model against SQLite and add representative applicants.
    def setUp(self):
        self.original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "sqlite://"
        self.original_models = sys.modules.pop("models", None)
        self.original_queries = sys.modules.pop("orm_queries", None)
        self.models = importlib.import_module("models")
        self.models.Base.metadata.create_all(self.models.engine)
        self.queries = importlib.import_module("orm_queries")
        with self.models.Session.begin() as session:
            session.add_all([
                self.models.Applicant(
                    program="Computer Science, Stanford University", status="Accepted",
                    term="Fall 2026", us_or_international="American", degree="PhD",
                    gpa=3.8, gre=320, gre_v=160, gre_aw=4.5,
                    llm_generated_program="Computer Science",
                    llm_generated_university="Stanford University",
                ),
                self.models.Applicant(
                    program="Computer Science, Johns Hopkins University", status="Accepted",
                    term="Fall 2025", us_or_international="International", degree="Masters",
                    gpa=3.6, gre=315, gre_v=158, gre_aw=4.0,
                    llm_generated_program="Computer Science",
                    llm_generated_university="Johns Hopkins University",
                ),
                self.models.Applicant(
                    program="Computer Science, MIT", status="Rejected", term="Fall 2025",
                    us_or_international="American", degree="Masters", gpa=3.7,
                    gre=318, gre_v=159, gre_aw=4.0,
                    llm_generated_program="Computer Science",
                    llm_generated_university="Massachusetts Institute of Technology",
                ),
                self.models.Applicant(
                    program="Computer Science, JHU", status="Pending", term="Fall 2026",
                    us_or_international="Other", degree="Masters", gpa=3.9,
                    gre=325, gre_v=162, gre_aw=5.0,
                ),
            ])

    # Restore imported model state and the database URL after ORM checks.
    def tearDown(self):
        self.models.Base.metadata.drop_all(self.models.engine)
        self.models.engine.dispose()
        sys.modules.pop("models", None)
        sys.modules.pop("orm_queries", None)
        if self.original_models is not None:
            sys.modules["models"] = self.original_models
        if self.original_queries is not None:
            sys.modules["orm_queries"] = self.original_queries
        if self.original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.original_database_url

    # Check all ORM query functions and the report entry point.
    def test_orm_queries(self):
        with self.models.Session() as session:
            self.assertEqual(self.queries.question_1(session), 2)
            self.assertEqual(self.queries.question_4(session), 3.8)
            self.assertEqual(self.queries.question_5(session), 50.0)
            self.assertEqual(self.queries.question_8(session), 1)
            self.assertEqual(self.queries.question_9(session), 1)
            self.assertEqual(self.queries.question_10(session)[0][0], "Stanford University")
            self.assertEqual(self.queries.question_11(session), (3.9, 325.0, 162.0, 5.0))

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.queries.main()
            runpy.run_path(self.queries.__file__, run_name="__main__")
        self.assertIn("Average GPA American: 3.8", output.getvalue())

    # Check null averages and empty-result behavior.
    def test_empty_orm_results(self):
        self.models.Base.metadata.drop_all(self.models.engine)
        self.models.Base.metadata.create_all(self.models.engine)
        with self.models.Session() as session:
            self.assertIsNone(self.queries.question_4(session))
            self.assertIsNone(self.queries.question_5(session))
            self.assertEqual(self.queries.question_10(session), [])
            self.assertEqual(self.queries.question_11(session), (None, None, None, None))

    # Check model imports reject a missing database URL.
    def test_model_requires_database_url(self):
        current_models = sys.modules.pop("models")
        os.environ.pop("DATABASE_URL", None)
        try:
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                importlib.import_module("models")
        finally:
            os.environ["DATABASE_URL"] = "sqlite://"
            sys.modules.pop("models", None)
            sys.modules["models"] = current_models


# Exercise the raw SQL reporting script using queued database rows.
@pytest.mark.analysis
class TestRawQueries(TestCase):
    # Run query_data.py and verify report output and connection cleanup.
    def test_query_report(self):
        cursor = FakeCursor(
            one_rows=[
                (3,), (25.0,), (3.5, 320.0, 160.0, 4.0), (3.8,), (50.0,),
                (3.9,), (2,), (1,), (1,), (3.7, 318.0, 159.0, 4.2),
            ],
            all_rows=[("Stanford University", 2)],
        )
        connection = FakeConnection(cursor)
        database = SourceFakeDatabase(connection)
        original_connect = psycopg.connect
        original_database_url = os.environ.get("DATABASE_URL")
        psycopg.connect = database.connect
        os.environ["DATABASE_URL"] = "fake-db"
        try:
            output = io.StringIO()
            query_path = os.path.join(
                os.path.dirname(__file__), "..", "src", "query_data.py"
            )
            with contextlib.redirect_stdout(output):
                runpy.run_path(query_path)
        finally:
            psycopg.connect = original_connect
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url

        self.assertIn("Q1: Fall 2026 applicant count: 3", output.getvalue())
        self.assertTrue(connection.closed)