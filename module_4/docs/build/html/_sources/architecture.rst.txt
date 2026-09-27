Architecture
============

The application is divided into web, ETL, and persistence/analysis layers.

.. code-block:: text

   Grad Cafe pages                     Existing JSON export
          |                                      |
          v                                      v
   scrape.py: parse results              load_data.py: normalize rows
          |                                      |
          +------------------+-------------------+
                             v
                   PostgreSQL applicants table
                    /          |           \
                   /           |            \
                  v            v             v
          query_data.py   orm_queries.py   clean_data.py
           raw SQL        SQLAlchemy       normalize/reset
                  \            /
                   \          /
                    v        v
                  app/app.py Flask routes
                         |
                         v
                 Jinja HTML templates

Layers
------

Web
~~~

``src/app/app.py`` exposes ``GET /`` for analysis and two POST actions:
``/pull-data`` starts a guarded background subprocess, while ``/update-analysis``
returns ``409`` during an active pull and otherwise flashes a refresh message. The
page is assembled from ``src/app/templates`` and styled by ``src/app/static``.

ETL
~~~

``src/scrape.py`` handles Grad Cafe robots checks, requests, pagination, HTML parsing,
and optional saved-file scraping. ``src/pull_data.py`` uses that scraper, filters
known result URLs, and inserts new records. ``src/load_data.py`` handles the initial
JSON import. ``src/clean_data.py`` normalizes stored text and numbers or resets the
table.

Database and analysis
~~~~~~~~~~~~~~~~~~~~~

``src/create_database.py`` creates the ``applicants`` table. ``src/models.py`` maps
the table to SQLAlchemy's ``Applicant`` class. ``src/query_data.py`` executes raw
SQL; ``src/orm_queries.py`` provides ORM equivalents. The Flask page reads the same
PostgreSQL table directly through ``psycopg``.

Record identity
---------------

Grad Cafe result URLs are treated as record identifiers by the pull process. URLs
already stored in PostgreSQL and repeated URLs within the same fetched page are
excluded before insertion. This keeps repeated pulls from duplicating the same result.