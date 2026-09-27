'''Test PostgreSQL inserts, the Required schema, and URL deduplication.

a. Verify inserted rows have the required schema and non-empty provided values.
b. Verify repeat URLs do not produce duplicate records in a pull batch.
c. Query inserted applicant values as a dictionary with expected field keys.
'''
import contextlib
import io
import json
import os
import runpy
import sys
import tempfile
from datetime import date
from types import SimpleNamespace
from unittest import TestCase

import psycopg
import psycopg2
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
import pytest

import clean_data
import create_database
import load_data
import pull_data
import scrape
from pull_data import _insert_records


# Queue database result rows and record SQL operations.
class FakeCursor:
    # Initialize the fake cursor's results and operation history.
    def __init__(self, rows=(), one_rows=(), all_rows=(), column_names=()):
        self.rows = list(rows)
        self.one_rows = list(one_rows)
        self.all_rows = list(all_rows)
        self.description = [SimpleNamespace(name=name) for name in column_names]
        self.statements = []
        self.batch_rows = []
        self.closed = False
        self.execute_error = None

    # Record a statement or raise its configured database error.
    def execute(self, statement, parameters=None):
        if self.execute_error:
            raise self.execute_error
        self.statements.append((statement, parameters))

    # Record batch inserts and their values.
    def executemany(self, statement, values):
        self.statements.append((statement, None))
        self.batch_rows.extend(list(values))

    # Return the next queued row.
    def fetchone(self):
        return self.one_rows.pop(0)

    # Return all queued rows.
    def fetchall(self):
        return self.rows or self.all_rows

    # Record cursor closure.
    def close(self):
        self.closed = True

    # Support cursor context management.
    def __enter__(self):
        return self

    # Leave the cursor context without suppressing exceptions.
    def __exit__(self, exception_type, exception, traceback):
        return False


# Supply a cursor through a fake database connection.
class FakeConnection:
    # Store the cursor and connection lifecycle state.
    def __init__(self, cursor=None):
        self.fake_cursor = cursor or FakeCursor()
        self.committed = False
        self.closed = False

    # Return the configured fake cursor.
    def cursor(self):
        return self.fake_cursor

    # Record a commit request.
    def commit(self):
        self.committed = True

    # Record connection closure.
    def close(self):
        self.closed = True

    # Support connection context management.
    def __enter__(self):
        return self

    # Leave the connection context without suppressing exceptions.
    def __exit__(self, exception_type, exception, traceback):
        return False


