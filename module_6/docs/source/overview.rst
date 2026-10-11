Project Overview
================

Grad Cafe Analytics stores applicant-submitted admissions results in PostgreSQL,
calculates summary statistics, and displays selected results through a Flask page.
The source code is in ``module_4/src``; these docs and the pytest suite are in
``module_4/docs`` and ``module_4/tests``.

Data paths
----------

There are two ways data enters the ``applicants`` table:

1. **Initial import:** ``load_data.py`` reads the checked-in
   ``llm_extend_applicant_data.json`` export, normalizes legacy keys, and inserts
   those records.
2. **New results:** the Flask **Pull Data** action starts ``pull_data.py`` as a
   subprocess. That script checks saved result URLs, asks ``scrape.py`` to parse
   new pages, and inserts records whose URLs are not already present.

The Flask page runs its SQL queries against PostgreSQL on each ``GET /`` request.
The **Update Analysis** action does not scrape or mutate the database; it returns a
status message and the next page load queries the latest saved data.

Analysis options
----------------

- ``query_data.py`` runs the assignment's reporting queries as raw PostgreSQL SQL.
- ``orm_queries.py`` implements corresponding query functions using SQLAlchemy.
- ``app/app.py`` runs three page queries and renders the international percentage,
  the leading Fall 2026 PhD Computer Science university, and Fall 2026 Master's
  Computer Science score averages.

Interpretation
--------------

Grad Cafe results are voluntary self-reports, not a random sample of applicants.
Missing scores, inconsistent program names, and reporting bias limit how broadly
the results can be generalized. The reported counts describe Grad Cafe submissions,
not the full applicant population; averages may also be affected by missing scores
and inconsistent program labels.