"""Fetch newly posted Grad Cafe results and insert unseen records.

The Flask application runs ``main`` in a background subprocess. Result URLs are
used to skip records already stored and duplicate URLs on the same scrape.
"""

import os
import psycopg

from scrape import GradCafeScraper
from load_data import _applicant_values

MAX_PAGES = 50  # safety cap so a stalled or unexpectedly large site can't scrape forever

def _existing_urls(conn_info):
    """Read non-null result URLs already present in PostgreSQL.

    Args:
        conn_info (str): PostgreSQL connection string.

    Returns:
        set[str]: Existing result URLs.
    """
    # Grad Cafe result URLs uniquely identify a record; use them to detect duplicates.
    with psycopg.connect(conn_info) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT url FROM applicants WHERE url IS NOT NULL")
            return {row[0] for row in cursor.fetchall()}

def _fetch_new_records(existing_urls):
    """Scrape up to ``MAX_PAGES`` and retain records with unseen URLs.

    Args:
        existing_urls (set[str]): URLs already in the database. The set is
            updated with each accepted URL to suppress within-pull duplicates.

    Returns:
        list[dict[str, object]]: Newly parsed records with unique, non-empty URLs.
    """
    scraper = GradCafeScraper()
    if not scraper._check_robots_permission():
        print("[Pull Data] Robots.txt does not permit scraping; aborting.")
        return []

    new_records = []
    url = scraper._build_url(page=1)
    for page in range(1, MAX_PAGES + 1):
        html = scraper._fetch_html(url)
        if not html:
            print(f"[Pull Data] Stopping at page {page}: no HTML returned.")
            break

        page_records = scraper.parse_admissions_data(html)
        if not page_records:
            print(f"[Pull Data] No records parsed on page {page}; stopping.")
            break

        unseen = []
        for record in page_records:
            record_url = record.get("url")
            if record_url and record_url not in existing_urls:
                existing_urls.add(record_url)
                unseen.append(record)
        new_records.extend(unseen)

        # Grad Cafe lists newest entries first, so a page with no new entries means
        # everything after it is already in the database.
        if not unseen:
            print(f"[Pull Data] Page {page} contained no new entries; stopping.")
            break

        next_url = scraper._next_page_url(html)
        if not next_url:
            print(f"[Pull Data] No further pages after page {page}.")
            break
        url = next_url

    return new_records

def _insert_records(records, conn_info):
    """Insert applicant records in one batch.

    Args:
        records (list[dict[str, object]]): New applicant records to insert.
        conn_info (str): PostgreSQL connection string.

    Returns:
        int: Number of inserted records, or zero for an empty input.
    """
    if not records:
        return 0
    with psycopg.connect(conn_info) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO applicants (
                    program, comments, date_added, url, status, term,
                    us_or_international, gpa, gre, gre_v, gre_aw, degree,
                    llm_generated_program, llm_generated_university
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (_applicant_values(record) for record in records),
            )
    return len(records)

def main():
    """Load the configured URL set, scrape new records, and insert them.

    Returns:
        None

    Raises:
        RuntimeError: If ``DATABASE_URL`` is not configured.
    """
    conn_info = os.getenv("DATABASE_URL")
    if not conn_info:
        raise RuntimeError("DATABASE_URL must be set before pulling data")

    print("[Pull Data] Checking database for existing records ...")
    existing_urls = _existing_urls(conn_info)
    print(f"[Pull Data] {len(existing_urls)} existing records found.")

    print("[Pull Data] Scraping Grad Cafe for new entries ...")
    new_records = _fetch_new_records(existing_urls)

    inserted = _insert_records(new_records, conn_info)
    print(f"[Pull Data] Inserted {inserted} new applicants into the database.")

if __name__ == "__main__":
    main()

# how to run:
# python pull_data.py
