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
For the deployment steps, update process, and troubleshooting record, see
[`ec2/EC2_DEPLOYMENT.md`](./ec2/EC2_DEPLOYMENT.md).
It defines `web`, `worker`, `db` (`postgres:16`), and `rabbitmq`
(`rabbitmq:3.13-management`). The dashboard is published on EC2 port `8080`.
Restrict inbound access to that port in the EC2 security group. The RabbitMQ
management port binds to EC2 loopback and should be accessed through an SSH
tunnel.

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
docker compose -f docker-compose.ec2.yml --env-file .env ps -a
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
network. The dashboard publishes on host port `8080` on all network interfaces,
so restrict inbound TCP port `8080` in the EC2 security group to trusted
sources; do not expose it to the entire internet. Docker-published ports may
bypass host firewall rules. RabbitMQ management binds to EC2 loopback on host
port `15673` (override with `RABBITMQ_HOST_PORT` in `.env`). To access the
management UI from your computer, run this in a local terminal, replacing the
key path, login name, and address with your EC2 details:

```bash
ssh -i /path/to/key.pem -L 15673:127.0.0.1:15673 ubuntu@<EC2_PUBLIC_IPV4>
```

For Amazon Linux, use `ec2-user` instead of `ubuntu`. Open
<http://localhost:15673/> locally for RabbitMQ management. The dashboard for
the currently deployed EC2 instance is <http://3.17.145.131:8080/>. Its public
IP may change if the instance is stopped and started; use an Elastic IP for a
stable address. Restrict inbound port `8080` to trusted sources. Do not expose
ports `5432`, `5672`, or `15673` publicly, and allow SSH only from your IP.

### Update and iterate the EC2 deployment

This deployment uses the Module 6 Docker Hub images. To publish updated web or
worker code, push the changes to the repository, then run the repository's
**Publish Module 6 images to Docker Hub** workflow from the GitHub **Actions**
tab using **Run workflow**. The workflow builds both images and pushes the
`latest`, `v1`, and commit-SHA tags to Docker Hub. Wait for the workflow to
finish successfully before updating EC2. This workflow does not build a
Module 7-specific image; Module 7 currently supplies the EC2 Compose
configuration and runs the published Module 6 services.

Connect to EC2, change to the repository's Module 7 EC2 directory, and pull
and recreate the web and worker containers:

```bash
cd ~/jhu_software_concepts/module_7/ec2
sudo docker compose -f docker-compose.ec2.yml --env-file .env pull web worker
sudo docker compose -f docker-compose.ec2.yml --env-file .env up -d --no-build
sudo docker compose -f docker-compose.ec2.yml --env-file .env ps -a
```

`ps -a` shows stopped containers as well as running ones. Confirm the web,
worker, PostgreSQL, and RabbitMQ services are running; web and worker should
be healthy. If a service is stopped or unhealthy, inspect its output:

```bash
sudo docker compose -f docker-compose.ec2.yml --env-file .env logs --tail=100 web worker
sudo docker compose -f docker-compose.ec2.yml --env-file .env logs --tail=100 db rabbitmq
```

If you changed `docker-compose.ec2.yml`, first update the repository checkout
on EC2 (for example, `git pull --ff-only` from the repository root), then
validate and apply the configuration:

```bash
cd ~/jhu_software_concepts
git pull --ff-only
cd module_7/ec2
sudo docker compose -f docker-compose.ec2.yml --env-file .env config --quiet
sudo docker compose -f docker-compose.ec2.yml --env-file .env up -d
sudo docker compose -f docker-compose.ec2.yml --env-file .env ps -a
```

If you change `.env`, edit the EC2 copy directly and rerun `up -d` so Compose
recreates services with the new settings. Do not overwrite it with a repository
pull, commit it, or publish it to artifacts; it contains credentials. Keep the
PostgreSQL named volume when iterating. `docker compose down` stops/removes
containers without deleting the data volume; avoid `down --volumes` unless
you intentionally want to erase the database.

## Lint

Run both checks from this directory; each should report a 10/10 Pylint score.
The notebook filename is required by the assignment but contains hyphens, so
disable Pylint's module-name `invalid-name` check for the notebook run:

```powershell
python -m pylint src --fail-under=10
python -m nbqa pylint grad-cafe-pipeline.ipynb --disable=invalid-name --fail-under=10
```

After collecting evidence, stop the EC2 instance and SageMaker notebook
instance from the AWS console to avoid ongoing compute charges.
