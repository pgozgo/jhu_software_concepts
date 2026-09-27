"""Convert scraped applicant records and insert them into PostgreSQL.

The loader accepts current JSON keys and legacy spellings used by older Grad Cafe
exports.
"""

import json
import os
import re
from datetime import datetime

import psycopg


def _number(value):
    """Extract the first numeric value from a scraped field.

    Args:
        value (object | None): Raw score value from JSON.

    Returns:
        float | None: Parsed score, or ``None`` when no number is present.
    """
    if value is None:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def _date(value):
    """Parse a Grad Cafe date string into a Python date.

    Args:
        value (str | None): Date such as ``Added on Sep 12, 2026``.

    Returns:
        datetime.date | None: Parsed date, or ``None`` for an empty value.

    Raises:
        ValueError: If a non-empty value does not match the expected format.
    """
    if not value:
        return None
    text = re.sub(r"^Added on\s+", "", str(value), flags=re.IGNORECASE)
    return datetime.strptime(text, "%b %d, %Y").date()


def _value(applicant, key, legacy_key=None):
    """Read a preferred JSON key, falling back to a legacy key.

    Args:
        applicant (dict[str, object]): Applicant record from JSON.
        key (str): Preferred key name.
        legacy_key (str | None): Older key name checked when ``key`` is absent.

    Returns:
        object | None: Value from the preferred or legacy key.
    """
    if key in applicant:
        return applicant[key]
    return applicant.get(legacy_key) if legacy_key else None


def _applicant_values(applicant):
    """Return applicant fields in the database insert-column order.

    Args:
        applicant (dict[str, object]): JSON applicant record.

    Returns:
        tuple[object, ...]: Fourteen values matching the INSERT statement order.
    """
    return (
        applicant.get("program"),
        applicant.get("comments"),
        _date(applicant.get("date_added")),
        applicant.get("url"),
        applicant.get("status"),
        applicant.get("term"),
        _value(applicant, "us_or_international", "US/International"),
        _number(_value(applicant, "gpa", "GPA")),
        _number(_value(applicant, "gre", "GRE")),
        _number(_value(applicant, "gre_v", "GRE-V")),
        _number(_value(applicant, "gre_aw", "GRE-AW")),
        _value(applicant, "degree", "Degree"),
        _value(applicant, "llm_generated_program", "llm-generated-program"),
        _value(applicant, "llm_generated_university", "llm-generated-university"),
    )


def load_data_to_db(json_file, conn_info):
    """Load every applicant in a JSON file into the applicants table.

    Args:
        json_file (str | os.PathLike[str]): Path to a JSON array of records.
        conn_info (str): PostgreSQL connection string.

    Returns:
        None

    Raises:
        OSError: If the JSON file cannot be opened.
        json.JSONDecodeError: If the file does not contain valid JSON.
        psycopg.Error: If PostgreSQL rejects the insert.
    """
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    with psycopg.connect(conn_info) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO applicants (
                    program, comments, date_added, url, status, term,
                    us_or_international, gpa, gre, gre_v, gre_aw, degree,
                    llm_generated_program, llm_generated_university
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (_applicant_values(applicant) for applicant in data),
            )
        print(f"Loaded {len(data)} applicants into the database.")
    print("Data loading complete.")


if __name__ == "__main__":
    json_file = os.path.join(
        os.path.dirname(__file__), "llm_extend_applicant_data.json"
    )
    conn_info = os.getenv("DATABASE_URL")
    if not conn_info:
        raise RuntimeError("DATABASE_URL must be set before loading data")
    load_data_to_db(json_file, conn_info)
