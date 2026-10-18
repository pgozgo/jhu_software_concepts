# EC2 Deployment

## Deployment record

The EC2 shell prompt showed an Amazon Linux instance (`ec2-user`). During
setup, the following issues were reported:

- An SSH example using a placeholder key path failed because that file did not
  exist. SSH requires the actual downloaded key path and instance address.
- `apt-get` was unavailable, as expected on Amazon Linux; use `dnf`.
- DNF could not find `docker-compose-plugin`; install the Compose CLI plugin
  separately if the package is unavailable.
- A pull of `ghcr.io/pgozgo/module_6-worker:latest` was denied. The configured
  images for this deployment are public Docker Hub images instead:
  `docker.io/pgozgo/module6-web:v1` and
  `docker.io/pgozgo/module6-worker:v1`.
- Compose reported missing `MODULE7_WEB_IMAGE` and `MODULE7_WORKER_IMAGE`
  variables when it read an older/different Compose file. The submitted EC2
  file specifies the image names directly and does not require those variables.

The Docker install, image pulls, and successful service startup have not been
independently verified from this repository workspace.

## Steps to deploy

1. Connect to the EC2 instance from your local terminal, using your real key,
   address, and OS login (`ec2-user` for Amazon Linux). For example, in
   Windows PowerShell:

   ```powershell
   ssh -i "C:\Users\YourName\Downloads\my-ec2-key.pem" ec2-user@203.0.113.42
   ```

   Replace `YourName`, `my-ec2-key.pem`, and `203.0.113.42` with your Windows
   username, downloaded key filename, and EC2 public IPv4 address.
   `203.0.113.42` is reserved for documentation and is not a real EC2 address.

2. On Amazon Linux, install Docker and start it at boot:

   ```bash
   sudo dnf update -y
   sudo dnf install -y docker curl
   sudo systemctl enable --now docker
   sudo docker run hello-world
   ```

   Verify Docker and Docker Compose are installed:

   ```bash
   docker --version
   docker compose version
   ```

   If the Compose plugin is missing, install the matching official plugin
   binary for the instance architecture:

   ```bash
   case "$(uname -m)" in
     x86_64) compose_arch=x86_64 ;;
     aarch64) compose_arch=aarch64 ;;
     *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
   esac
   sudo install -d -m 0755 /usr/local/lib/docker/cli-plugins
   sudo curl -fsSL \
     "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${compose_arch}" \
     -o /usr/local/lib/docker/cli-plugins/docker-compose
   sudo chmod 0755 /usr/local/lib/docker/cli-plugins/docker-compose
   docker compose version
   ```

3. Clone or update the repository on EC2. From the repository root:

   ```bash
   git pull --ff-only
   cd module_7/ec2
   ```

4. Create `.env` from the checked-in template if it does not already exist.
   Restrict access to it, then edit it on EC2:

   ```bash
   cp .env.example .env
   chmod 600 .env
   nano .env
   ```

   In `nano`, replace the placeholder values for each password variable with
   a different strong password:

   - `POSTGRES_PASSWORD`
   - `DB_SETUP_PASSWORD`
   - `DB_APP_PASSWORD`
   - `DB_MAINTENANCE_PASSWORD`
   - `RABBITMQ_PASSWORD`

   Generate URL-safe random values with `openssl`; run it separately for each
   password and paste each result into the matching line in `.env`:

   ```bash
   openssl rand -hex 24
   ```

   Keep the generated values private. Do not reuse the same password for
   multiple services, include them in shell commands, or commit/share `.env`.
   Save and exit nano with **Ctrl+O**, **Enter**, then **Ctrl+X**. Compose reads
   these credentials from `.env` when you start or recreate the services.

5. Validate and start the submitted EC2 stack. The `sudo` prefix is used here
   because Docker group membership grants root-equivalent privileges:

   ```bash
   sudo docker compose -f docker-compose.ec2.yml --env-file .env config --quiet
   sudo docker compose -f docker-compose.ec2.yml --env-file .env pull
   sudo docker compose -f docker-compose.ec2.yml --env-file .env up -d
   sudo docker compose -f docker-compose.ec2.yml --env-file .env ps -a
   ```

