# Module 6 container deployment

The Compose stack runs exactly four services: PostgreSQL, RabbitMQ, the Flask
web service, and a single-prefetch ETL worker. The worker imports the bundled
cleaned JSON dataset after PostgreSQL is healthy and before consuming jobs.
PostgreSQL creates its schema from `src/db/init.sql`.

From `module_6`, copy `.env.example` to `.env`, replace both local-only
passwords, then run:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open the dashboard at <http://localhost:8080/>. The **Pull Data** and
**Update Analysis** buttons enqueue `scrape_new_data` and
`recompute_analytics` tasks and immediately show a queued status. The broker
uses the durable direct `tasks` exchange, the durable `tasks_q` queue, and
persistent messages. The RabbitMQ management UI is at
<http://localhost:15672/>; PostgreSQL and AMQP are only exposed on the private
Compose network.

The worker invokes `src/db/load_data.py` before consuming tasks. It imports
the bundled data when the applicants table is empty and skips initialization
when the database already contains rows. The named `postgres_data` and
`applicant_data` volumes preserve the database and cleaned input across
restarts. To remove the containers while keeping data, run
`docker compose down`. To also delete both volumes, use
`docker compose down --volumes`.

Registry references: [Python](https://hub.docker.com/_/python),
[PostgreSQL](https://hub.docker.com/_/postgres), and
[RabbitMQ](https://hub.docker.com/_/rabbitmq).
