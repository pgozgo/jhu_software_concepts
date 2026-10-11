# Module 6 container deployment

The Compose stack runs exactly four services: PostgreSQL, RabbitMQ, the Flask
web service, and a single-prefetch ETL worker. The worker imports the bundled
cleaned JSON dataset after PostgreSQL is healthy and before consuming jobs.
PostgreSQL creates its schema from `src/db/init.sql`.

From `module_6`, copy `.env.example` to `.env`, set distinct URL-safe values
for the PostgreSQL and RabbitMQ role passwords, then run:

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
when the database already contains rows. PostgreSQL data persists in the
named `postgres_data` volume; the worker reads `src/data/` through a
read-only bind mount. To remove the containers while keeping database data,
run `docker compose down`. To also delete the database volume, use
`docker compose down --volumes`.

## Publish and run registry images

The GitHub Actions workflow **Publish Module 6 images to Docker Hub** builds
and pushes web and worker images to the Docker Hub repositories below. Add
`DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` as GitHub Actions repository
secrets, then run the workflow manually from the repository's **Actions** tab.

- [Web image](https://hub.docker.com/repository/docker/pgozgo/module6-web):
  `pgozgo/module6-web:v1`
- [Worker image](https://hub.docker.com/repository/docker/pgozgo/module6-worker):
  `pgozgo/module6-worker:v1`

The `v1` tags are published and available to pull. With `.env` configured,
run `docker compose pull web worker` followed by
`docker compose up -d --no-build`. The workflow also publishes `latest` and
commit-SHA tags for future releases.

Base image references: [Python](https://hub.docker.com/_/python),
[PostgreSQL](https://hub.docker.com/_/postgres), and
[RabbitMQ](https://hub.docker.com/_/rabbitmq).
