"""RabbitMQ worker and incremental applicant ingestion handlers."""

import json
import logging
import os
from importlib import import_module
from pathlib import Path

import psycopg
from psycopg import sql
from db.load_data import (
    INGESTION_SOURCE,
    INSERT_SQL,
    applicant_values,
    refresh_analytics_views,
)
from worker.etl.incremental_scraper import GradCafeScraper, fetch_records_after_watermark

LOGGER = logging.getLogger(__name__)
EXCHANGE = "tasks"
QUEUE = "tasks_q"
ROUTING_KEY = "tasks"
WATERMARK_READ_SQL = sql.SQL(
    """
    SELECT last_seen
    FROM {}
    WHERE source = {}
"""
).format(
    sql.Identifier("ingestion_watermarks"),
    sql.Placeholder(),
)
WATERMARK_WRITE_SQL = sql.SQL(
    """
    INSERT INTO {} (source, last_seen, updated_at)
    VALUES ({}, {}, now())
    ON CONFLICT (source) DO UPDATE
    SET last_seen = EXCLUDED.last_seen, updated_at = now()
"""
).format(
    sql.Identifier("ingestion_watermarks"),
    sql.Placeholder(),
    sql.Placeholder(),
)


def declare_topology(channel):
    """Declare the durable direct task exchange and its bound queue."""
    channel.exchange_declare(
        exchange=EXCHANGE,
        exchange_type="direct",
        durable=True,
    )
    channel.queue_declare(queue=QUEUE, durable=True)
    channel.queue_bind(
        queue=QUEUE,
        exchange=EXCHANGE,
        routing_key=ROUTING_KEY,
    )


def handle_scrape_new_data(conn, payload):
    """Scrape after the stored watermark, insert rows, and stage watermark update."""
    cursor = conn.cursor()
    try:
        statement = WATERMARK_READ_SQL
        cursor.execute(statement, (INGESTION_SOURCE,))
        watermark_row = cursor.fetchone()
        last_seen = int(watermark_row[0]) if watermark_row and watermark_row[0] else 0

        since = payload.get("since")
        if since is not None:
            try:
                last_seen = max(last_seen, int(since))
            except (TypeError, ValueError) as error:
                raise ValueError("payload.since must be a numeric result ID") from error

        max_pages = payload.get("max_pages", 50)
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
            raise ValueError("payload.max_pages must be a positive integer")

        scraper = GradCafeScraper()
        records, max_seen = fetch_records_after_watermark(
            scraper,
            last_seen,
            max_pages=max_pages,
        )
        normalized_records = [
            applicant_values(record)
            for record in records
            if record.get("url")
        ]
        if normalized_records:
            cursor.executemany(INSERT_SQL, normalized_records)

        if max_seen > last_seen:
            statement = WATERMARK_WRITE_SQL
            cursor.execute(statement, (INGESTION_SOURCE, str(max_seen)))
        refresh_analytics_views(cursor)
        return len(normalized_records)
    finally:
        cursor.close()


def handle_recompute_analytics(conn, payload):
    """Refresh the database-backed summaries in the current transaction."""
    del payload
    cursor = conn.cursor()
    try:
        refresh_analytics_views(cursor)
    finally:
        cursor.close()


TASK_HANDLERS = {
    "scrape_new_data": handle_scrape_new_data,
    "recompute_analytics": handle_recompute_analytics,
}


def process_delivery(
    channel,
    method,
    properties,
    body,
    *,
    connection_factory=None,
    task_handlers=None,
):
    """Run one task in its own transaction; ack only after commit."""
    del properties
    try:
        message = json.loads(body)
        if not isinstance(message, dict):
            raise ValueError("task message must be a JSON object")
        kind = message.get("kind")
        payload = message.get("payload") or {}
        if not isinstance(payload, dict):
            raise ValueError("task payload must be a JSON object")
        if not isinstance(kind, str):
            raise ValueError("task kind must be a string")
        handler = (task_handlers or TASK_HANDLERS).get(kind)
        if handler is None:
            raise ValueError(f"Unsupported worker task: {kind!r}")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
        LOGGER.exception("Rejecting invalid task delivery %s", method.delivery_tag)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return

    try:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL must be configured before starting the worker")
        connection_factory = connection_factory or psycopg.connect
        with connection_factory(database_url) as database_connection:
            with database_connection.transaction():
                handler(database_connection, payload)
    except Exception:
        LOGGER.exception("Task delivery %s failed", method.delivery_tag)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    else:
        channel.basic_ack(delivery_tag=method.delivery_tag)


def main(
    connection_factory=None,
    parameters_factory=None,
    database_connection_factory=None,
):
    """Connect to RabbitMQ and consume durable tasks with prefetch one."""
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        raise RuntimeError("RABBITMQ_URL must be configured before starting the worker")

    pika = None
    if connection_factory is None or parameters_factory is None:
        pika = import_module("pika")
        connection_factory = connection_factory or pika.BlockingConnection
        parameters_factory = parameters_factory or pika.URLParameters

    channel_connection = connection_factory(parameters_factory(rabbitmq_url))
    channel = channel_connection.channel()
    declare_topology(channel)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(
        queue=QUEUE,
        on_message_callback=lambda ch, method, properties, body: process_delivery(
            ch,
            method,
            properties,
            body,
            connection_factory=database_connection_factory,
        ),
        auto_ack=False,
    )
    ready_file = os.getenv("WORKER_READY_FILE")
    if ready_file:
        Path(ready_file).touch()
    LOGGER.info("Waiting for tasks on %s", QUEUE)
    try:
        channel.start_consuming()
    finally:
        if channel_connection.is_open:
            channel_connection.close()


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    main()
