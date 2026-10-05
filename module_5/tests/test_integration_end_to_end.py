'''Test the pull, update, and render flow end to end.

a. Pull fake scraper rows into PostgreSQL, update analysis, and render results.
b. Repeat the pull with overlapping rows and verify the database remains consistent.
'''
import contextlib
import io
import json
import os
import runpy
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

import psycopg
import pytest
import scrape
import urllib3
import pytest

import app.app as flask_app_module
import pull_data
from test_db_insert import FakeScraper, prepare_test_database


# Represent the completed synchronous fake pull process.
class FakeProcess:
    # Return the process completion code when polled.
    def poll(self):
        return 0


# Run the production pull entry point in place of spawning a subprocess.
class FakePullLauncher:
    # Initialize the launcher call counter.
    def __init__(self):
        self.calls = 0

    # Execute the pull pipeline and return its completed process substitute.
    def __call__(self, *args, **kwargs):
        self.calls += 1
        pull_data.main()
        return FakeProcess()


# Exercise the complete flow against an isolated PostgreSQL schema.
# Group end-to-end application tests.
@pytest.mark.integration
@pytest.mark.db
class TestPullUpdateRender(TestCase):
    # Create the test schema and configure the Flask client.
    def setUp(self):
        self.database_url = os.getenv("TEST_DATABASE_URL")
        if not self.database_url:
            self.skipTest("Set TEST_DATABASE_URL for end-to-end tests")

        self.test_url = prepare_test_database(self.database_url, "module4_e2e_test")
        self.original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = self.test_url
        self.launcher = FakePullLauncher()
        self.application = flask_app_module.create_app({
            "TESTING": True,
            "DATABASE_URL": self.test_url,
            "PULL_DATA_RUNNER": self.launcher,
        })
        self.client = self.application.test_client()

    # Restore the database URL after the integration test.
    def tearDown(self):
        if self.original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.original_database_url

    # Pull records twice, refresh analysis, and verify uniqueness and formatting.
    def test_pull_update_render(self):
        fake_records = [
            {
                "program": "Computer Science, Stanford University",
                "comments": "Research focus",
                "date_added": "Added on Sep 12, 2026",
                "url": "https://example.test/result/1",
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
            },
            {
                "program": "Computer Science, Johns Hopkins University",
                "comments": "Systems focus",
                "date_added": "Added on Sep 13, 2026",
                "url": "https://example.test/result/2",
                "status": "Pending",
                "term": "Fall 2026",
                "us_or_international": "American",
                "gpa": "3.65",
                "gre": "318",
                "gre_v": "156",
                "gre_aw": "4.0",
                "degree": "Master's",
                "llm_generated_program": "Computer Science",
                "llm_generated_university": "Johns Hopkins University",
            },
        ]
        scraper = FakeScraper(fake_records)
        original_scraper = pull_data.GradCafeScraper
        pull_data.GradCafeScraper = lambda: scraper
        try:
            first_pull = self.client.post("/pull-data")
            repeated_pull = self.client.post("/pull-data")
        finally:
            pull_data.GradCafeScraper = original_scraper
        update_response = self.client.post("/update-analysis")
        analysis_response = self.client.get("/analysis")

        self.assertEqual(first_pull.status_code, 202)
        self.assertEqual(first_pull.get_json(), {"ok": True})
        self.assertEqual(repeated_pull.status_code, 202)
        self.assertEqual(self.launcher.calls, 2)
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.get_json(), {"ok": True})
        self.assertEqual(analysis_response.status_code, 200)
        page = analysis_response.get_data(as_text=True)
        self.assertIn("50.00%", page)
        self.assertIn("Stanford University", page)
        self.assertIn("3.65", page)
        with psycopg.connect(self.test_url) as connection:
            count = connection.execute("SELECT COUNT(*) FROM applicants").fetchone()[0]
        self.assertEqual(count, 2)


# Return a chosen HTTP status and body to the scraper.
class FakeHttpResponse:
    # Store the response status and bytes body.
    def __init__(self, status, data=b"page"):
        self.status = status
        self.data = data


