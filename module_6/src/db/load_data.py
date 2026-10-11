"""Load the cleaned applicant JSON dataset into PostgreSQL."""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg import sql

DEFAULT_DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "applicant_data.json"
APPLICANT_COLUMNS = (
    "program",
    "comments",
    "date_added",
    "url",
    "status",
    "term",
    "us_or_international",
    "gpa",
    "gre",
    "gre_v",
    "gre_aw",
    "degree",
    "llm_generated_program",
    "llm_generated_university",
)
INSERT_SQL = sql.SQL(
    "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO NOTHING"
).format(
    sql.Identifier("applicants"),
    sql.SQL(", ").join(map(sql.Identifier, APPLICANT_COLUMNS)),
    sql.SQL(", ").join(map(sql.Placeholder, APPLICANT_COLUMNS)),
    sql.Identifier("url"),
)
INGESTION_WATERMARKS_SQL = sql.SQL(
    """CREATE TABLE IF NOT EXISTS {} (
        source TEXT PRIMARY KEY,
        last_seen TEXT,
        updated_at TIMESTAMPTZ DEFAULT now()
    )"""
).format(sql.Identifier("ingestion_watermarks"))
ANALYTICS_VIEW_SQL = {
    "applicant_international_summary": sql.SQL(
        """CREATE MATERIALIZED VIEW IF NOT EXISTS {} AS
        SELECT ROUND(
            100.0 * COUNT(*) FILTER (
                WHERE us_or_international = 'International'
            ) / NULLIF(COUNT(*) FILTER (
                WHERE NULLIF(TRIM(us_or_international), '') IS NOT NULL
            ), 0            ),
            2
        ) AS percent_international
        FROM {}"""
    ).format(
        sql.Identifier("applicant_international_summary"),
        sql.Identifier("applicants"),
    ),
    "applicant_university_summary": sql.SQL(
        """CREATE MATERIALIZED VIEW IF NOT EXISTS {} AS
        SELECT TRIM(SPLIT_PART(program, ',', 2)) AS university,
               COUNT(*) AS applicant_count
        FROM {}
        WHERE term = 'Fall 2026'
          AND degree = 'PhD'
          AND program ILIKE '%Computer Science%'
          AND program LIKE '%,%'
        GROUP BY university"""
    ).format(
        sql.Identifier("applicant_university_summary"),
        sql.Identifier("applicants"),
    ),
    "applicant_score_summary": sql.SQL(
        """CREATE MATERIALIZED VIEW IF NOT EXISTS {} AS
        SELECT ROUND(AVG(gpa)::numeric, 2) AS avg_gpa,
               ROUND(AVG(gre)::numeric, 2) AS avg_gre,
               ROUND(AVG(gre_v)::numeric, 2) AS avg_gre_v,
               ROUND(AVG(gre_aw)::numeric, 2) AS avg_gre_aw
        FROM {}
        WHERE term = 'Fall 2026'
          AND degree ILIKE '%master%'
          AND program ILIKE '%Computer Science%'"""
    ).format(
        sql.Identifier("applicant_score_summary"),
        sql.Identifier("applicants"),
    ),
}
REFRESH_ANALYTICS_SQL = {
    name: sql.SQL("REFRESH MATERIALIZED VIEW {}").format(sql.Identifier(name))
    for name in ANALYTICS_VIEW_SQL
}
APPLICANTS_EXIST_SQL = sql.SQL(
    "SELECT EXISTS (SELECT 1 FROM {})"
).format(sql.Identifier("applicants"))
SEED_WATERMARK_SQL = sql.SQL(
    """INSERT INTO {} (source, last_seen)
       SELECT {}, MAX(SUBSTRING(url FROM '/result/([0-9]+)')::BIGINT)::TEXT
       FROM {}
       WHERE url ~ '/result/[0-9]+'
       HAVING MAX(SUBSTRING(url FROM '/result/([0-9]+)')::BIGINT) IS NOT NULL
       ON CONFLICT (source) DO NOTHING"""
).format(
    sql.Identifier("ingestion_watermarks"),
    sql.Placeholder(),
    sql.Identifier("applicants"),
)
INGESTION_SOURCE = "gradcafe"
OWNER_ROLE = os.getenv("DB_OWNER_ROLE", "gradcafe_owner")
MAINTENANCE_ROLE = os.getenv("DB_MAINTENANCE_USER", "gradcafe_maintenance")
APP_ROLE = os.getenv("DB_APP_USER", "gradcafe_app")
SET_OWNER_ROLE_SQL = sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(OWNER_ROLE))
SET_MAINTENANCE_ROLE_SQL = sql.SQL(
    "SET LOCAL ROLE {}"
).format(sql.Identifier(MAINTENANCE_ROLE))


