'''Test Pull Data and Update Analysis routes.

a. POST /pull-data starts a background pull.
b. POST /update-analysis succeeds when idle.
c. While a pull is active, both routes return 409 and do no work.
'''
from unittest import TestCase

import pytest

import app.app as flask_app_module
from test_flask_page import FakeAnalysisQuery


# Represent a background process with a configurable running state.
class FakeProcess:
    # Store the poll result returned by this fake process.
    def __init__(self, return_code=None):
        self.return_code = return_code

    # Return None while running or a code after completion.
    def poll(self):
        return self.return_code


# Record process launches and return a selected fake process.
class FakePopen:
    # Initialize the process result and call log.
    def __init__(self, process):
        self.process = process
        self.calls = []

    # Record the attempted subprocess launch.
    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.process


# Group action endpoint tests with fake database results.
@pytest.mark.buttons
class TestAnalysisButtons(TestCase):
    # Configure the Flask client and predictable analysis values.
    def setUp(self):
        self.analysis_query = FakeAnalysisQuery()
        self.application = flask_app_module.create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_URL": "postgresql://test/test",
            "ANALYSIS_QUERY": self.analysis_query,
        })
        self.client = self.application.test_client()

    # Verify Pull Data launches one background process.
    def test_pull_starts(self):
        popen = FakePopen(FakeProcess())
        self.application.config["PULL_DATA_RUNNER"] = popen
        # Exercise the POST /pull-data route while no pull is active.
        response = self.client.post("/pull-data")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(popen.calls), 1)
        self.assertEqual(response.get_json(), {"ok": True})

    # Verify a busy update does not access the database or start a process.
    def test_update_busy(self):
        popen = FakePopen(FakeProcess())
        self.application.config["PULL_DATA_RUNNER"] = popen
        self.client.post("/pull-data")
        # Exercise the busy branch of POST /update-analysis.
        response = self.client.post("/update-analysis")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json(), {"busy": True})
        self.assertEqual(len(popen.calls), 1)
        self.assertEqual(self.analysis_query.database_urls, [])

    # Verify a busy pull does not launch another process.
    def test_pull_busy(self):
        popen = FakePopen(FakeProcess())
        self.application.config["PULL_DATA_RUNNER"] = popen
        self.client.post("/pull-data")
        # Exercise the busy branch of POST /pull-data.
        response = self.client.post("/pull-data")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json(), {"busy": True})
        self.assertEqual(len(popen.calls), 1)

    # Verify an idle update redirects to the analysis page.
    def test_update_idle(self):
        # Exercise the idle branch of POST /update-analysis.
        response = self.client.post("/update-analysis")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})
        self.assertEqual(self.analysis_query.database_urls, ["postgresql://test/test"])

    # Check Update Analysis reports missing database configuration.
    def test_update_requires_database_url(self):
        application = flask_app_module.create_app({
            "TESTING": True,
            "DATABASE_URL": None,
            "ANALYSIS_QUERY": self.analysis_query,
        })

        with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
            application.test_client().post("/update-analysis")