# Return scripted responses or raise a scripted network error.
class FakeHttpClient:
    # Store queued responses and an optional request exception.
    def __init__(self, responses=(), error=None):
        self.responses = list(responses)
        self.error = error
        self.requests = []

    # Record request details and return the next fake response.
    def request(self, *args, **kwargs):
        self.requests.append((args, kwargs))
        if self.error:
            raise self.error
        return self.responses.pop(0)


# Exercise scraper helpers and HTML parsing without live HTTP requests.
@pytest.mark.integration
class TestScraper(TestCase):
    # Create a scraper for the fake Grad Cafe domain.
    def setUp(self):
        self.scraper = scrape.GradCafeScraper("https://example.test/")

    # Verify URL building and cursor-style next links.
    def test_urls_and_pagination(self):
        self.assertEqual(
            self.scraper._build_url(), "https://example.test/survey/index.php"
        )
        self.assertEqual(
            self.scraper._build_url(2, "computer science"),
            "https://example.test/survey/index.php?page=2&q=computer+science",
        )
        self.assertEqual(
            self.scraper._next_page_url('<a href="/survey?page=2">Next</a>'),
            "https://example.test/survey?page=2",
        )
        self.assertIsNone(self.scraper._next_page_url("<p>End</p>"))

    # Verify robots rules, default status handling, and read failures.
    def test_robots_permission(self):
        self.scraper.http = FakeHttpClient([
            FakeHttpResponse(200, b"User-agent: *\nDisallow: /survey/index.php")
        ])
        self.assertFalse(self.scraper._check_robots_permission())
        self.scraper.http = FakeHttpClient([
            FakeHttpResponse(200, b"User-agent: *\nAllow: /")
        ])
        self.assertTrue(self.scraper._check_robots_permission())
        self.scraper.http = FakeHttpClient([FakeHttpResponse(503)])
        self.assertTrue(self.scraper._check_robots_permission())

        original_parser = scrape.urllib.robotparser.RobotFileParser

        # Return a parser whose fallback read can be configured per test.
        class FallbackParser:
            # Configure the read result and fetch permission.
            def __init__(self, read_error=False, allowed=False):
                self.read_error = read_error
                self.allowed = allowed

            # Accept the robots URL assignment.
            def set_url(self, url):
                self.url = url

            # Accept response-body parsing.
            def parse(self, lines):
                self.lines = lines

            # Return the configured fallback permission.
            def can_fetch(self, user_agent, url):
                return self.allowed

            # Simulate reading the robots URL when the request fails.
            def read(self):
                if self.read_error:
                    raise OSError("offline")

        scrape.urllib.robotparser.RobotFileParser = lambda: FallbackParser(allowed=True)
        self.scraper.http = FakeHttpClient(error=RuntimeError("request failed"))
        try:
            self.assertTrue(self.scraper._check_robots_permission())
            scrape.urllib.robotparser.RobotFileParser = lambda: FallbackParser(read_error=True)
            self.assertTrue(self.scraper._check_robots_permission())
        finally:
            scrape.urllib.robotparser.RobotFileParser = original_parser

    # Verify successful, blocked, rate-limited, and failed page requests.
    def test_fetch_responses(self):
        for status, expected in ((200, "page"), (403, None), (429, None), (500, None)):
            self.scraper.http = FakeHttpClient([FakeHttpResponse(status)])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.scraper._fetch_html("page-url"), expected)

        self.scraper.http = FakeHttpClient(error=urllib3.exceptions.HTTPError("offline"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(self.scraper._fetch_html("page-url"))
        self.scraper.http = FakeHttpClient(error=ValueError("bad response"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(self.scraper._fetch_html("page-url"))

    # Reject paths that cannot share a common filesystem root.
    def test_safe_path_rejects_incompatible_roots(self):
        with patch("scrape.os.path.commonpath", side_effect=ValueError("different roots")):
            with self.assertRaisesRegex(ValueError, "selected working directory"):
                scrape._resolve_path_within_root("inside.html", ".")

    # Verify text cleanup and elapsed-time formatting variants.
    def test_text_and_time_helpers(self):
        self.assertEqual(scrape.clean_text(None), "")
        self.assertEqual(scrape.clean_text("<b>A &amp; B</b> Report  Spam"), "A & B")
        self.assertEqual(scrape._format_seconds(None), "Unknown")
        self.assertEqual(scrape._format_seconds(-1), "Unknown")
        self.assertEqual(scrape._format_seconds(65), "01m 05s")
        self.assertEqual(scrape._format_seconds(3661), "1h 01m 01s")

    # Parse representative rows, subrows, optional fields, and skipped rows.
    def test_parse_admissions_rows(self):
        html = """
        <table>
          <tr><th>University</th><th>Program</th></tr>
          <tr></tr>
          <tr><td>Only one cell</td></tr>
          <tr><td>Ignore</td><td>Unrelated</td></tr>
          <tr><td>Stanford</td><td>Computer Science PhD Fall 2026 Accepted
            GPA: 3.90 GRE: 325 GRE V: 160 GRE AW: 4.5
            International with US Degree Added on Sep 12, 2026
            <span class="tw-sr-only">Total comments 50</span>
            <a href="/result/101">Result</a></td></tr>
          <tr class="tw-border-none"><td colspan="2"><p>A strong research fit and great faculty.</p></td></tr>
          <tr><td>MIT</td><td>Rejected Winter 2025 Americans /result/202</td>
            <td>Sep 13, 2025</td></tr>
          <tr><td>Accepted</td></tr>
          <tr><td><span class="comment">A later decision note</span></td><td></td></tr>
          <tr><td></td><td>Computational Biology Masters Rejected Internationally trained</td><td></td></tr>
          <tr><td></td><td>Physics department</td><td></td></tr>
          <tr><td>Other University</td><td>MFA Other</td><td></td></tr>
          <tr><td></td><td></td><td>Sep 14, 2025</td></tr>
        </table>
        """

        records = self.scraper.parse_admissions_data(html)

        self.assertEqual(len(records), 6)
        self.assertEqual(records[0]["program"], "Computer Science, Stanford")
        self.assertEqual(records[0]["url"], "https://example.test/result/101")
        self.assertEqual(records[0]["degree"], "PhD")
        self.assertEqual(records[0]["gpa"], 3.9)
        self.assertEqual(records[0]["gre_aw"], 4.5)
        self.assertIn("research fit", records[0]["comments"])
        self.assertEqual(records[1]["url"], "https://example.test/result/202")
        self.assertEqual(records[1]["status"], "Rejected")
        self.assertEqual(records[1]["date_added"], "Added on Sep 13, 2025")
        self.assertEqual(records[1]["us_or_international"], "American")
        self.assertEqual(records[2]["program"], "Computational Biology")
        self.assertEqual(records[2]["degree"], "Masters")
        self.assertEqual(records[3]["program"], "Physics department")
        self.assertEqual(records[4]["program"], "Other University")
        self.assertEqual(records[4]["degree"], "MFA")
        self.assertEqual(records[4]["us_or_international"], "Other")
        self.assertNotIn("program", records[5])
        self.assertEqual(records[5]["date_added"], "Added on Sep 14, 2025")
        self.assertEqual(self.scraper.parse_admissions_data(""), [])

    # Check parser fallbacks for subrow links, alternate dates, and long comments.
    def test_parser_fallback_fields(self):
        html = """
        <table>
          <tr><td>College</td><td>Computer Science Accepted</td></tr>
          <tr><td><a href="/result/303">Result</a></td></tr>
          <tr><td>College Two</td><td>Physics Accepted Sep 15, 2025</td><td>unknown</td></tr>
          <tr><td>College Three</td><td>History Accepted Sep 16, 2025</td></tr>
          <tr><td>College Four</td><td>Biology Rejected</td></tr>
          <tr><td><p>Accepted after months of thoughtful review</p></td></tr>
        </table>
        """
        original_clean_text = scrape.clean_text
        raw_url = "https://example.test/result/404"

        # Simulate URL normalization rejecting an otherwise valid result URL.
        def clean_url_as_empty(value):
            if value == raw_url:
                return ""
            return original_clean_text(value)

        scrape.clean_text = clean_url_as_empty
        try:
            linked_and_dated = self.scraper.parse_admissions_data(html)
            rejected_url = self.scraper.parse_admissions_data(
                '<table><tr><td>School</td><td>CS Accepted '
                '<a href="/result/404">Result</a></td></tr></table>'
            )
        finally:
            scrape.clean_text = original_clean_text

        self.assertEqual(linked_and_dated[0]["url"], "https://example.test/result/303")
        self.assertEqual(linked_and_dated[1]["date_added"], "Added on Sep 15, 2025")
        self.assertEqual(linked_and_dated[2]["date_added"], "Added on Sep 16, 2025")
        self.assertIn("comments", linked_and_dated[3])
        self.assertNotIn("url", rejected_url[0])

    # Check saved-file ingestion, deduplication, and scraper JSON output.
    def test_saved_file_and_scrape_wrapper(self):
        row = "<tr><td>Stanford</td><td>CS track Accepted Fall 2026</td></tr>"
        html = f"<table>{row}{row}</table>"
        with tempfile.TemporaryDirectory() as directory:
            html_file = os.path.join(directory, "saved.html")
            output_file = os.path.join(directory, "records.json")
            with open(html_file, "w", encoding="utf-8") as saved_page:
                saved_page.write(html)

            self.assertEqual(scrape.scrape_data(html_file=os.path.join(directory, "missing.html")), [])
            records = scrape.scrape_data(html_file=html_file)
            self.assertEqual(len(records), 1)
            scrape.save_data(records, output_file)
            with open(output_file, encoding="utf-8") as saved_records:
                self.assertEqual(json.load(saved_records), records)

            original_scrape_data = scrape.scrape_data
            scrape.scrape_data = lambda **kwargs: records
            try:
                result = self.scraper.scrape(output_file=output_file)
            finally:
                scrape.scrape_data = original_scrape_data
            self.assertEqual(result, records)

            original_scrape_data = scrape.scrape_data
            scrape.scrape_data = lambda **kwargs: []
            try:
                self.assertEqual(self.scraper.scrape(output_file=output_file), [])
            finally:
                scrape.scrape_data = original_scrape_data

    # Check directory filtering, threaded parsing, and parse-error recovery.
    def test_directory_scraping(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, contents in (
                ("first.html", "<table><tr><td>Stanford</td><td>CS Accepted</td></tr></table>"),
                ("second.htm", "<table><tr><td>MIT</td><td>CS Rejected</td></tr></table>"),
                ("ignored.txt", "not html"),
            ):
                with open(os.path.join(directory, name), "w", encoding="utf-8") as page:
                    page.write(contents)
            records = scrape.scrape_data(html_dir=directory, allowed_root=directory)
            self.assertEqual({record["program"] for record in records}, {"CS, Stanford", "CS, MIT"})

        class ErrorAwareScraper:
            # Track the current saved-file parse input.
            def __init__(self):
                self.current = ""

            # Accept the saved page and return its text as the parser input.
            def _fetch_html(self, url):
                return url

            # Raise for the broken file and return one record for a good file.
            def parse_admissions_data(self, html):
                if html == "bad":
                    raise ValueError("invalid page")
                return [{"url": html}]

        with tempfile.TemporaryDirectory() as directory:
            for name, contents in (("broken.html", "bad"), ("valid.html", "good")):
                with open(os.path.join(directory, name), "w", encoding="utf-8") as page:
                    page.write(contents)
            original_scraper = scrape.GradCafeScraper
            scrape.GradCafeScraper = ErrorAwareScraper
            try:
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    records = scrape.scrape_data(html_dir=directory)
            finally:
                scrape.GradCafeScraper = original_scraper
        self.assertEqual(records, [{"url": "good"}])
        self.assertIn("Batch Error", output.getvalue())

    # Drive scrape_data through the fake live-page sequence.
    def run_live_scrape(
        self, pages, allowed=True, target_row=0, max_pages=1, clock_values=None
    ):
        class PageScraper:
            # Store scripted pages and current-page state.
            def __init__(self):
                self.pages = list(pages)
                self.current = None

            # Return the scripted robots permission.
            def _check_robots_permission(self):
                return allowed

            # Return the stable initial page URL.
            def _build_url(self, page=1):
                return "page-1"

            # Pop the next page and remember its parsing data.
            def _fetch_html(self, url):
                self.current = self.pages.pop(0)
                return self.current["html"]

            # Return records associated with the current page.
            def parse_admissions_data(self, html):
                return self.current["records"]

            # Return the current page's next link.
            def _next_page_url(self, html):
                return self.current["next"]

        original_scraper = scrape.GradCafeScraper
        original_time = scrape.time.time
        original_sleep = scrape.time.sleep
        original_uniform = scrape.random.uniform
        ticks = iter(clock_values if clock_values is not None else range(1, 100))
        scrape.GradCafeScraper = PageScraper
        scrape.time.time = lambda: next(ticks)
        scrape.time.sleep = lambda seconds: None
        scrape.random.uniform = lambda low, high: 2.0
        try:
            return scrape.scrape_data(
                max_pages=max_pages, target_row=target_row
            )
        finally:
            scrape.GradCafeScraper = original_scraper
            scrape.time.time = original_time
            scrape.time.sleep = original_sleep
            scrape.random.uniform = original_uniform

    # Check live scraping stop conditions, pagination, and target truncation.
    def test_live_scraping(self):
        self.assertEqual(self.run_live_scrape([], allowed=False), [])
        self.assertEqual(self.run_live_scrape([{"html": None, "records": [], "next": None}]), [])
        self.assertEqual(self.run_live_scrape([{"html": "page", "records": [], "next": None}]), [])
        self.assertEqual(
            self.run_live_scrape([
                {"html": "one", "records": [{"url": "same"}], "next": "page-2"},
                {"html": "two", "records": [{"url": "same"}], "next": None},
            ], max_pages=2),
            [{"url": "same"}],
        )
        self.assertEqual(
            self.run_live_scrape([
                {"html": "one", "records": [{"url": "one"}, {"url": "two"}], "next": None}
            ], target_row=1),
            [{"url": "one"}],
        )
        self.assertEqual(
            self.run_live_scrape([
                {"html": "one", "records": [{"value": 1}], "next": None}
            ]),
            [{"value": 1}],
        )
        self.assertEqual(
            self.run_live_scrape(
                [{"html": "one", "records": [{"url": "one"}], "next": None}],
                target_row=1,
                clock_values=[2, 1],
            ),
            [{"url": "one"}],
        )

    # Check scraper CLI saves results and leaves output absent for empty data.
    def test_scraper_cli(self):
        row = "<tr><td>Stanford</td><td>CS Accepted</td></tr>"
        with tempfile.TemporaryDirectory() as directory:
            html_file = "page.html"
            output_file = "output.json"
            original_argv = sys.argv
            original_cwd = os.getcwd()
            try:
                os.chdir(directory)
                with open(html_file, "w", encoding="utf-8") as page:
                    page.write(f"<table>{row}</table>")
                sys.argv = ["scrape.py", "--file", html_file, "--output", output_file]
                with contextlib.redirect_stdout(io.StringIO()):
                    runpy.run_path(scrape.__file__, run_name="__main__")
                self.assertTrue(os.path.exists(output_file))
                os.remove(output_file)
                sys.argv = ["scrape.py", "--file", "missing.html", "--output", output_file]
                with contextlib.redirect_stdout(io.StringIO()):
                    runpy.run_path(scrape.__file__, run_name="__main__")
                self.assertFalse(os.path.exists(output_file))

                for arguments in (
                    ["--file", os.path.join("..", "outside.html"), "--output", output_file],
                    ["--file", html_file, "--output", os.path.join("..", "escape.json")],
                ):
                    sys.argv = ["scrape.py", *arguments]
                    with contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as error:
                            runpy.run_path(scrape.__file__, run_name="__main__")
                    self.assertEqual(error.exception.code, 2)
            finally:
                sys.argv = original_argv
                os.chdir(original_cwd)