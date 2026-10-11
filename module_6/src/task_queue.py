"""Shared durable RabbitMQ task topology."""

EXCHANGE = "tasks"
QUEUE = "tasks_q"
ROUTING_KEY = "tasks"


def declare_topology(channel):
    """Declare the durable direct exchange, queue, and binding."""
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
