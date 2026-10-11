"""Publish durable task messages to RabbitMQ."""

from datetime import datetime, timezone
from importlib import import_module
import json
import os

EXCHANGE = "tasks"
QUEUE = "tasks_q"
ROUTING_KEY = "tasks"


def _open_channel():
    """Open RabbitMQ and declare the durable task exchange and queue."""
    pika = import_module("pika")

    connection = pika.BlockingConnection(
        pika.URLParameters(os.environ["RABBITMQ_URL"])
    )
    try:
        channel = connection.channel()
        channel.exchange_declare(
            exchange=EXCHANGE,
            exchange_type="direct",
            durable=True,
        )
        channel.queue_declare(queue=QUEUE, durable=True)
        channel.queue_bind(
            exchange=EXCHANGE,
            queue=QUEUE,
            routing_key=ROUTING_KEY,
        )
    except Exception:
        connection.close()
        raise
    return connection, channel


def publish_task(
    kind: str,
    payload: dict | None = None,
    headers: dict | None = None,
) -> None:
    """Publish a persistent JSON task and always close its RabbitMQ connection."""
    pika = import_module("pika")

    body = json.dumps(
        {
            "kind": kind,
            "ts": datetime.now(timezone.utc).isoformat(),
            "payload": payload or {},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    connection, channel = _open_channel()
    try:
        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=ROUTING_KEY,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=2,
                headers=headers or {},
            ),
            mandatory=False,
        )
    finally:
        connection.close()
