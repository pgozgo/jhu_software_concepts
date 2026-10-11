"""Raw SQL report queries for applicant data."""

import os

import psycopg
from psycopg import sql

INTERNATIONAL_COUNTS_QUERY = sql.SQL(
    """SELECT COUNT(*),
              COUNT(*) FILTER (WHERE us_or_international = {})
       FROM {}"""
).format(
    sql.Placeholder(),
    sql.Identifier("applicants"),
)
INTERNATIONAL_LABEL = "International"


def main():
    """Print a small database summary without connecting during module import."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be configured before querying applicant data")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            statement = INTERNATIONAL_COUNTS_QUERY
            cursor.execute(statement, (INTERNATIONAL_LABEL,))
            total, international = cursor.fetchone()
    percent = round(100 * international / total, 2) if total else 0.0
    print(f"Applicant records: {total}")
    print(f"International applicants: {percent}%")


if __name__ == "__main__":
    main()
