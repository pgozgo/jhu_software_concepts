# Module 3: create_database.py
# This script creates a PostgreSQL database connection and an applicants table if it doesn't exist.

import psycopg2
from psycopg2 import OperationalError

def create_connection(db_name, db_user, db_password, db_host, db_port):
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