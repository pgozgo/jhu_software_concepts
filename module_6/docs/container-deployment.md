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

## Run on an EC2 instance

Create an EC2 instance running Ubuntu 24.04 or Amazon Linux 2023. Allow SSH
(TCP port 22) in its security group only from your current IP address. Do not
open PostgreSQL (5432), RabbitMQ AMQP (5672), or the dashboard (8080) to the
public internet; the Compose file binds the dashboard and RabbitMQ management
UI to the instance's loopback interface.

Connect from your computer, substituting the path to your private key and the
instance's public IPv4 address. Ubuntu images generally use `ubuntu`; Amazon
Linux images generally use `ec2-user`.

```bash
ssh -i /path/to/key.pem ubuntu@<EC2_PUBLIC_IPV4>
```

### Ubuntu 24.04

Install Docker Engine and the Compose plugin from Docker's official APT
repository:

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run hello-world
docker compose version
```

### Amazon Linux 2023

Install and start Docker using DNF. Install Compose as the Docker CLI plugin
from its official release; this avoids relying on whether the Compose plugin
package is available in the configured Amazon Linux repositories.

```bash
sudo dnf update -y
sudo dnf install -y docker curl
sudo systemctl enable --now docker

case "$(uname -m)" in
  x86_64) compose_arch=x86_64 ;;
  aarch64) compose_arch=aarch64 ;;
  *) echo "Unsupported EC2 architecture: $(uname -m)" >&2; exit 1 ;;
esac

sudo install -d -m 0755 /usr/local/lib/docker/cli-plugins
sudo curl -fsSL \
  "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${compose_arch}" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod 0755 /usr/local/lib/docker/cli-plugins/docker-compose
sudo docker run hello-world
docker compose version
```

Docker commands below use `sudo`, avoiding a persistent change to Docker
group membership. The `docker` group grants root-equivalent privileges. If you
choose to add your login to that group, log out and reconnect before using
Docker without `sudo`.

Clone this repository on the instance, then configure and launch the stack
using the published Module 6 images:

```bash
git clone https://github.com/pgozgo/jhu_software_concepts.git
cd jhu_software_concepts/module_6
cp .env.example .env
nano .env
sudo docker compose pull web worker
sudo docker compose up -d --no-build
sudo docker compose ps
```

Replace every placeholder password in `.env` with a distinct, strong value.
Keep `.env` on the instance and never commit or share it. The `v1` image tags
are configured in Compose. To run locally built images from the cloned source
instead, use `sudo docker compose up -d --build`.

The app listens only on the instance's loopback interface. To view it from your
computer, leave this SSH tunnel open in a second local terminal:

```bash
ssh -i /path/to/key.pem -L 8080:127.0.0.1:8080 ubuntu@<EC2_PUBLIC_IPV4>
```

For Amazon Linux, replace `ubuntu` with `ec2-user`. Then open
<http://localhost:8080/> in your computer's browser. Update the remote
deployment with `sudo docker compose pull web worker` and
`sudo docker compose up -d --no-build`. To stop the services without deleting
the database volume, run `sudo docker compose down`; do not add `--volumes`
unless you intend to delete the stored database.

Installation references: [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/),
[Docker Compose plugin on Linux](https://docs.docker.com/compose/install/linux/),
and [Amazon Linux 2023 package management](https://docs.aws.amazon.com/linux/al2023/ug/package-management.html).
