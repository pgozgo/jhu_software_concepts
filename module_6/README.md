# Module 6: Containerized Grad Cafe applicant analysis

Module 6 runs a Flask dashboard and an incremental scraper as separate
services. RabbitMQ carries durable scrape jobs between them, and PostgreSQL
stores applicant records. On first startup, Compose initializes the database
schema and the worker loads the LLM-cleaned dataset from the read-only
`src/data/applicant_data.json` mount.

## Layout

```text
module_6/
├── docker-compose.yml
├── setup.py
├── src/
│   ├── task_queue.py
│   ├── data/applicant_data.json
│   ├── db/init.sql
│   ├── db/load_data.py
│   ├── web/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── run.py
│   │   ├── publisher.py
│   │   └── app/
│   └── worker/
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── consumer.py
│       └── etl/
│           ├── incremental_scraper.py
│           └── query_data.py
└── tests/
```

The existing repository-level `.github/workflows` directory and `.gitignore`
are already located at the repository root, alongside the module folders.
Module 6's Compose-specific implementation is under `src/web`, `src/worker`,
`src/db`, and `src/data`; `src/task_queue.py` shares the durable RabbitMQ
topology between publisher and consumer.

## Requirements checklist

### Shall

- **SHALL** provide separate `src/web/` and `src/worker/` services.
- **SHALL** define exactly four Compose services: `web`, `worker`, `db`
  (PostgreSQL), and `rabbitmq`.
- **SHALL** use Compose's private project network, a named PostgreSQL data
  volume, and a read-only worker mount of `src/data/`.
- **SHALL** serve the Flask app on port `8080` (`127.0.0.1:8080` on the host).

### Should

- **SHOULD** run both Python images as the unprivileged `app` user (UID 10001).
- **SHOULD** initialize the database schema from `src/db/init.sql`.

## Run with Docker Compose

Install Docker Desktop and make sure its engine is running. From PowerShell,
run these commands:

```powershell
Set-Location .\module_6
Copy-Item .env.example .env
```

Edit `.env` and replace all placeholder passwords with distinct, URL-safe
values. These credentials stay in environment configuration and are not
embedded in the application source. Then build and start the stack:

```powershell
docker compose up --build
```