The stack uses the published Module 6 application images; it does not package
the Module 7 S3 notebook as a web or worker image. The dashboard maps to EC2
port `8080` on all interfaces. Restrict inbound port `8080` to trusted sources
in the EC2 security group. PostgreSQL and RabbitMQ AMQP remain on the private
Compose network, and the RabbitMQ management UI binds to EC2 loopback.

The dashboard for the current EC2 instance is available at
<http://3.17.145.131:8080/>. This is an instance-specific public IP and may
change if the instance is stopped and started; use an Elastic IP if you need
a stable address. Anyone who can reach this URL and is allowed by the EC2
security group may access the dashboard, so restrict inbound TCP port `8080`
to trusted sources.
To access the RabbitMQ management UI from Windows PowerShell, open a second
local terminal and keep this SSH tunnel running:

```powershell
ssh -i "C:\Users\YourName\Downloads\my-ec2-key.pem" -L 15673:127.0.0.1:15673 ec2-user@203.0.113.42
```

Replace the sample key path and reserved example IP with your actual values.
Then open <http://localhost:15673/> in your local browser. For Ubuntu EC2
instances, replace `ec2-user` with `ubuntu`. Do not expose ports `5432`,
`5672`, or `15673` publicly; allow SSH only from your IP and port `8080` only
from trusted sources. Docker-published ports may bypass host firewall rules.

## Updating the deployment

For updated Module 6 application images, push the source changes and run
**Publish Module 6 images to Docker Hub** from the repository's GitHub Actions
tab. After the workflow succeeds, on EC2 run:

```bash
cd ~/jhu_software_concepts/module_7/ec2
sudo docker compose -f docker-compose.ec2.yml --env-file .env pull web worker
sudo docker compose -f docker-compose.ec2.yml --env-file .env up -d --no-build
sudo docker compose -f docker-compose.ec2.yml --env-file .env ps -a
```

For Compose-file changes, update the repository checkout before running
`config --quiet` and `up -d`. For `.env` changes, edit the EC2 copy directly, replace the applicable secret
values with new distinct values, and rerun `up -d`; do not replace it with a
repository copy. Routine updates
preserve the PostgreSQL named volume. Do not use `down --volumes` unless you
intend to delete the database.

## After verification

Stop the EC2 instance and the SageMaker notebook instance from the AWS console
after collecting the required screenshots and verifying the workflows. Stop,
do not terminate, the EC2 instance if you need to preserve it for later; check
AWS billing details for any storage or other resources that may continue to
incur charges.

## Troubleshooting

- **`apt-get: command not found`:** This is Amazon Linux; use `dnf`.
- **`No match for argument: docker-compose-plugin`:** Install Docker with DNF
  and use the Compose plugin binary commands in step 2.
- **`pull access denied` for `ghcr.io/...`:** Use the configured Docker Hub
  image references above. Log in only if the repository is private and you
  have access; authentication cannot resolve a misspelled or unpublished
  image/tag.
- **Compose says an image variable is missing:** Make sure you are in
  `module_7/ec2`, have the current `docker-compose.ec2.yml`, and run the
  commands with both `-f docker-compose.ec2.yml` and `--env-file .env`.
- **Container exited or is unhealthy:** Check all containers and recent logs:

  ```bash
  sudo docker compose -f docker-compose.ec2.yml --env-file .env ps -a
  sudo docker compose -f docker-compose.ec2.yml --env-file .env logs --tail=100 web worker db rabbitmq
  ```

- **Existing PostgreSQL volume:** The initialization SQL only runs when the
  database volume is first initialized. Follow the existing-volume migration
  guidance in the [Module 6 README](../module_6/README.md#existing-database-volume)
  before changing the database roles or schema.
