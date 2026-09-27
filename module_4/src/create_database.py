"""Create a PostgreSQL connection and the applicants table when absent.

The ``main`` function currently uses local connection defaults. Adjust them to
match the target PostgreSQL instance before running the script.
"""

import psycopg2
from psycopg2 import OperationalError

def create_connection(db_name, db_user, db_password, db_host, db_port):
    """Connect to PostgreSQL using separate connection parameters.

    Args:
        db_name (str): Database name.
        db_user (str): Database user.
        db_password (str): Password for ``db_user``.
        db_host (str): Database host name or address.
        db_port (str | int): Database port.

    Returns:
        psycopg2.extensions.connection | None: Connection, or ``None`` if
        psycopg2 raises ``OperationalError``.
    """
    connection = None
    try:
        connection = psycopg2.connect(
            database=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port,
        )
        print("Connection to PostgreSQL DB successful")
    except OperationalError as e:
        print(f"The error '{e}' occurred")
    return connection

def create_table(connection):
    """Create the applicants table if it does not already exist.

    Args:
        connection (psycopg2.extensions.connection): Open database connection.

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
    try:
        cursor = connection.cursor()
        cursor.execute(create_table_query)
        connection.commit()
        print("Applicants table created successfully")
    except OperationalError as e:
        print(f"The error '{e}' occurred")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def main():
    """Connect with the script defaults and create the applicants table.

    Returns:
        None
    """
    db_name = "postgres"
    db_user = "postgres"
    db_password = "abc123"
    db_host = "127.0.0.1"
    db_port = "5432"

    connection = create_connection(db_name, db_user, db_password, db_host, db_port)
    if connection:
        create_table(connection)

if __name__ == "__main__":
    main()

# how to run this script:
# python module_3/create_database.py

# to connect to the database after creating it, you can use the same connection parameters as defined above.
# Example usage:
# connection = create_connection("postgres", "postgres", "abc123", "127.0.0.1", "5432")