For an EC2 deployment, see [Container deployment](./docs/container-deployment.md#run-on-an-ec2-instance).

The dashboard is at <http://localhost:8080/>. **Pull Data** publishes a
`scrape_new_data` task; **Update Analysis** publishes a
`recompute_analytics` task. Both buttons receive HTTP `202 Accepted`
immediately and display a **Request queued** banner. The persistent messages
are published to the durable direct `tasks` exchange and `tasks_q` queue.
Each task runs in a PostgreSQL transaction; successful work is committed before
RabbitMQ is acknowledged, while failures are rolled back and rejected without
requeue. Incremental scraping reads and advances the `gradcafe` result-ID
watermark in that same transaction, and applicant URLs remain unique to make
repeated deliveries safe.

The Compose project has exactly four services: `web`, `worker`, `db`, and
`rabbitmq`. The PostgreSQL health check gates the worker's initial JSON load;
the web service starts after both PostgreSQL and the worker are healthy.
PostgreSQL retains its state in `postgres_data`, and the worker reads the
applicant JSON from the read-only `src/data/` bind mount at `/app/src/data`.
Worker startup runs
`src/db/load_data.py`: when the PostgreSQL table is empty, it initializes it
from the bundled JSON. If the database is already populated, initialization is
skipped. The schema and loader use unique applicant URLs to avoid duplicates.

### Services and ports

| Service | Host port | Purpose |
| --- | ---: | --- |
| Web | `8080` | Flask dashboard and `/health` readiness endpoint |
| PostgreSQL | Container-only `5432` | Applicant database on the private Compose network |
| RabbitMQ AMQP | Container-only `5672` | Durable work queue on the private Compose network |
| RabbitMQ management UI | `127.0.0.1:15672` | Queue administration (`.env` credentials) |
| Worker | — | Consumes scrape jobs with prefetch set to one |

Both Python Dockerfiles run as an unprivileged `app` user. Compose's default
project network is private to the project.

The stack uses the published [`postgres:16`](https://hub.docker.com/_/postgres),
[`rabbitmq:3-management`](https://hub.docker.com/_/rabbitmq), and
[`python:3.13-slim`](https://hub.docker.com/_/python) base images. The Module 6
web and worker images are on Docker Hub:

- [Web image: `pgozgo/module6-web`](https://hub.docker.com/repository/docker/pgozgo/module6-web)
- [Worker image: `pgozgo/module6-worker`](https://hub.docker.com/repository/docker/pgozgo/module6-worker)

Both repositories currently publish the `v1` tag. To publish updates from
GitHub Actions, add repository Actions secrets `DOCKERHUB_USERNAME` and
`DOCKERHUB_TOKEN` (a Docker Hub access token), then open the repository's
**Actions** tab, select **Publish Module 6 images to Docker Hub**, and choose
**Run workflow**. It pushes `latest`, `v1`, and the commit SHA tag for both
images.

To pull the published `v1` images and run the stack without rebuilding:

```powershell
docker pull pgozgo/module6-web:v1
docker pull pgozgo/module6-worker:v1
docker compose pull web worker
docker compose up -d --no-build
```

Use the normal `.env` setup above. For a local source build instead, use
`docker compose up --build`.

Only the dashboard and loopback-bound management UI are published to the host;
PostgreSQL and AMQP remain private to the Compose network.

### Environment variables

Compose reads these values from `.env` in this directory. The tracked
`.env.example` contains local-development placeholders; copy it to `.env` and
replace the passwords before use. Do not commit `.env`.

| Variable | Purpose |
| --- | --- |
| `POSTGRES_DB` | PostgreSQL database name |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | PostgreSQL bootstrap administrator |
| `DB_OWNER_ROLE` | No-login owner of the applicant and watermark tables |
| `DB_SETUP_USER`, `DB_SETUP_PASSWORD` | Setup-only account used by the startup loader |
| `DB_APP_USER`, `DB_APP_PASSWORD` | Read-only web dashboard account |
| `DB_MAINTENANCE_USER`, `DB_MAINTENANCE_PASSWORD` | Worker account for ingestion and summary refresh |
| `RABBITMQ_USER`, `RABBITMQ_PASSWORD` | RabbitMQ credentials |
| `LOG_LEVEL` | Worker logging level |

Compose constructs `DATABASE_URL`, `SETUP_DATABASE_URL`, and `RABBITMQ_URL`
for the services from these values. The web service receives only the
read-only application credential. The worker uses the setup credential for
initialization, then removes it before starting the consumer with the
maintenance credential. The table owner is a `NOLOGIN` role; the maintenance
account alone receives `UPDATE` and `TRUNCATE` on `applicants`. The web account
has `SELECT` only and cannot modify or truncate applicant data.

### Load the applicant data

On normal startup, Compose runs `python -m db.load_data` in the worker before
it starts consuming tasks. To run the loader manually while the services are
up:

```powershell
docker compose exec worker python -m db.load_data --file /app/src/data/applicant_data.json
```

The setup account creates the watermark and analytics objects, imports the JSON only
when the applicants table is empty, skips duplicate applicant URLs, seeds the
initial scraping watermark, and refreshes the summaries. It reports when the
initial data load is skipped because the table already contains records.

### Existing database volume

The PostgreSQL image runs `src/db/init.sql` automatically only when it first
initializes an empty data volume. To preserve a volume created by an earlier
version, first copy the new role settings from `.env.example` into `.env`,
keeping the current database name and bootstrap administrator credentials.
Start PostgreSQL, then run the migration script once as the existing database
bootstrap superuser:

```powershell
docker compose up -d db
docker compose exec -T db psql -v ON_ERROR_STOP=1 `
  -U <existing-bootstrap-user> -d <database-name> `
  -f /docker-entrypoint-initdb.d/001-init.sql
docker compose up -d --build
```

Replace the two angle-bracket values with the database's current administrator
username and database name. The script creates/updates the roles and transfers
ownership/grants without deleting applicant rows. Keep the database volume;
do not use `docker compose down --volumes` for this migration.

### Local Python installation

Python 3.11 or newer is required. The setup below also works with a clean
Python 3.12 environment. From the `module_6` directory, choose either pip or
uv.

With pip:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install -r requirements.txt
```

With uv:

```powershell
uv venv --python 3.12
.\.venv\Scripts\Activate.ps1
uv pip install -e .
uv pip install -r requirements.txt
```

The editable project install supplies the web and worker runtime dependencies.
The root `requirements.txt` adds development tools, including pytest, Pylint,
and pydeps. These `uv pip install` commands resolve and install dependencies
from the project's version ranges. Do not substitute `uv pip sync` with these
unlocked requirement files; if using `uv pip sync`, first compile a fully
resolved requirements file with `uv pip compile`.

### SQL safety and result limits

The Compose web and worker database paths build statements with `psycopg.sql`
composables instead of interpolating SQL strings. Identifiers are composed
with `sql.Identifier`; runtime values, including the dashboard's university
`LIMIT`, are passed separately through placeholders. Analytics view names
come from the application's fixed view-name list, not request data.

The dashboard validates and enforces the `limit` query parameter on the server:
missing values default to `1`, non-integer values return HTTP `400`, and
malformed, non-ASCII, or excessively long values return HTTP `400`. Valid
integer values are constrained to the range `1`–`100`. The HTML input's
`min`/`max` attributes are only a usability aid; server-side validation is the
effective boundary.

### Tests, lint, and CI

The service tests run without PostgreSQL or RabbitMQ. From this directory:

```powershell
python -m pytest
```

The pytest configuration enforces 100% statement coverage for the
queue-facing service modules: Flask app and publisher, worker consumer, shared
queue topology, and database loader. The container test suite also exercises
the worker scraper's watermark handling, pagination, duplicate filtering, and
robots.txt denial behavior; the scraper's HTML parsing and live-network helpers
remain outside that focused coverage gate.

Run Pylint on the Module 6 service and database code:

```powershell
python -m pylint src\web src\worker src\db src\task_queue.py --fail-under=10
```

No standalone lint-output report is included. To save a local report for
submission or review, use:

```powershell
python -m pylint src\web src\worker src\db src\task_queue.py --fail-under=10 2>&1 |
    Tee-Object pylint-evidence.txt
if ($LASTEXITCODE -ne 0) { throw "Pylint failed with exit code $LASTEXITCODE" }
```

The repository's `.github/workflows/module6.yml` workflow runs for Module 6
pushes and pull requests, plus manual dispatch. It runs the 100% focused
coverage gate, requires a 10.00 Pylint score, and validates the Compose
configuration. The Docker Hub image publishing workflow is manually dispatched
separately.

### Submission files

- [Module 6 report PDF](./module_6_report.pdf)
- [Running dashboard screenshot](./dashboard-screenshot.png)
- [RabbitMQ management screenshot](./rabbitmq-management-screenshot.png)
- [GitHub repository](https://github.com/pgozgo/jhu_software_concepts/tree/main/module_6)
- [Docker Hub web image](https://hub.docker.com/repository/docker/pgozgo/module6-web)
- [Docker Hub worker image](https://hub.docker.com/repository/docker/pgozgo/module6-worker)

The RabbitMQ capture shows the management login screen without credentials.
The Docker Hub `v1` tags were verified as available for anonymous pulls.

## Lifecycle and troubleshooting

```powershell
docker compose ps
docker compose logs -f web worker
docker compose down
```

`docker compose down` retains database contents in the named volume. To remove
the database as well and reload the bundled data on the next start, run:

```powershell
docker compose down --volumes
```

Removing volumes clears both the PostgreSQL records and the persisted cleaned
JSON data.

If `docker` is not recognized, open a new PowerShell terminal after installing
Docker Desktop. If Docker reports that it cannot connect to its engine, launch
Docker Desktop and wait for it to finish starting.
