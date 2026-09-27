"""Normalize applicant values and maintain the PostgreSQL applicants table.

The command-line interface cleans stored text and numeric values by default. Pass
``--reset`` to delete all rows and restart the table's serial primary key.
"""

import os
import re
import argparse

import psycopg


TEXT_COLUMNS = (
    "program",
    "comments",
    "url",
    "status",
    "term",
    "us_or_international",
    "degree",
    "llm_generated_program",
    "llm_generated_university",
)
NUMERIC_COLUMNS = ("gpa", "gre", "gre_v", "gre_aw")


def _clean_text(value):
    """Normalize whitespace and map empty values to ``None``.

    Args:
        value (object | None): Value read from a text column.

    Returns:
        str | None: Normalized text, or ``None`` for null/blank values.
    """
    # Normalize whitespace and store blank text as NULL.
    if value is None:
        return None
    cleaned_value = re.sub(r"\s+", " ", str(value)).strip()
    return cleaned_value or None


def _clean_number(value):
    """Convert numbers or extract the first number from scraped text.

    Args:
        value (object | None): Raw value from a numeric database column.

    Returns:
        float | None: Parsed numeric value, or ``None`` when no number exists.
    """
    # Keep numeric database values numeric and extract numbers from scraped text.
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def clean_applicant_data(applicant):
    """Return a cleaned copy of an applicant row.

    Args:
        applicant (dict[str, object]): Row keyed by applicants-table columns.

    Returns:
        dict[str, object]: Copy with normalized text and numeric values.
    """
    # Clean one database record without changing its primary key.
    cleaned_applicant = dict(applicant)

    for column in TEXT_COLUMNS:
        cleaned_applicant[column] = _clean_text(applicant.get(column))

    for column in NUMERIC_COLUMNS:
        cleaned_applicant[column] = _clean_number(applicant.get(column))

    return cleaned_applicant


def clean_database(conn_info):
    """Clean all applicant rows and update them in one transaction.

    Args:
        conn_info (str): PostgreSQL connection string.

    Returns:
        None
    """
    # Read, clean, and update all existing applicant records in one transaction.
    with psycopg.connect(conn_info) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT p_id, program, comments, url, status, term,
                       us_or_international, degree, llm_generated_program,
                       llm_generated_university, gpa, gre, gre_v, gre_aw
                FROM applicants
                """
            )
            columns = [description.name for description in cursor.description]
            applicants = [
                clean_applicant_data(dict(zip(columns, row)))
                for row in cursor.fetchall()
            ]

            cursor.executemany(
                """
                UPDATE applicants
                SET program = %s,
                    comments = %s,
                    url = %s,
                    status = %s,
                    term = %s,
                    us_or_international = %s,
                    degree = %s,
                    llm_generated_program = %s,
                    llm_generated_university = %s,
                    gpa = %s,
                    gre = %s,
                    gre_v = %s,
                    gre_aw = %s
                WHERE p_id = %s
                """,
                (
                    (
                        applicant["program"],
                        applicant["comments"],
                        applicant["url"],
                        applicant["status"],
                        applicant["term"],
                        applicant["us_or_international"],
                        applicant["degree"],
                        applicant["llm_generated_program"],
                        applicant["llm_generated_university"],
                        applicant["gpa"],
                        applicant["gre"],
                        applicant["gre_v"],
                        applicant["gre_aw"],
                        applicant["p_id"],
                    )
                    for applicant in applicants
                ),
            )

    print(f"Cleaned {len(applicants)} applicants in the database.")


def reset_database(conn_info):
    """Delete all applicant rows and restart the serial primary key.

    Args:
        conn_info (str): PostgreSQL connection string.

    Returns:
        None
    """
    # Delete all applicant rows and restart the SERIAL primary key.
    with psycopg.connect(conn_info) as connection:
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE applicants RESTART IDENTITY")

    print("Applicants table reset.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clean existing applicant data or reset the applicants table."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all applicants and restart p_id from 1.",
    )
    args = parser.parse_args()

    conn_info = os.getenv("DATABASE_URL")
    if not conn_info:
        raise RuntimeError("DATABASE_URL must be set before cleaning data")

    if args.reset:
        reset_database(conn_info)
    else:
        clean_database(conn_info)

# how to run:
# python clean_data.py --reset   # to reset the database
# python clean_data.py           # to clean the database

# from command line, you can run the script as follows:
# python -c "import os, psycopg; conn=psycopg.connect(os.environ['DATABASE_URL']); conn.execute('TRUNCATE TABLE applicants RESTART IDENTITY'); conn.commit(); conn.close(); print('Applicants table reset.')"
# python clean_data.py --reset   # to reset the database
# python clean_data.py           # to clean the database