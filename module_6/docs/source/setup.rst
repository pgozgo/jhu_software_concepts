Setup and Usage
===============

Requirements
------------

- Python 3.10 or later.
- PostgreSQL for the application and real database integration tests.
- The packages listed in ``module_4/requirements.txt``.

From the repository root, install dependencies with:

.. code-block:: console

   python -m pip install -r module_4/requirements.txt

Database configuration
----------------------

Set ``DATABASE_URL`` to a PostgreSQL connection string for the application and
command-line scripts. For example, in PowerShell:

.. code-block:: powershell

   $env:DATABASE_URL = "postgresql://postgres:password@127.0.0.1:5432/gradcafe"

The ``applicants`` table must exist before loading records or opening the analysis
page. ``src/create_database.py`` creates the table; its current ``main()`` contains
local connection defaults, so adjust those values to match the local PostgreSQL
server before running it:

.. code-block:: console

   cd module_4
   python src/create_database.py

Then, from ``module_4``:

.. code-block:: console

   python src/load_data.py
   python src/clean_data.py
   python src/query_data.py
   python src/orm_queries.py

``clean_data.py`` normalizes existing rows by default. Use ``--reset`` only when
you intentionally want to delete all applicant rows and restart the primary key.

Run the web application
-----------------------

With ``DATABASE_URL`` set and the table populated, start the Flask server from the
repository root:

.. code-block:: console

   cd module_4
   python src/app/app.py

Open ``http://127.0.0.1:8080/``. **Pull Data** starts ``src/pull_data.py`` in a
subprocess and requires network access to Grad Cafe. **Update Analysis** does not
trigger a scrape.

Run tests and coverage
----------------------

From the repository root:

.. code-block:: console

   python -m pytest -c module_4/pytest.ini

The configured run reports coverage and fails below 100%. The PostgreSQL-backed
schema and end-to-end tests use ``TEST_DATABASE_URL``; set it to a dedicated,
disposable test database to run them locally. If it is unset, those tests skip.
The GitHub Actions workflow starts PostgreSQL and supplies both database URLs.

To save the terminal report in PowerShell:

.. code-block:: powershell

   python -m pytest -c module_4/pytest.ini 2>&1 |
       Tee-Object -FilePath module_4/coverage_summary.txt