def _number(value):
    """Parse the first numeric value from an applicant field."""
    if value is None:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def _date(value):
    """Parse a Grad Cafe date or return ``None`` for an empty value."""
    if not value:
        return None
    text = re.sub(r"^Added on\s+", "", str(value), flags=re.IGNORECASE)
    return datetime.strptime(text, "%b %d, %Y").date()


def applicant_values(applicant):
    """Map current and legacy JSON field names to the SQL insert shape."""
    def value(key, legacy=None):
        return applicant[key] if key in applicant else applicant.get(legacy) if legacy else None

    return {
        "program": applicant.get("program"),
        "comments": applicant.get("comments"),
        "date_added": _date(applicant.get("date_added")),
        "url": applicant.get("url"),
        "status": applicant.get("status"),
        "term": applicant.get("term"),
        "us_or_international": value("us_or_international", "US/International"),
        "gpa": _number(value("gpa", "GPA")),
        "gre": _number(value("gre", "GRE")),
        "gre_v": _number(value("gre_v", "GRE-V")),
        "gre_aw": _number(value("gre_aw", "GRE-AW")),
        "degree": value("degree", "Degree"),
        "llm_generated_program": value("llm_generated_program", "llm-generated-program"),
        "llm_generated_university": value("llm_generated_university", "llm-generated-university"),
    }


def initialize_database_objects(cursor):
    """Create worker metadata and UI summary views if they do not exist."""
    cursor.execute(SET_OWNER_ROLE_SQL)
    statement = INGESTION_WATERMARKS_SQL
    cursor.execute(statement)
    cursor.execute(SET_MAINTENANCE_ROLE_SQL)
    for statement in ANALYTICS_VIEW_SQL.values():
        cursor.execute(statement)
    for view_name in ANALYTICS_VIEW_SQL:
        statement = sql.SQL("GRANT SELECT ON {} TO {}").format(
            sql.Identifier(view_name),
            sql.Identifier(APP_ROLE),
        )
        cursor.execute(statement)


def refresh_analytics_views(cursor):
    """Refresh each materialized summary within the caller's transaction."""
    cursor.execute(SET_MAINTENANCE_ROLE_SQL)
    for statement in REFRESH_ANALYTICS_SQL.values():
        cursor.execute(statement)


def seed_watermark_from_applicants(cursor):
    """Seed an absent Grad Cafe watermark from imported result IDs."""
    cursor.execute(SEED_WATERMARK_SQL, (INGESTION_SOURCE,))


def load_data_to_db(json_file, database_url):
    """Initialize an empty table from JSON; duplicate URLs are skipped."""
    with open(json_file, "r", encoding="utf-8") as data_file:
        records = json.load(data_file)
    if not isinstance(records, list):
        raise ValueError("Applicant data must be a JSON array")

    loaded = 0
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            initialize_database_objects(cursor)
            cursor.execute(APPLICANTS_EXIST_SQL)
            if not cursor.fetchone()[0]:
                for start in range(0, len(records), 1000):
                    batch = [
                        applicant_values(row)
                        for row in records[start:start + 1000]
                    ]
                    cursor.executemany(INSERT_SQL, batch)
                    loaded += cursor.rowcount
            seed_watermark_from_applicants(cursor)
            refresh_analytics_views(cursor)
    return loaded


def main():
    """Load a selected JSON file using the configured database URL."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_DATA_FILE)
    args = parser.parse_args()
    database_url = os.getenv("SETUP_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "SETUP_DATABASE_URL or DATABASE_URL must be configured before loading applicant data"
        )
    loaded = load_data_to_db(args.file, database_url)
    if loaded:
        print(f"Loaded {loaded} applicant records from {args.file}.")
    else:
        print("Applicant table already contains data; initial load skipped.")


if __name__ == "__main__":
    main()
