# Module 7: S3 data pipeline

## Requirements

- Python 3.10 or newer
- AWS credentials with permission to download the configured S3 object

## Setup

From this directory, create and activate a virtual environment, then install the
dependencies:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Configure AWS credentials using an AWS-supported method, such as an IAM role or
the AWS shared credentials file. Do not put credentials in source code or commit
them in a `.env` file.

## How to run

Open `grad-cafe-pipeline.ipynb` in VS Code with the Jupyter extension, select the
environment created above as its kernel, and run the notebook cell. The notebook
downloads `applicant_data.json` from the configured bucket to
`applicant_data_SM.json` in the current working directory.

## EC2 deployment with Docker Compose

The submission Compose file is [`ec2/docker-compose.ec2.yml`](./ec2/docker-compose.ec2.yml).
It defines `web`, `worker`, `db` (`postgres:16`), and `rabbitmq`
(`rabbitmq:3.13-management`). The web and RabbitMQ management ports bind to
the EC2 instance's loopback interface; use an SSH tunnel to access them rather
than opening them to the public internet.

The EC2 Compose file uses the published Module 6 service images from Docker
Hub: `pgozgo/module6-web:v1` and `pgozgo/module6-worker:v1`. The Module 7 S3
notebook does not itself build web or worker images. This deployment runs the
Module 6 application stack using those published images.

On the EC2 instance, install Docker Engine and the Compose plugin, clone the
repository, then run from the `module_7/ec2` directory:

```bash
cp .env.example .env
nano .env
docker pull docker.io/pgozgo/module6-web:v1
docker pull docker.io/pgozgo/module6-worker:v1
docker compose -f docker-compose.ec2.yml --env-file .env pull
docker compose -f docker-compose.ec2.yml --env-file .env up -d
docker compose -f docker-compose.ec2.yml --env-file .env ps
```

The explicit `docker pull` commands are optional because Compose's `pull`
command fetches the configured images too. Set distinct, strong, URL-safe
passwords for PostgreSQL, its setup/app/maintenance roles, and RabbitMQ in
`.env`. Keep `.env` on the instance; never commit credentials. On a new
database volume, Compose initializes roles/schema from Module 6's
`src/db/init.sql` and the worker loads the bundled applicant data. If an
existing PostgreSQL volume was initialized with another configuration, follow
the migration instructions in the [Module 6 README](../module_6/README.md#existing-database-volume)
before starting this adapted stack.

PostgreSQL and RabbitMQ AMQP are only reachable from the private Compose
network. The management UI and dashboard bind to EC2 loopback on host ports
`15673` and `8081` respectively (override with `RABBITMQ_HOST_PORT` and
`WEB_HOST_PORT` in `.env`). To open the dashboard from your computer, run this
in a local terminal, replacing the key path, login name, and address with your
EC2 details:

```bash
ssh -i /path/to/key.pem -L 8081:127.0.0.1:8081 ubuntu@<EC2_PUBLIC_IPV4>
```

For Amazon Linux, use `ec2-user` instead of `ubuntu`. Open
<http://localhost:8081/> locally. Add a second tunnel with
`-L 15673:127.0.0.1:15673` if you need the RabbitMQ management UI. The security
group should allow SSH only from your IP; do not expose ports `5432`, `5672`,
`8081`, or `15673` publicly.

## Lint

Run both checks from this directory; each should report a 10/10 Pylint score:

```powershell
python -m pylint src
python -m nbqa pylint grad-cafe-pipeline.ipynb
```
