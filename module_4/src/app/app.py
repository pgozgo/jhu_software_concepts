"""Flask web application for live Grad Cafe applicant analysis.

The application reads PostgreSQL through ``DATABASE_URL``. ``POST /pull-data``
starts ``pull_data.py`` in a subprocess; ``POST /update-analysis`` only refreshes
the analysis view and never starts a scrape.
"""

import os
import subprocess
import sys
import threading

from flask import Flask, flash, redirect, render_template, url_for
import psycopg

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))

PULL_DATA_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pull_data.py")

# Tracks the running "Pull Data" subprocess (if any) so a second pull can't start concurrently.
_pull_process = None
_pull_lock = threading.Lock()


@app.after_request
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


def _pull_in_progress():
    """Return whether the current pull subprocess is still running.

    Returns:
        bool: ``True`` while the process has no exit code; otherwise ``False``.
    """
    global _pull_process
    with _pull_lock:
        return _pull_process is not None and _pull_process.poll() is None


@app.route('/pull-data', methods=['POST'])
def pull_data():
    """Start the background data pull unless another pull is running.

    Returns:
        flask.Response | tuple[str, int]: Redirect to the analysis page when a
        pull starts, or a message with HTTP 409 when the app is already busy.
    """
    global _pull_process
    with _pull_lock:
        if _pull_process is not None and _pull_process.poll() is None:
            return "A data pull is already running. Please wait for it to finish.", 409
        else:
            _pull_process = subprocess.Popen(
                [sys.executable, PULL_DATA_SCRIPT],
                env=os.environ.copy(),
            )
            flash("Pull Data started. New Grad Cafe entries will be added shortly.", "info")
    return redirect(url_for('index'))


@app.route('/update-analysis', methods=['POST'])
def update_analysis():
    """Refresh the analysis page without starting a scrape.

    Returns:
        flask.Response | tuple[str, int]: Redirect when idle, or a message with
        HTTP 409 while a pull subprocess is running.
    """
    # This never triggers a scrape; it only re-runs the analysis queries below.
    if _pull_in_progress():
        return (
            "New data is currently being retrieved. Showing the latest results "
            "already saved in the database.",
            409,
        )
    flash("Analysis updated with the most current data in the database.", "info")
    return redirect(url_for('index'))


@app.route('/')
def index():
    """Query PostgreSQL and render the applicant analysis page.

    Returns:
        flask.Response: Rendered HTML containing the percentage, Question 10,
        and Question 11 results.

    Raises:
        RuntimeError: If ``DATABASE_URL`` is not configured.
        psycopg.Error: If a database query fails.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set before starting the app")

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

    return render_template(
        "index.html",
        percent_international=percent_international,
        q10_university_counts=q10_university_counts,
        q11_averages=q11_averages,
        pull_running=_pull_in_progress(),
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

# how to run the app:
# 1. Set the DATABASE_URL environment variable to point to your PostgreSQL database.
# 2. Run this script with Python: python app.py
# 3. Open a web browser and navigate to http://localhost:8080/ to view the application.