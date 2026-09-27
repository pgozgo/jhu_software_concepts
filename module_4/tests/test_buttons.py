'''Test Pull Data and Update Analysis routes.

a. POST /pull-data starts a background pull.
b. POST /update-analysis succeeds when idle.
c. While a pull is active, both routes return 409 and do no work.
'''
import os
from unittest import TestCase

import pytest

import app.app as flask_app_module
from test_flask_page import FakeDatabase


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
        self.original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "postgresql://test/test"
        self.original_connect = flask_app_module.psycopg.connect
        self.database = FakeDatabase()
        flask_app_module.psycopg.connect = self.database.connect
        self.original_popen = flask_app_module.subprocess.Popen
        self.original_pull_process = flask_app_module._pull_process
        flask_app_module._pull_process = None
        flask_app_module.app.config.update(TESTING=True)
        self.client = flask_app_module.app.test_client()

    # Restore app dependencies and the database URL after each route test.
    def tearDown(self):
        flask_app_module.psycopg.connect = self.original_connect
        flask_app_module.subprocess.Popen = self.original_popen
        flask_app_module._pull_process = self.original_pull_process
        if self.original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.original_database_url

    # Verify Pull Data launches one background process.
    def test_pull_starts(self):
        popen = FakePopen(FakeProcess())
        flask_app_module.subprocess.Popen = popen
        # Exercise the POST /pull-data route while no pull is active.
        response = self.client.post("/pull-data", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(popen.calls), 1)
        self.assertIn("Pull Data started", response.get_data(as_text=True))

    # Verify a busy update does not access the database or start a process.
    def test_update_busy(self):
        flask_app_module._pull_process = FakeProcess()
        popen = FakePopen(FakeProcess())
        flask_app_module.subprocess.Popen = popen
        connection_calls = self.database.connection_calls
        # Exercise the busy branch of POST /update-analysis.
        response = self.client.post("/update-analysis")

        self.assertEqual(response.status_code, 409)
        self.assertIn("currently being retrieved", response.get_data(as_text=True))
        self.assertEqual(self.database.connection_calls, connection_calls)
        self.assertEqual(popen.calls, [])

    # Verify a busy pull does not launch another process.
    def test_pull_busy(self):
        flask_app_module._pull_process = FakeProcess()
        popen = FakePopen(FakeProcess())
        flask_app_module.subprocess.Popen = popen
        # Exercise the busy branch of POST /pull-data.
        response = self.client.post("/pull-data")

        self.assertEqual(response.status_code, 409)
        self.assertIn("already running", response.get_data(as_text=True))
        self.assertEqual(popen.calls, [])

    # Verify an idle update redirects to the analysis page.
    def test_update_idle(self):
        # Exercise the idle branch of POST /update-analysis.
        response = self.client.post("/update-analysis", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Analysis updated", response.get_data(as_text=True))