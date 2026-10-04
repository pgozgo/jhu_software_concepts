"""Flask web application for live Grad Cafe applicant analysis.

The application reads PostgreSQL settings from the environment or a local
``.env`` file. ``POST /pull-data`` starts ``pull_data.py`` in a subprocess;
``POST /update-analysis`` only refreshes the analysis view.
"""

import os
import subprocess
import sys
import threading

from flask import Flask, jsonify, render_template
import psycopg

if __package__ in (None, ""):
    source_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, source_directory)

from create_database import database_url_from_environment  # pylint: disable=wrong-import-position

PULL_DATA_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pull_data.py")

def disable_browser_cache(response):
    """Prevent browsers from caching live analysis responses.

    Args:
        response (flask.Response): Response produced by a Flask route.

    Returns:
        flask.Response: The same response with no-cache headers added.
    """
    # Analysis values must always be read again from PostgreSQL.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def _pull_in_progress(application):
    """Return whether the current pull subprocess is still running.

    Returns:
        bool: ``True`` while the process has no exit code; otherwise ``False``.
    """
    state = application.extensions["pull_data_state"]
    with state["lock"]:
        process = state["process"]
        return process is not None and process.poll() is None


def pull_data(application):
    """Start the background data pull unless another pull is running.

    Returns:
        flask.Response | tuple[str, int]: Redirect to the analysis page when a
        pull starts, or a message with HTTP 409 when the app is already busy.
    """
    state = application.extensions["pull_data_state"]
    with state["lock"]:
        process = state["process"]
        if process is not None and process.poll() is None:
            return jsonify(busy=True), 409
        runner = application.config["PULL_DATA_RUNNER"]
        state["process"] = runner(
            application.config["PULL_DATA_SCRIPT"], os.environ.copy()
        )
        return jsonify(ok=True), 202


def update_analysis(application):
    """Refresh the analysis page without starting a scrape.

    Returns:
        flask.Response | tuple[str, int]: Redirect when idle, or a message with
        HTTP 409 while a pull subprocess is running.
    """
    # This never triggers a scrape; it only re-runs the analysis queries below.
    if _pull_in_progress(application):
        return jsonify(busy=True), 409
    database_url = application.config.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL or DB_* settings must be set before starting the app")
    application.config["ANALYSIS_QUERY"](database_url)
    return jsonify(ok=True), 200


def index(application):
    """Query PostgreSQL and render the applicant analysis page.

    Returns:
        flask.Response: Rendered HTML containing the percentage, Question 10,
        and Question 11 results.

    Raises:
        RuntimeError: If database connection settings are not configured.
        psycopg.Error: If a database query fails.
    """
    database_url = application.config.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL or DB_* settings must be set before starting the app")

    analysis_query = application.config["ANALYSIS_QUERY"]
    analysis = analysis_query(database_url)

    return render_template(
        "index.html",
        **analysis,
        pull_running=_pull_in_progress(application),
    )


def run_analysis_queries(database_url):
    """Query PostgreSQL for the values rendered on the analysis page.

    Args:
        database_url (str): PostgreSQL connection string.

    Returns:
        dict[str, object]: Template values for international percentage, Question
        10 university counts, and Question 11 score averages.
    """
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ROUND(
                    100.0 * COUNT(*) FILTER (WHERE us_or_international = 'International')
                    / NULLIF(COUNT(*) FILTER (
                        WHERE NULLIF(TRIM(us_or_international), '') IS NOT NULL
                    ), 0),
                    2
                )
                FROM applicants
                """
            )
            percent_international = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT TRIM(SPLIT_PART(program, ',', 2)) AS university,
                       COUNT(*) AS applicant_count
                FROM applicants
                WHERE term = %s
                  AND degree = %s
                  AND program ILIKE %s
                  AND program LIKE %s
                GROUP BY university
                ORDER BY applicant_count DESC, university
                LIMIT 1
                """,
                ("Fall 2026", "PhD", "%Computer Science%", "%,%"),
            )
            q10_university_counts = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    ROUND(AVG(gpa)::numeric, 2),
                    ROUND(AVG(gre)::numeric, 2),
                    ROUND(AVG(gre_v)::numeric, 2),
                    ROUND(AVG(gre_aw)::numeric, 2)
                FROM applicants
                WHERE term = %s
                  AND degree ILIKE %s
                  AND program ILIKE %s
                """,
                ("Fall 2026", "%master%", "%Computer Science%"),
            )
            q11_averages = cursor.fetchone()

    return {
        "percent_international": percent_international,
        "q10_university_counts": q10_university_counts,
        "q11_averages": q11_averages,
    }


def start_pull_process(script_path, environment):
    """Launch the configured pull script as a child process.

    Args:
        script_path (str): Absolute path to ``pull_data.py``.
        environment (dict[str, str]): Environment passed to the child process.

    Returns:
        subprocess.Popen: Handle used to determine whether a pull is running.
    """
    return subprocess.Popen([sys.executable, script_path], env=environment)


def create_app(config=None):
    """Create a Flask app with configurable database and replaceable services.

    Args:
        config (dict[str, object] | None): Flask configuration overrides. Tests
            can supply ``DATABASE_URL``, ``ANALYSIS_QUERY``, and
            ``PULL_DATA_RUNNER`` callables to avoid real PostgreSQL/network work.

    Returns:
        flask.Flask: Configured application with isolated pull-process state.
    """
    application = Flask(__name__)
    application.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", os.urandom(24)),
        DATABASE_URL=database_url_from_environment(required=False),
        PULL_DATA_SCRIPT=PULL_DATA_SCRIPT,
        ANALYSIS_QUERY=run_analysis_queries,
        PULL_DATA_RUNNER=start_pull_process,
    )
    if config:
        application.config.update(config)
    application.secret_key = application.config["SECRET_KEY"]
    application.extensions["pull_data_state"] = {
        "process": None,
        "lock": threading.Lock(),
    }
    application.after_request(disable_browser_cache)
    application.add_url_rule(
        "/", endpoint="index", view_func=lambda: index(application)
    )
    application.add_url_rule(
        "/analysis", endpoint="analysis", view_func=lambda: index(application)
    )
    application.add_url_rule(
        "/pull-data", endpoint="pull_data",
        view_func=lambda: pull_data(application), methods=["POST"]
    )
    application.add_url_rule(
        "/update-analysis", endpoint="update_analysis",
        view_func=lambda: update_analysis(application), methods=["POST"]
    )
    return application


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

# how to run the app:
# 1. Set the DATABASE_URL environment variable to point to your PostgreSQL database.
# 2. Run this script with Python: python app.py
# 3. Open a web browser and navigate to http://localhost:8080/ to view the application.
