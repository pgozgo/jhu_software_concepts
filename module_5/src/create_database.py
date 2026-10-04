"""Configure PostgreSQL connections and create the applicants table if absent."""

import os

import psycopg2
from dotenv import load_dotenv
from psycopg2 import OperationalError
from sqlalchemy.engine import URL


def database_url_from_environment(prefix="DB", required=True):
    """Build a PostgreSQL URL from DB_* settings.

    ``DATABASE_URL`` is accepted for runtime compatibility; schema setup always
    uses the separate ``DB_SETUP_USER`` and ``DB_SETUP_PASSWORD`` credentials.

    Args:
        prefix (str): Prefix for username and password variables.
        required (bool): Raise an error when configuration is absent or incomplete.

    Returns:
        str | None: Encoded PostgreSQL connection URL, or ``None`` if optional
        configuration is absent.

    Raises:
        RuntimeError: If required connection settings are missing or invalid.
    """
    load_dotenv()
    legacy_url = os.getenv("DATABASE_URL") if prefix == "DB" else None
    if legacy_url:
        return legacy_url

    settings = {
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT"),
        "database": os.getenv("DB_NAME"),
        "username": os.getenv(f"{prefix}_USER"),
        "password": os.getenv(f"{prefix}_PASSWORD"),
    }
    if all(value in (None, "") for value in settings.values()):
        if not required:
            return None
        required_variables = [
            "DB_HOST",
            "DB_PORT",
            "DB_NAME",
            f"{prefix}_USER",
            f"{prefix}_PASSWORD",
        ]
        fallback = " or DATABASE_URL" if prefix == "DB" else ""
        raise RuntimeError(
            f"Set {', '.join(required_variables)}{fallback} "
            "in the environment or .env file"
        )

    missing = [name for name, value in settings.items() if value in (None, "")]
    if missing:
        variable_names = [
            f"{prefix}_{name.upper()}" if name in {"username", "password"}
            else f"DB_{name.upper()}"
            for name in missing
        ]
        raise RuntimeError(
            "Missing database environment variables: " + ", ".join(variable_names)
        )
    try:
        port = int(settings["port"])
    except ValueError as error:
        raise RuntimeError("DB_PORT must be an integer between 1 and 65535") from error
    if not 1 <= port <= 65535:
        raise RuntimeError("DB_PORT must be an integer between 1 and 65535")

    return URL.create(
        "postgresql",
        username=settings["username"],
        password=settings["password"],
        host=settings["host"],
        port=port,
        database=settings["database"],
    ).render_as_string(hide_password=False)


def create_connection(database_url):
    """Connect to PostgreSQL using the supplied environment-derived URL.

    Args:
        database_url (str): PostgreSQL connection URL.

    Returns:
        psycopg2.extensions.connection | None: Connection, or ``None`` if
        psycopg2 raises ``OperationalError``.
    """
    try:
        connection = psycopg2.connect(database_url)
        print("Connection to PostgreSQL DB successful")
    except OperationalError as error:
        print(f"The error '{error}' occurred")
        return None
    return connection


def create_table(connection):
    """Create the applicants table if it does not already exist.

    Args:
        connection (psycopg2.extensions.connection): Open setup-role connection.

    Returns:
        None

    Notes:
        Commits the DDL statement and closes the cursor and connection.
    """
    create_table_query = """
    CREATE TABLE IF NOT EXISTS applicants (
        p_id SERIAL PRIMARY KEY,
        program TEXT,
        comments TEXT,
        date_added DATE,
        url TEXT,
        status TEXT,
        term TEXT,
        us_or_international TEXT,
        gpa FLOAT,
        gre FLOAT,
        gre_v FLOAT,
        gre_aw FLOAT,
        degree TEXT,
        llm_generated_program TEXT,
        llm_generated_university TEXT
    )
    """
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(create_table_query)
        connection.commit()
        print("Applicants table created successfully")
    except OperationalError as error:
        print(f"The error '{error}' occurred")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def main():
    """Create the table using credentials reserved for schema setup."""
    setup_url = database_url_from_environment(prefix="DB_SETUP")
    connection = create_connection(setup_url)
    if connection:
        create_table(connection)


if __name__ == "__main__":
    main()
