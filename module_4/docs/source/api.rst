API Reference
=============

The ``clean.py`` functionality is implemented in ``clean_data.py`` in this
repository. ``query_data.py`` is shown as source rather than imported because its
current design connects to PostgreSQL and executes queries during module import.

Flask application and routes
----------------------------

.. automodule:: app.app
   :members: disable_browser_cache, index, pull_data, update_analysis

Scraper
-------

.. autoclass:: scrape.GradCafeScraper
   :members: _build_url, _check_robots_permission, _fetch_html, _next_page_url, parse_admissions_data, scrape

.. autofunction:: scrape.clean_text

.. autofunction:: scrape.scrape_data

.. autofunction:: scrape.save_data

Database and ETL
----------------

.. automodule:: clean_data
   :members: clean_applicant_data, clean_database, reset_database

.. automodule:: load_data
   :members: load_data_to_db

.. automodule:: pull_data
   :members: main

.. automodule:: create_database
   :members: create_connection, create_table, main

ORM model and queries
---------------------

During the docs build, ``conf.py`` supplies an in-memory SQLite URL only when no
``DATABASE_URL`` is already set. This lets autodoc import the model without a live
PostgreSQL server; it does not alter the application configuration.

.. automodule:: models
   :members: Applicant, Base, Session, engine

.. automodule:: orm_queries
   :members: question_1, question_4, question_5, question_8, question_9, question_10, question_11, main

Raw SQL report
--------------

``query_data.py`` runs queries at import time, so importing it during a docs build
would open a database connection. The complete script is included below without
execution:

.. literalinclude:: ../../src/query_data.py
   :language: python
   :caption: module_4/src/query_data.py