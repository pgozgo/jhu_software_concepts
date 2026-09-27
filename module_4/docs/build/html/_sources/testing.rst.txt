Testing Guide
=============

Test structure
--------------

Tests live in ``module_4/tests`` and use ``unittest.TestCase``. Pytest discovers
the test methods and applies class-level pytest markers. Test setup and cleanup use
``setUp`` and ``tearDown``; no shared ``conftest.py`` is required.

Markers
-------

The marker names are registered in ``module_4/pytest.ini``:

``web``
   Flask route registration, page rendering, labels, and app setup.
``buttons``
   Pull Data and Update Analysis requests, busy gating, and URL deduplication.
``analysis``
   Rendered percentage formatting plus raw SQL and ORM query results.
``db``
   Schema, insert, cleaning, loading, and database helper behavior.
``integration``
   Pull/update/render flows and scraper request, parsing, and file paths.

Selectors
---------

Run one group with ``-m``:

.. code-block:: console

   python -m pytest -c module_4/pytest.ini -m web
   python -m pytest -c module_4/pytest.ini -m "db or integration"

Run all tests with coverage from the repository root:

.. code-block:: console

   python -m pytest -c module_4/pytest.ini

The pytest configuration measures ``module_4/src`` and enforces 100% statement
coverage. ``--cov-report=term-missing`` lists missed source lines if the gate fails.

Fixtures and test doubles
-------------------------

The suite uses ``unittest`` setup methods rather than pytest fixture functions.
External behavior is represented by small plain-Python fakes:

- ``FakeCursor``, ``FakeConnection``, and ``FakeDatabase`` return known query rows
  and record SQL writes without contacting PostgreSQL.
- ``FakeScraper`` and ``FakeHttpClient`` provide deterministic HTML, parsed rows,
  HTTP status codes, and request errors without accessing the network.
- ``FakePopen`` and ``FakePullLauncher`` record or synchronously simulate the pull
  subprocess.
- ORM tests use an in-memory SQLite database; database integration tests create
  dedicated schemas inside ``TEST_DATABASE_URL``.

The real PostgreSQL tests skip when ``TEST_DATABASE_URL`` is unset. Always point it
to a disposable test database, not a production database. GitHub Actions provides
a PostgreSQL 16 service for those cases.