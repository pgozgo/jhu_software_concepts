# Module 3: PostgreSQL Analysis and Flask Application

## Overview / Process

This module takes the applicant records scraped and cleaned in Module 2, loads them into a
PostgreSQL database, analyzes them with both raw SQL and SQLAlchemy, and serves the results
through a small Flask web app. The app also lets a user pull newly available Grad Cafe entries
on demand without leaving the browser.

High-level pipeline:

1. `create_database.py` creates the `applicants` table (if it doesn't already exist).
2. `load_data.py` loads a scraped/cleaned JSON file (Module 2 output) into that table.
3. `clean_data.py` can re-clean existing rows in place, or reset the table entirely.
4. `query_data.py` and `orm_queries.py` answer the assignment's analysis questions using raw
   SQL and SQLAlchemy, respectively.
5. `app/app.py` serves a Flask page showing two of those analyses live from the database, plus
   **Pull Data** and **Update Analysis** buttons described below.
6. `pull_data.py` is invoked by the **Pull Data** button (as a subprocess) to scrape newly
   posted Grad Cafe entries and insert only the ones not already in the database.

## How to Run

1. Install dependencies:
   ```
   pip install -r requirements.txt
   pip install -r ../module_2/requirements.txt
   ```
   (Module 2's scraper/parsing dependencies, e.g. `beautifulsoup4`/`urllib3`, are required
   because `pull_data.py` reuses the Module 2 scraper directly.)
2. Set the `DATABASE_URL` environment variable to point at your PostgreSQL instance, e.g.
   ```
   $env:DATABASE_URL = "postgresql://postgres:abc123@127.0.0.1:5432/postgres"
   ```
3. Create the table: `python create_database.py`
4. Load initial data: `python load_data.py`
5. (Optional) Clean existing rows: `python clean_data.py`
6. Run the analyses:
   - Raw SQL: `python query_data.py`
   - SQLAlchemy: `python orm_queries.py`
7. Start the web app:
   ```
   cd app
   python app.py
   ```
   Then open `http://localhost:8080/`.

## Module 2 `scrape.py` and Data File Notes

- `module_3/scrape.py` is an unmodified copy of `module_2/scrape.py`, kept alongside
  `pull_data.py` for easy, self-contained access (no cross-directory `sys.path` needed).
  `pull_data.py` imports `GradCafeScraper` from this local copy and reuses its existing
  `_check_robots_permission`, `_build_url`, `_fetch_html`, `_next_page_url`, and
  `parse_admissions_data` methods as-is.
- **No changes were made to the checked-in Module 2 JSON files**
  (`applicant_data.json`, `llm_extend_applicant_data.json`, etc.). Those files remain the
  one-time bulk exports used for the initial `load_data.py` load.
- The **Pull Data** flow does not read or write any of those JSON files. Instead,
  `pull_data.py` scrapes live pages, compares result URLs against what's already in the
  `applicants` table, and inserts only new rows directly, skipping the JSON intermediate step
  entirely.

## File Guide

1. **`load_data.py`** — Reads a Module 2 JSON export and bulk-inserts every record into the
   `applicants` table via `psycopg`. Run once to populate the database from a scraped file.
2. **`query_data.py`** — Answers the assignment's analysis questions using hand-written SQL
   executed through `psycopg`. Run directly to print formatted console output.
3. **`models.py`** — Defines the SQLAlchemy `Applicant` model (mapped to the existing
   `applicants` table) plus the shared `engine`/`Session` used by `orm_queries.py`.
4. **`orm_queries.py`** — Repeats the required analysis questions using SQLAlchemy's query
   builder (`select`, `func`, `and_`, `or_`) instead of raw SQL.
5. **`query_results.pdf`** — Exported PDF containing the formatted results from both
   `query_data.py` and `orm_queries.py`, matching the required decimal/percentage formatting.
6. **`limitations.pdf`** — Write-up describing known limitations of the scraped data and
   analysis (e.g. incomplete GRE scores, ambiguous program names, LLM standardization gaps).
7. **Flask application code** (`app/app.py`) — Serves `/` with the two live PostgreSQL
   analyses, plus `POST /pull-data` (starts the Module 2 scrape as a background subprocess,
   guarded so only one can run at a time) and `POST /update-analysis` (re-runs the same
   queries and flashes a status message without starting a scrape).
8. **HTML template(s)** (`app/templates/base.html`, `app/templates/index.html`) — `base.html`
   is the shared page shell (header, flash messages); `index.html` renders the two analysis
   sections and the Pull Data / Update Analysis buttons.
9. **CSS/static files** (`app/static/style.css`) — Styles the page layout, metric cards, flash
   messages, and the two action buttons.
10. **Module 2 scraping code required for Pull Data** — `module_3/scrape.py` (an unmodified
    copy of `module_2/scrape.py`, kept local for easy access) provides the `GradCafeScraper`
    class and helpers that `pull_data.py` imports to fetch and parse new Grad Cafe result pages.
11. **`README.md`** — This file; process overview, run instructions, and a guide to every
    deliverable in this module.
12. **`requirements.txt`** — Python dependencies for the database scripts and Flask app
    (`Flask`, `SQLAlchemy`, `psycopg`).
13. **Screenshots** — Include image captures of:
    - raw SQL console output (`python query_data.py`);
    - SQLAlchemy ORM console output (`python orm_queries.py`); and
    - the running Flask webpage at `http://localhost:8080/`.
14. **`github.txt`** — Contains the SSH URL to the private GitHub repository for this
    assignment (e.g. `git@github.com:<username>/<repo>.git`).

## SQL vs SQLAlchemy Comparison

## Question 1: Fall 2026 Applicant Count

### Raw SQL

```sql
SELECT COUNT(*)
FROM applicants
WHERE term = 'Fall 2026';
```

### SQLAlchemy ORM

```python
statement = (
    select(func.count())
    .select_from(Applicant)
    .where(Applicant.term == "Fall 2026")
)
fall_2026_applicant_count = session.scalar(statement)
```

The raw SQL states the database operation directly, which makes the exact query easy to inspect and debug in PostgreSQL. SQLAlchemy uses Python model attributes instead of handwritten SQL strings, which can make queries easier to maintain when the application already uses ORM models. The ORM also provides an abstraction that can make it easier to move between supported database systems. Direct SQL gives more control over database-specific features and is often more convenient for testing a query independently in a database client.
