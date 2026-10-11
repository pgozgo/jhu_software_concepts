"""Publish durable task messages to RabbitMQ."""

from datetime import datetime, timezone
from importlib import import_module
import json
import os

from task_queue import EXCHANGE, ROUTING_KEY, declare_topology


def _open_channel():
    """Open RabbitMQ and declare the durable task exchange and queue."""
    pika = import_module("pika")

    connection = pika.BlockingConnection(
        pika.URLParameters(os.environ["RABBITMQ_URL"])
    )
    try:
        channel = connection.channel()
        declare_topology(channel)
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
