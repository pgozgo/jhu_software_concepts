"""
Module 3: Load Applicant Data into Database
This module provides functionality to load applicant data from a JSON file into a PostgreSQL database.
"""

import json
import os
import re
from datetime import datetime

import psycopg

def _number(value):
    # Extract the first numeric value from a scraped field.
    if value is None:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None

def _date(value):
    # Convert values such as 'Added on Sep 12, 2026' to a database date.
    if not value:
        return None
    text = re.sub(r"^Added on\s+", "", str(value), flags=re.IGNORECASE)
    return datetime.strptime(text, "%b %d, %Y").date()

def _value(applicant, key, legacy_key=None):
    # Retrieve the value for a given key, falling back to a legacy key if necessary.
    if key in applicant:
        return applicant[key]
    return applicant.get(legacy_key) if legacy_key else None

def _applicant_values(applicant):
    # Map applicant_data.json keys to the applicants table columns.
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
    # Load applicant data from the specified JSON file into the PostgreSQL database.
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    with psycopg.connect(conn_info) as conn:
        with conn.cursor() as cur:
            cur.executemany( # Insert multiple applicant records into the database.
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

# how to run:
# Ensure that the DATABASE_URL environment variable is set to the connection string for your PostgreSQL database before running this script.
# i.e) $env:DATABASE_URL = "postgresql://username:password@localhost:5432/mydatabase"
# check) $env:DATABASE_URL ( should show the current value of the DATABASE_URL environment variable )
# python load_data.py