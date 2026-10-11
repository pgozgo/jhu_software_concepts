"""Flask applicant dashboard and queue-backed scrape endpoint."""

import os
import re

import psycopg
from psycopg import sql
from flask import Flask, abort, current_app, jsonify, render_template, request

from web.publisher import publish_task

DEFAULT_QUERY_LIMIT = 1
MAX_QUERY_LIMIT = 100
MAX_LIMIT_TEXT_LENGTH = 64
LIMIT_PATTERN = re.compile(r"[+-]?[0-9]+\Z")
HEALTH_CHECK_QUERY = sql.SQL("SELECT 1")
INTERNATIONAL_SUMMARY_QUERY = sql.SQL(
    "SELECT {} FROM {}"
).format(
    sql.Identifier("percent_international"),
    sql.Identifier("applicant_international_summary"),
)
UNIVERSITY_COUNTS_QUERY = sql.SQL(
    "SELECT {}, {} FROM {} "
    "ORDER BY {} DESC, {} LIMIT {}"
).format(
    sql.Identifier("university"),
    sql.Identifier("applicant_count"),
    sql.Identifier("applicant_university_summary"),
    sql.Identifier("applicant_count"),
    sql.Identifier("university"),
    sql.Placeholder(),
)
SCORE_AVERAGES_QUERY = sql.SQL(
    "SELECT {}, {}, {}, {} FROM {}"
).format(
    sql.Identifier("avg_gpa"),
    sql.Identifier("avg_gre"),
    sql.Identifier("avg_gre_v"),
    sql.Identifier("avg_gre_aw"),
    sql.Identifier("applicant_score_summary"),
)


def clamp_query_limit(value):
    """Parse a query limit and constrain it to the supported range."""
    if value is None:
        return DEFAULT_QUERY_LIMIT
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("limit must be an integer")
    if isinstance(value, str):
        if (
            len(value) > MAX_LIMIT_TEXT_LENGTH
            or not value.isascii()
            or not LIMIT_PATTERN.fullmatch(value)
        ):
            raise ValueError("limit must be an integer")
    requested = int(value)
    return min(MAX_QUERY_LIMIT, max(1, requested))


def run_analysis_queries(database_url, limit=DEFAULT_QUERY_LIMIT):
    """Return the values displayed on the applicant dashboard."""
    limit = clamp_query_limit(limit)
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(INTERNATIONAL_SUMMARY_QUERY)
            percent_international = cursor.fetchone()[0]
            cursor.execute(UNIVERSITY_COUNTS_QUERY, (limit,))
            university_counts = cursor.fetchall()
            cursor.execute(SCORE_AVERAGES_QUERY)
            score_averages = cursor.fetchone()

    return {
        "percent_international": percent_international,
        "q10_university_counts": university_counts,
        "q11_averages": score_averages,
    }


def create_app(config=None):
    """Create the Flask app with injectable services for unit tests."""
    application = Flask(__name__)
    application.config.update(
        DATABASE_URL=os.getenv("DATABASE_URL"),
        ANALYSIS_QUERY=run_analysis_queries,
        PUBLISH_TASK=publish_task,
    )
    if config:
        application.config.update(config)

    @application.get("/health")
    def health():
        """Report ready only when PostgreSQL accepts a query."""
        database_url = application.config.get("DATABASE_URL")
        if not database_url:
            return jsonify(ok=False, message="DATABASE_URL is not configured"), 503
        try:
            with psycopg.connect(database_url, connect_timeout=2) as connection:
                connection.execute(HEALTH_CHECK_QUERY)
        except psycopg.Error:
            return jsonify(ok=False, message="database is unavailable"), 503
        return jsonify(ok=True), 200

    @application.get("/", endpoint="index")
    @application.get("/analysis", endpoint="analysis")
    def index():
        """Render the dashboard using current PostgreSQL results."""
        database_url = application.config.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL must be configured before starting the app")
        try:
            limit = clamp_query_limit(request.args.get("limit"))
        except ValueError as error:
            abort(400, description=str(error))
        analysis = application.config["ANALYSIS_QUERY"](database_url, limit)
        return render_template(
            "index.html",
            **analysis,
            pull_running=False,
            query_limit=limit,
        )

    @application.post("/pull-data")
    def pull_data():
        """Enqueue a scrape request for the worker service."""
        try:
            application.config["PUBLISH_TASK"]("scrape_new_data")
        except Exception:  # pylint: disable=broad-exception-caught
            current_app.logger.exception("Could not queue scrape request")
            return jsonify(ok=False, message="Could not queue request"), 503
        return jsonify(
            ok=True,
            queued=True,
            message="Request queued",
        ), 202

    @application.post("/update-analysis")
    def update_analysis():
        """Queue an analytics refresh without holding the HTTP request open."""
        try:
            application.config["PUBLISH_TASK"]("recompute_analytics")
        except Exception:  # pylint: disable=broad-exception-caught
            current_app.logger.exception("Could not queue analytics refresh")
            return jsonify(ok=False, message="Could not queue request"), 503
        return jsonify(
            ok=True,
            queued=True,
            message="Request queued",
        ), 202

    return application


app = create_app()