# Return a configured connection and record connection requests.
class FakeDatabase:
    # Store the connection returned by connect.
    def __init__(self, connection):
        self.connection = connection
        self.calls = []

    # Record arguments and return the configured connection.
    def connect(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.connection


# Return supplied records through the scraper interface used by the pull code.
class FakeScraper:
    # Store the rows that the fake scraper should return.
    def __init__(self, records, allowed=True, html="fake-html", next_page=None):
        self.records = records
        self.allowed = allowed
        self.html = html
        self.next_page = next_page

    # Permit the fake scrape under the same check as the real scraper.
    def _check_robots_permission(self):
        return self.allowed

    # Return a stable first-page URL for the pull loop.
    def _build_url(self, page):
        return "fake-page-1"

    # Return a stable fake page to the parser.
    def _fetch_html(self, url):
        return self.html

    # Return the configured records for the fake page.
    def parse_admissions_data(self, html):
        return self.records

    # Stop pagination after the fake page.
    def _next_page_url(self, html):
        return self.next_page


# Prepare a fixed, isolated applicants schema for database tests.
def prepare_test_database(database_url, schema):
    with psycopg.connect(database_url) as connection:
        connection.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    test_url = make_conninfo(database_url, options=f"-c search_path={schema}")
    with psycopg.connect(test_url) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS applicants (
                p_id SERIAL PRIMARY KEY,
                program TEXT,
                comments TEXT,
                date_added DATE,
                url TEXT,
                status TEXT,
                term TEXT,
                us_or_international TEXT,
                gpa FLOAT,
                gre FLOAT,
                gre_v FLOAT,
                gre_aw FLOAT,
                degree TEXT,
                llm_generated_program TEXT,
                llm_generated_university TEXT
            )
            """
        )
        connection.execute("TRUNCATE TABLE applicants RESTART IDENTITY")
    return test_url


# Group PostgreSQL insertion checks with a disposable schema.
# Exercise inserting and querying applicant rows in PostgreSQL.
@pytest.mark.db
class TestDatabaseInsert(TestCase):
    # Create a private applicants table before each integration test.
    def setUp(self):
        self.database_url = os.getenv("TEST_DATABASE_URL")
        if not self.database_url:
            self.skipTest("Set TEST_DATABASE_URL for PostgreSQL tests")

        self.test_url = prepare_test_database(self.database_url, "module4_insert_test")

    # Verify values, Required columns, and dictionary-shaped query results.
    def test_insert_schema(self):
        record = {
            "program": "Computer Science, Stanford University",
            "comments": "Research focus",
            "date_added": "Added on Sep 12, 2026",
            "url": "https://example.test/result/1001",
            "status": "Accepted",
            "term": "Fall 2026",
            "us_or_international": "International",
            "gpa": "3.85",
            "gre": "325",
            "gre_v": "160",
            "gre_aw": "4.5",
            "degree": "PhD",
            "llm_generated_program": "Computer Science",
            "llm_generated_university": "Stanford University",
        }
        expected_columns = {
            "p_id", "program", "comments", "date_added", "url", "status", "term",
            "us_or_international", "gpa", "gre", "gre_v", "gre_aw", "degree",
            "llm_generated_program", "llm_generated_university",
        }

        self.assertEqual(_insert_records([record], self.test_url), 1)
        with psycopg.connect(self.test_url, row_factory=dict_row) as connection:
            columns = {
                row["column_name"]
                for row in connection.execute(
                    """SELECT column_name FROM information_schema.columns
                       WHERE table_schema = current_schema() AND table_name = 'applicants'"""
                ).fetchall()
            }
            row = connection.execute(
                """SELECT p_id, program, comments, date_added, url, status, term,
                          us_or_international, gpa, gre, gre_v, gre_aw, degree,
                          llm_generated_program, llm_generated_university
                   FROM applicants"""
            ).fetchone()

        self.assertEqual(columns, expected_columns)
        self.assertEqual(set(row), expected_columns)
        self.assertEqual(row["date_added"], date(2026, 9, 12))
        self.assertEqual(row["program"], record["program"])
        self.assertEqual(row["url"], record["url"])
        self.assertEqual(row["gpa"], 3.85)
        self.assertEqual(row["gre"], 325.0)
        self.assertEqual(row["llm_generated_university"], "Stanford University")


# Test duplicate filtering independently of PostgreSQL.
@pytest.mark.buttons
class TestPullRecordDeduplication(TestCase):
    # Exclude URLs already stored and duplicates within the current page.
    def test_pull_deduplicates_urls(self):
        scraper = FakeScraper([
            {"url": "https://example.test/existing"},
            {"url": "https://example.test/new-1"},
            {"url": "https://example.test/new-1"},
            {"url": "https://example.test/new-2"},
        ])
        existing_urls = {"https://example.test/existing"}
        original_scraper = pull_data.GradCafeScraper
        pull_data.GradCafeScraper = lambda: scraper

        try:
            new_records = pull_data._fetch_new_records(existing_urls)
        finally:
            pull_data.GradCafeScraper = original_scraper

        self.assertEqual(
            [record["url"] for record in new_records],
            ["https://example.test/new-1", "https://example.test/new-2"],
        )

    # Check denied access and empty fetch/parse results stop scraping.
    def test_pull_stops_on_denied_or_empty_pages(self):
        original_scraper = pull_data.GradCafeScraper
        try:
            for scraper in (
                FakeScraper([], allowed=False),
                FakeScraper([], html=None),
                FakeScraper([]),
                FakeScraper([{"url": "existing"}]),
            ):
                pull_data.GradCafeScraper = lambda scraper=scraper: scraper
                result = pull_data._fetch_new_records({"existing"})
                self.assertEqual(result, [])
        finally:
            pull_data.GradCafeScraper = original_scraper

    # Check scraper pagination advances and tracks URLs across pages.
    def test_pull_follows_next_page(self):
        class TwoPageScraper(FakeScraper):
            # Return page-specific HTML while recording requested URLs.
            def __init__(self):
                super().__init__([])
                self.requested_urls = []
                self.page = 0

            # Record requests and return an HTML token for the current page.
            def _fetch_html(self, url):
                self.requested_urls.append(url)
                self.page += 1
                return f"html-{self.page}"

            # Return a new URL on page one and no next URL on page two.
            def _next_page_url(self, html):
                return "fake-page-2" if html == "html-1" else None

            # Return distinct records for each page.
            def parse_admissions_data(self, html):
                return [{"url": f"record-{html}"}]

        scraper = TwoPageScraper()
        original_scraper = pull_data.GradCafeScraper
        pull_data.GradCafeScraper = lambda: scraper
        try:
            records = pull_data._fetch_new_records(set())
        finally:
            pull_data.GradCafeScraper = original_scraper

        self.assertEqual([record["url"] for record in records], ["record-html-1", "record-html-2"])
        self.assertEqual(scraper.requested_urls, ["fake-page-1", "fake-page-2"])


# Exercise pull-data database helpers and its command-line entry point.
@pytest.mark.db
class TestPullData(TestCase):
    # Return saved URLs from the fake database connection.
    def test_existing_urls(self):
        cursor = FakeCursor(all_rows=[("old-url",), ("other-url",)])
        database = FakeDatabase(FakeConnection(cursor))
        original_connect = pull_data.psycopg.connect
        pull_data.psycopg.connect = database.connect
        try:
            urls = pull_data._existing_urls("fake-db")
        finally:
            pull_data.psycopg.connect = original_connect
        self.assertEqual(urls, {"old-url", "other-url"})

    # Check empty inserts avoid connecting and populated inserts map values.
    def test_insert_records(self):
        cursor = FakeCursor()
        database = FakeDatabase(FakeConnection(cursor))
        original_connect = pull_data.psycopg.connect
        pull_data.psycopg.connect = database.connect
        try:
            self.assertEqual(pull_data._insert_records([], "fake-db"), 0)
            self.assertEqual(database.calls, [])
            self.assertEqual(
                pull_data._insert_records([{"program": "CS", "url": "u"}], "fake-db"),
                1,
            )
        finally:
            pull_data.psycopg.connect = original_connect
        self.assertEqual(cursor.batch_rows[0][0], "CS")
        self.assertEqual(cursor.batch_rows[0][3], "u")

    # Check pull main validates its URL and runs fetch/insert with fakes.
    def test_main(self):
        original_database_url = os.environ.get("DATABASE_URL")
        original_connect = pull_data.psycopg.connect
        original_scraper = pull_data.GradCafeScraper
        original_scrape_class = scrape.GradCafeScraper
        cursor = FakeCursor(all_rows=[("old-url",)])
        database = FakeDatabase(FakeConnection(cursor))
        pull_data.psycopg.connect = database.connect
        pull_data.GradCafeScraper = lambda: FakeScraper([{"url": "new-url"}])
        scrape.GradCafeScraper = lambda: FakeScraper([{"url": "script-url"}])
        os.environ["DATABASE_URL"] = "fake-db"
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                pull_data.main()
                runpy.run_path(pull_data.__file__, run_name="__main__")
            os.environ.pop("DATABASE_URL", None)
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                pull_data.main()
        finally:
            pull_data.psycopg.connect = original_connect
            pull_data.GradCafeScraper = original_scraper
            scrape.GradCafeScraper = original_scrape_class
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url

        self.assertEqual(len(cursor.batch_rows), 2)
        self.assertEqual([row[3] for row in cursor.batch_rows], ["new-url", "script-url"])


# Exercise applicant cleanup and reset operations.
@pytest.mark.db
class TestCleanData(TestCase):
    # Check null, whitespace, numeric, and scraped-string normalization.
    def test_clean_values(self):
        self.assertIsNone(clean_data._clean_text(None))
        self.assertIsNone(clean_data._clean_text("  \t "))
        self.assertEqual(clean_data._clean_text("  A\n B  "), "A B")
        self.assertIsNone(clean_data._clean_number(None))
        self.assertIsNone(clean_data._clean_number(""))
        self.assertEqual(clean_data._clean_number(3), 3.0)
        self.assertEqual(clean_data._clean_number("GPA: 3.75/4.0"), 3.75)
        self.assertIsNone(clean_data._clean_number("not reported"))

    # Check records are cleaned without changing their primary keys.
    def test_clean_record(self):
        applicant = {"p_id": 5, "program": " Computer\n Science ", "gpa": "GPA 3.8"}
        cleaned = clean_data.clean_applicant_data(applicant)
        self.assertEqual(cleaned["p_id"], 5)
        self.assertEqual(cleaned["program"], "Computer Science")
        self.assertEqual(cleaned["gpa"], 3.8)
        self.assertEqual(applicant["program"], " Computer\n Science ")

    # Check cleaning maps updates and reset truncates the table.
    def test_database_clean_and_reset(self):
        columns = ["p_id", *clean_data.TEXT_COLUMNS, *clean_data.NUMERIC_COLUMNS]
        source_row = (
            9, " CS\n", " note ", " url ", "Accepted", "Fall 2026", "American",
            "PhD", "Computer Science", "Stanford", "3.9", "320", "160", "4.5",
        )
        cursor = FakeCursor(rows=[source_row], column_names=columns)
        database = FakeDatabase(FakeConnection(cursor))
        original_connect = clean_data.psycopg.connect
        clean_data.psycopg.connect = database.connect
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                clean_data.clean_database("fake-db")
                clean_data.reset_database("fake-db")
        finally:
            clean_data.psycopg.connect = original_connect

        self.assertEqual(len(cursor.batch_rows), 1)
        self.assertEqual(cursor.batch_rows[0][0], "CS")
        self.assertEqual(cursor.batch_rows[0][9], 3.9)
        self.assertIn("TRUNCATE TABLE applicants RESTART IDENTITY", cursor.statements[-1][0])
        self.assertEqual(len(database.calls), 2)

    # Check clean-data CLI reset, clean, and missing-URL paths.
    def test_command_line_modes(self):
        database = FakeDatabase(FakeConnection(FakeCursor(column_names=[])))
        original_connect = clean_data.psycopg.connect
        original_database_url = os.environ.get("DATABASE_URL")
        original_argv = sys.argv
        clean_data.psycopg.connect = database.connect
        os.environ["DATABASE_URL"] = "fake-db"
        try:
            sys.argv = ["clean_data.py", "--reset"]
            with contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(clean_data.__file__, run_name="__main__")
            sys.argv = ["clean_data.py"]
            with contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(clean_data.__file__, run_name="__main__")
            os.environ.pop("DATABASE_URL", None)
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                runpy.run_path(clean_data.__file__, run_name="__main__")
        finally:
            clean_data.psycopg.connect = original_connect
            sys.argv = original_argv
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url


# Exercise the legacy psycopg2 database creator.
@pytest.mark.db
class TestCreateDatabase(TestCase):
    # Check successful connections and handled connection errors.
    def test_create_connection(self):
        connection = FakeConnection()
        database = FakeDatabase(connection)
        original_connect = create_database.psycopg2.connect
        create_database.psycopg2.connect = database.connect
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIs(
                    create_database.create_connection("db", "user", "pw", "host", 5432),
                    connection,
                )

            # Raise the expected driver error from the fake connection function.
            def fail_connect(**kwargs):
                raise psycopg2.OperationalError("offline")

            create_database.psycopg2.connect = fail_connect
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(
                    create_database.create_connection("db", "user", "pw", "host", 5432)
                )
        finally:
            create_database.psycopg2.connect = original_connect

    # Check table creation, handled SQL errors, and connection cleanup.
    def test_create_table(self):
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        with contextlib.redirect_stdout(io.StringIO()):
            create_database.create_table(connection)
        self.assertIn("CREATE TABLE IF NOT EXISTS applicants", cursor.statements[0][0])
        self.assertTrue(connection.committed)
        self.assertTrue(cursor.closed)
        self.assertTrue(connection.closed)

        error_cursor = FakeCursor()
        error_cursor.execute_error = psycopg2.OperationalError("offline")
        error_connection = FakeConnection(error_cursor)
        with contextlib.redirect_stdout(io.StringIO()):
            create_database.create_table(error_connection)
        self.assertTrue(error_cursor.closed)
        self.assertTrue(error_connection.closed)

    # Check main uses its configured defaults and creates the table.
    def test_main(self):
        connection = FakeConnection()
        original_create_connection = create_database.create_connection
        original_connect = create_database.psycopg2.connect
        create_database.create_connection = lambda *args: connection
        create_database.psycopg2.connect = lambda **kwargs: connection
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                create_database.main()
                runpy.run_path(create_database.__file__, run_name="__main__")
        finally:
            create_database.create_connection = original_create_connection
            create_database.psycopg2.connect = original_connect
        self.assertTrue(connection.committed)


# Exercise JSON conversion and applicant bulk loading.
@pytest.mark.db
class TestLoadData(TestCase):
    # Check numeric/date conversion and support for legacy JSON keys.
    def test_field_conversion(self):
        self.assertIsNone(load_data._number(None))
        self.assertIsNone(load_data._number("none"))
        self.assertEqual(load_data._number("GRE: 321"), 321.0)
        self.assertIsNone(load_data._date(None))
        self.assertEqual(load_data._date("Added on Sep 12, 2026"), date(2026, 9, 12))
        self.assertEqual(load_data._value({"old": 1}, "new", "old"), 1)
        self.assertIsNone(load_data._value({}, "new"))
        applicant = {
            "program": "CS", "comments": "note", "date_added": None, "url": "u",
            "status": "Accepted", "term": "Fall 2026", "US/International": "American",
            "GPA": "3.9", "GRE": "320", "GRE-V": "160", "GRE-AW": "4.5",
            "Degree": "PhD", "llm-generated-program": "CS",
            "llm-generated-university": "Stanford",
        }
        values = load_data._applicant_values(applicant)
        self.assertEqual(values[6:11], ("American", 3.9, 320.0, 160.0, 4.5))
        self.assertEqual(values[-2:], ("CS", "Stanford"))

    # Check JSON insertion with records, empty data, and guarded CLI paths.
    def test_load_data_to_db(self):
        cursor = FakeCursor()
        database = FakeDatabase(FakeConnection(cursor))
        original_connect = load_data.psycopg.connect
        original_join = load_data.os.path.join
        original_database_url = os.environ.get("DATABASE_URL")
        original_argv = sys.argv
        load_data.psycopg.connect = database.connect
        try:
            with tempfile.TemporaryDirectory() as directory:
                json_path = os.path.join(directory, "records.json")
                with open(json_path, "w", encoding="utf-8") as data_file:
                    json.dump([{"program": "CS", "gpa": "3.8"}], data_file)
                with contextlib.redirect_stdout(io.StringIO()):
                    load_data.load_data_to_db(json_path, "fake-db")

                empty_path = os.path.join(directory, "empty.json")
                with open(empty_path, "w", encoding="utf-8") as data_file:
                    json.dump([], data_file)
                with contextlib.redirect_stdout(io.StringIO()):
                    load_data.load_data_to_db(empty_path, "fake-db")

                # Route the CLI to the small fixture rather than the large export.
                load_data.os.path.join = lambda *parts: (
                    json_path if parts[-1] == "llm_extend_applicant_data.json"
                    else original_join(*parts)
                )
                os.environ["DATABASE_URL"] = "fake-db"
                sys.argv = ["load_data.py"]
                with contextlib.redirect_stdout(io.StringIO()):
                    runpy.run_path(load_data.__file__, run_name="__main__")
                os.environ.pop("DATABASE_URL", None)
                with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                    runpy.run_path(load_data.__file__, run_name="__main__")
        finally:
            load_data.os.path.join = original_join
            load_data.psycopg.connect = original_connect
            sys.argv = original_argv
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url
