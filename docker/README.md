# 🐳 Docker Setup Guide for HiddenEgo Telegram Bot

This guide provides comprehensive instructions for deploying the HiddenEgo Telegram Anonymous Messaging Bot using Docker.

## 📋 Table of Contents
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Environment Configuration](#environment-configuration)
- [Docker Network Configuration](#docker-network-configuration)
- [Manual Setup](#manual-setup)
- [Container Management](#container-management)
- [Lean Deployments](#-lean-deployments-low-end-vps--shared-host)
- [Moving to a New VPS](MIGRATION.md)
- [Troubleshooting](#troubleshooting)
- [Security Considerations](#security-considerations)
- [Volume Management](#volume-management)

## 🔧 Prerequisites

Before starting, ensure you have:

- **Docker Engine** (v20.10+ recommended)
- **Docker Compose** (v2.0+ recommended)
- **Linux/macOS/WSL2** (Windows with WSL2 support)
- **Network access** for downloading dependencies
- **Port availability** (default: 13360, configurable via `.env`)

### Installation Commands

**Ubuntu/Debian:**
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt-get update
sudo apt-get install docker-compose-plugin
```

**macOS (with Homebrew):**
```bash
brew install docker docker-compose
```

## 🚀 Quick Start

### 1. Clone and Setup
```bash
git clone https://github.com/411A/Telegram-Anonymous-Messaging-Bot-Creator.git
cd Telegram-Anonymous-Messaging-Bot-Creator
```

### 2. Configure Environment
```bash
# Copy example environment file
cp .env.example .env

# Edit the configuration
nano .env  # or your preferred editor
```

### 3. Start with Helper Script
```bash
cd docker/
./run.sh pull
```

`./run.sh pull` downloads the CI-built image from GitHub Container Registry and
starts it without running a build on the VPS. If the package is private,
`docker login ghcr.io` first. To build locally instead, use
`./run.sh start -b`.

`run.sh` is stored executable in Git; if a manual copy dropped the bit,
`chmod +x run.sh` once.

### 4. Alternative: Direct Docker Compose
```bash
cd docker/
docker compose --env-file ../.env run --rm hidego-tgbot
```

## ⚙️ Environment Configuration

### Required Environment Variables

Edit your `.env` file in the project root with these essential settings:

```bash
# Bot Configuration
BOT_CREATOR_USERNAME=@YourBotUsername
MAIN_BOT_TOKEN=123456789:your-bot-token-here

# Webhook Configuration
WEBHOOK_BASE_URL=https://your-domain.com
TG_SECRET_TOKEN=your-secret-token-here

# Server Configuration
FASTAPI_PORT=13360
FASTAPI_BIND_ADDR=127.0.0.1

# Trusted proxy addresses (gateway + cloudflared container)
TRUSTED_PROXY_CIDRS=172.30.0.1/32,172.30.0.2/32

# Logging
LOG_FILENAME=Logs.log
LOGGER_TIMEZONE=UTC
```

### Getting Your Bot Token

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the provided token to `MAIN_BOT_TOKEN`
4. Set your bot username in `BOT_CREATOR_USERNAME`

### Webhook Configuration

**For Development (using ngrok):**
```bash
# Install ngrok
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok

# Start tunnel
ngrok http 13360

# Copy the HTTPS URL to WEBHOOK_BASE_URL in .env
```

**For Production:**
- Use a reverse proxy (nginx, Cloudflare Tunnel)
- Ensure HTTPS is enabled
- Point to your server's public IP/domain

## 🌐 Docker Network Configuration

### Fixed Network Setup

This project uses a **fixed Docker network** to ensure consistent security and prevent issues when multiple Docker projects run on the same host.

**Network Details:**
- **Network Name**: `hidego-network`
- **Subnet**: `172.30.0.0/24`
- **Gateway**: `172.30.0.1`
- **cloudflared**: `172.30.0.2` (static)
- **hidego-tgbot**: `172.30.0.3` (static)
- **Driver**: bridge

**Why Fixed Network?**
- Prevents IP conflicts with other Docker projects
- Consistent security configuration
- Lets the app trust the exact proxy addresses instead of the whole subnet
- Easier to configure firewall rules

### Trusted Proxy Configuration

Only the Cloudflare Tunnel connector may supply the client IP used by the webhook allow-list. The Compose file gives `cloudflared` the fixed address `172.30.0.2`, and the bot trusts these proxies by default:

```bash
# .env
TRUSTED_PROXY_CIDRS=172.30.0.1/32,172.30.0.2/32
```

- `172.30.0.1` - Docker gateway (traffic from a host-run `cloudflared`).
- `172.30.0.2` - `cloudflared` container (static IP in `docker-compose.yml`).

Do **not** trust the whole `/24`: any container on that network could then forge `CF-Connecting-IP` / `X-Forwarded-For`. `DOCKER_NETWORK_IP` is still read as a legacy alias when `TRUSTED_PROXY_CIDRS` is unset.

**Troubleshooting:**
If you see `403 Forbidden` errors with webhook security blocked:
1. Check that `TRUSTED_PROXY_CIDRS` matches the gateway and `cloudflared` address in `docker-compose.yml`
2. Verify with: `docker network inspect hidego-tgbot_hidego-network | grep -A 5 "IPAM"`
3. Update `.env` if the addresses are different

**Custom Network Configuration:**
If you need to use a different subnet, update both files:

1. **Edit `docker-compose.yml`:**
```yaml
networks:
  hidego-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.31.0.0/24      # Your custom subnet
          gateway: 172.31.0.1          # Your custom gateway
```

2. **Edit `.env`:**
```bash
TRUSTED_PROXY_CIDRS=172.31.0.1/32,172.31.0.2/32   # Gateway + cloudflared
```

Also update the `cloudflared` (`172.31.0.2`) and bot (`172.31.0.3`) static addresses in `docker-compose.yml`.

**Recommended Subnet Ranges:**
- `172.30.0.0/24` (default) - Gateway: `172.30.0.1`
- `172.31.0.0/24` - Gateway: `172.31.0.1`
- `10.0.0.0/24` - Gateway: `10.0.0.1`
- `192.168.100.0/24` - Gateway: `192.168.100.1`

### Published Port

`FASTAPI_PORT` is published on **loopback only**:

```bash
# .env
FASTAPI_BIND_ADDR=127.0.0.1
FASTAPI_PORT=13360
```

This is deliberate. A container port published as `0.0.0.0:PORT` is reachable from the Internet even when UFW reports it blocked, because Docker inserts its own DNAT rules ahead of UFW. Cloudflare Tunnel does not need a host port at all: `cloudflared` reaches `http://hidego-tgbot:13360` over the Compose network. The loopback mapping remains for a host-run `cloudflared` and for `./run.sh` health checks.

Verify the exposure with:

```bash
./run.sh security-check
```

Expected output: `Bot port ... is loopback-only` and `cloudflared publishes no host ports`.

**If you use an orange-cloud DNS record instead of a tunnel:** Cloudflare proxies only its [supported HTTP/HTTPS ports](https://developers.cloudflare.com/fundamentals/reference/network-ports/) and connects to the origin on the same port. Publish only `443` (with TLS termination) and allow only [Cloudflare IP ranges](https://www.cloudflare.com/ips/) to reach it. Use the `DOCKER-USER` iptables chain, not UFW, because Docker-published ports bypass UFW. A Cloudflare Tunnel avoids all of this: no inbound port and no origin IP allow-list.

### 🔍 Verifying Your Network Configuration

**Check Current Network Settings:**
```bash
# List all Docker networks
docker network ls

# Inspect the hidego network
docker network inspect hidego-tgbot_hidego-network

# Quick gateway check
docker network inspect hidego-tgbot_hidego-network | grep -A 5 "IPAM"
```

**Verify Settings Match:**
```bash
# 1. Check docker-compose.yml gateway and cloudflared address
grep -A 8 "hidego-network" docker/docker-compose.yml

# 2. Check .env settings
grep -E "TRUSTED_PROXY_CIDRS|FASTAPI_BIND_ADDR" .env

# 3. These should match!
```

## 🔒 Network Security

The fixed Docker network and loopback-only port keep the webhook path on one controlled channel:

**Security Features:**
- `FASTAPI_PORT` listens on `127.0.0.1` only; there is no public origin port
- `cloudflared` connects outbound to Cloudflare on `7844/tcp+udp`; no ingress port
- Tunnel ingress matches only `/webhook/...`; all other paths return 404
- Webhook clients are validated against Telegram's official IP ranges
- Only the Docker gateway and the `cloudflared` container may forward a client IP
- Secret token (`TG_SECRET_TOKEN`) is checked in constant time

**Trusted Sources:**
The bot accepts webhooks from:
1. **Telegram's official IP ranges** (automatically validated)
2. **Localhost** (`127.0.0.1`) for testing

The proxy itself is not a webhook source; it only supplies the real client IP.

**Firewall:**
With Cloudflare Tunnel the VPS needs **no inbound webhook port**. Close all inbound traffic except SSH (and your management ports) at both the cloud provider's firewall/security group and the OS firewall:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw enable
```

Keep outbound `7844/tcp` and `7844/udp` open for `cloudflared`. Do not open `80`/`443` for the tunnel.

> ⚠️ UFW does **not** filter Docker-published ports. Docker writes DNAT rules that bypass UFW's INPUT chain. This is why the Compose file binds the port to `127.0.0.1` instead of relying on the firewall alone.

**Security Best Practices:**
- Never set `FASTAPI_BIND_ADDR=0.0.0.0`
- Always use Cloudflare Tunnel (or a local reverse proxy)
- Keep `TG_SECRET_TOKEN` secure and unique
- Regularly update the Docker images
- Monitor logs for suspicious activity
- Run `./run.sh security-check` after changing ports/network settings

## 🔧 Manual Setup

### 1. Build the Image
```bash
cd docker/
docker compose --env-file ../.env build
```

### 2. Create Required Directories
```bash
mkdir -p ../data ../logs ../secret ../diff
```

### 3. Set Permissions
```bash
# Ensure proper ownership
sudo chown -R $USER:$USER ../data ../logs ../secret ../diff
chmod -R 755 ../data ../logs ../secret ../diff
```

### 4. Run Container
```bash
# Interactive mode (recommended for first setup)
docker compose --env-file ../.env run --rm hidego-tgbot

# Detached mode
docker compose --env-file ../.env up -d
```

Important: direct `docker compose` commands must include `--env-file ../.env` from the `docker/` directory. Compose uses that file for `${FASTAPI_PORT}` and `${FASTAPI_BIND_ADDR}` interpolation in ports and healthchecks; `env_file:` only passes variables into the container.

This project also sets the Compose project name to `hidego-tgbot`. Do not remove it. Without a unique project name, Compose defaults to the folder name, so multiple bots deployed from folders named `docker` can accidentally stop each other on `down`, cleanup, or rebuild flows. If you copy this Docker setup for another bot, change `name:`, `COMPOSE_PROJECT_NAME`, and container names to unique values.

## 📱 Container Management

### Using the Helper Script

The `run.sh` script provides convenient container management:

```bash
# Start the bot and enable watchdog recovery
./run.sh start

# Start with rebuild
./run.sh start -b

# Reconcile/recreate missing, exited, or unhealthy containers
./run.sh recover

# Install a systemd timer that runs recover every 2 minutes
./run.sh install-watchdog

# Check compose/container/watchdog state
./run.sh status
./run.sh watchdog-status

# Stop all containers and disable watchdog recovery
./run.sh stop

# View logs
./run.sh logs

# Open shell in running container
./run.sh shell

# Clean up unused resources
./run.sh cleanup
```

Production warning: Docker manual password mode is not unattended-recoverable. If Infisical is not configured, a recreated container may wait for password input after reboot, prune, or `docker compose down`. Use Infisical before installing the watchdog.

## 🪶 Lean Deployments (low-end VPS / shared host)

Opt-in per run — nothing is hardcoded, default runs stay full-performance:

```bash
./run.sh start --lean        # or: LEAN_MODE=1 ./run.sh start
```

For a **persistent** low-end deployment, also add this to `.env`:

```bash
LEAN_MODE=1
```

`run.sh recover` (used by the systemd watchdog) reads `.env`, so the RAM/CPU caps stay applied after reboots, crashes, and container recreation. Without this line, a watchdog recovery would silently recreate the stack without the lean override.

This loads `docker-compose.lean.yml` on top of the base file: RAM/CPU caps (bot 512m/1 CPU, tunnel 128m/0.5 CPU), memory-backed `/tmp`, calmer restart policy, single uvicorn worker. Override any value in `.env` (see `.env.example`); plain Compose equivalent:

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.lean.yml up -d
```

**Sizing guide (total VPS RAM):**

| VPS RAM | `BOT_MEM_LIMIT` | `TUNNEL_MEM_LIMIT` | `BOT_CPUS` / `TUNNEL_CPUS` | Also |
|---------|-----------------|--------------------|----------------------------|------|
| 512 MB | `320m` | `96m` | `0.75` / `0.25` | Add 1–2 GB swap |
| 1 GB | `448m` | `128m` | `1.0` / `0.5` | 1 GB swap recommended |
| ≥2 GB | default `512m` | default `128m` | default | Optional |

These are caps, not reservations; the bot usually idles well below them. If the container is OOM-killed (`docker inspect -f '{{.State.OOMKilled}}' hidego-tgbot`), lower `BOT_MEM_LIMIT` only after checking actual usage with `docker stats`.

### Prebuilt Images (recommended on a small VPS)

The `Publish container image` GitHub Actions workflow builds the image on
GitHub's runners and pushes it to GitHub Container Registry (GHCR). The VPS
then pulls the finished image — no `pip install`, compiler, or build step runs
on the 1 vCPU box.

```bash
cd docker

./run.sh pull                     # latest image built from main
./run.sh pull sha-583442a         # pin an exact build
```

`./run.sh pull` downloads the image, re-tags it as the local
`hidego-tgbot/bot:latest`, and starts the stack with `--no-build`. Use
`BOT_IMAGE_REPO` / `IMAGE_TAG` in `.env` to change the registry or default tag.

**First pull / private package:** GHCR packages are private by default even
for public repositories. Either make the package public in its GitHub package
settings, or authenticate once on the VPS:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

The token only needs `read:packages`.

**Why this is safer than building on the VPS:**

- The image is built from a clean GitHub runner, not from whatever happens to
  be in the VPS working tree.
- The workflow runs `ruff check .` and `mypy` before publishing, so a broken
  or untyped commit never becomes an image.
- Every build gets a per-commit `sha-<commit>` tag plus OCI labels, SBOM, and
  build provenance. Pin that tag — or the digest from the Actions summary —
  for reproducible deployments instead of tracking `latest`.
- `/safetycheck` compares the container against the exact `GIT_COMMIT` baked
  into the image, so a published image is not reported as modified just
  because `main` advanced after it was built.

A prebuilt image is not automatically more secure: you are trusting GitHub
Actions and GHCR to build and store it. The safeguards are the quality gate,
immutable tags, provenance/SBOM, and least-privilege workflow permissions. The
local build path (`./run.sh start -b`) remains available if you prefer to
build from your own checkout.

**Building on a very low-end VPS:** the image build runs `pip install` for the full dependency set and can OOM below ~1 GB RAM. Either add swap first:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

or build on a stronger machine and copy the image (same CPU architecture — `amd64` vs `arm64` matters):

```bash
# On the build machine (same architecture):
docker build -t hidego-tgbot/bot:latest -f docker/Dockerfile .
docker save hidego-tgbot/bot:latest | gzip > hidego-bot.tar.gz
scp hidego-bot.tar.gz user@new-vps:

# On the new VPS:
gunzip -c hidego-bot.tar.gz | docker load
```

The cloudflared image is tiny and can be built on the VPS.

Stay small over time: `./run.sh prune` (project-scoped, keeps one latest image per service) or `./run.sh prune --full` (also evicts stale builder cache). Sibling projects are never touched.

For a complete clone/backup/migration runbook, see [MIGRATION.md](MIGRATION.md).

### Direct Docker Commands

```bash
# Check running containers
docker ps

# View logs
docker logs -f hidego-tgbot

# Execute commands in container
docker exec -it hidego-tgbot bash

# If container name is different (from docker compose run)
docker exec -it $(docker ps --format "table {{.Names}}" | grep hidego-tgbot | head -1) bash

# Stop container
docker stop hidego-tgbot

# Remove container
docker rm hidego-tgbot

# Remove image
docker rmi hidego-tgbot
```

## 🔍 Troubleshooting

### Common Issues

**Permission Denied:**
```bash
# Fix ownership
sudo chown -R $USER:$USER data/ logs/ secret/ diff/
chmod -R 755 data/ logs/ secret/ diff/
```

**Port Already in Use:**
```bash
# Check what's using the port
sudo netstat -tlnp | grep :13360

# Kill the process or change FASTAPI_PORT in .env
```

**Container Won't Start:**
```bash
# Check logs
docker logs hidego-tgbot

# Rebuild image
docker compose --env-file ../.env build --no-cache
```

**Database Issues:**
```bash
# Remove corrupted database
rm -f data/DATA.db*

# Restart container to recreate
docker compose --env-file ../.env restart
```

### Debug Mode

Enable verbose logging by modifying `src/configs/settings.py`:
```python
LOGGER_STREAM_LEVEL: Final = 'DEBUG'
LOGGER_FILE_LEVEL: Final = 'DEBUG'
```

### Network Issues

Check Docker network:
```bash
# List networks
docker network ls

# Inspect network
docker network inspect hidego-tgbot_hidego-network

# Test connectivity
docker exec hidego-tgbot ping 8.8.8.8
```

## 🔒 Security Considerations

### Container Security

- **Non-root user**: Container runs as host user (UID/GID mapping)
- **No new privileges**: Security option prevents privilege escalation
- **Read-only .env**: Environment file mounted as read-only
- **No resource limits by default**: unrestricted CPU and memory for optimal performance (opt-in caps: see [Lean Deployments](#-lean-deployments-low-end-vps--shared-host))

### Network Security

- **Isolated network**: Custom bridge network isolates container
- **Webhook validation**: Only Telegram IPs can send webhooks
- **Secret token**: Additional webhook security layer
- **Proxy trust**: Configurable trusted proxy IP ranges

### Data Security

- **Encrypted storage**: Sensitive data encrypted with user-provided key
- **Zero-knowledge**: Partial hash storage prevents admin decryption
- **Volume mounting**: Persistent data stored outside container
- **Secure config**: Encryption keys stored in separate secure file

## 💾 Volume Management

### Persistent Data Volumes

The following directories are mounted as volumes:

```yaml
volumes:
  - ../data:/app/data      # Database and application data
  - ../logs:/app/logs      # Application logs
  - ../secret:/app/secret  # Encryption keys and secure config
  - ../diff:/app/diff      # GitHub safety check differences
  - ../.env:/app/.env:ro   # Environment configuration (read-only)
```

### Backup Strategy

**Create Backup:**
```bash
# Stop container
./run.sh stop

# Create backup
tar -czf backup-$(date +%Y%m%d).tar.gz data/ logs/ secret/ .env

# Restart container
./run.sh start
```

**Restore Backup:**
```bash
# Stop container
./run.sh stop

# Extract backup
tar -xzf backup-YYYYMMDD.tar.gz

# Set permissions
chmod -R 755 data/ logs/ secret/

# Restart container
./run.sh start
```

### Data Migration

**Export Data:**
```bash
# Export database
sqlite3 data/DATA.db .dump > database_backup.sql

# Export logs
cp -r logs/ logs_backup/
```

**Import Data:**
```bash
# Import database
sqlite3 data/DATA.db < database_backup.sql

# Restore logs
cp -r logs_backup/* logs/
```

## 🚀 Production Deployment

### Recommended Production Setup

1. **Use a reverse proxy** (nginx, Cloudflare Tunnel)
2. **Enable HTTPS** with valid SSL certificates
3. **Set up the host watchdog** with `./run.sh install-watchdog`
4. **Configure log rotation** to prevent disk space issues
5. **Set up automated backups**
6. **Use a dedicated server** or VPS
7. **Configure the firewall** to deny all inbound traffic except SSH; allow `cloudflared` egress on `7844/tcp+udp`

### Automatic Recovery Watchdog

Docker restart policies only restart containers that still exist. They do not recreate a stack after `docker compose down`, container removal, image pruning, or an unhealthy-but-running container. This project includes a host watchdog for those cases.

The watchdog is scoped to the `hidego-tgbot` Compose project and exact container names, so it must not stop unrelated Docker projects.

```bash
cd docker/

# Start once and remove any intentional-stop marker
./run.sh start

# Install the systemd timer on the host
./run.sh install-watchdog

# Verify the timer/service
./run.sh watchdog-status

# Run the same recovery pass manually
./run.sh recover
```

The watchdog runs `./run.sh recover` every 2 minutes after boot. It recreates missing containers/images, restarts unhealthy containers, starts Cloudflare Tunnel when `config.yml` and `credentials.json` exist, and leaves the stack stopped after `./run.sh stop` or `./run.sh cleanup` until the next `./run.sh start`.

### Sample nginx Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /path/to/certificate.pem;
    ssl_certificate_key /path/to/private.key;
    
    location / {
        proxy_pass http://localhost:13360;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Health Monitoring

The compose file already includes this healthcheck (Python stdlib probe — the image ships no curl binary):
```yaml
healthcheck:
  test: ["CMD-SHELL", "python -c \"import os,urllib.request;urllib.request.urlopen('http://localhost:'+os.environ.get('FASTAPI_PORT','13360')+'/health',timeout=8)\" || exit 1"]
  interval: 300s
  timeout: 10s
  retries: 3
  start_period: 120s
```

`interval` is 300s on purpose: every probe starts a separate Python
interpreter, and 60s polling spent CPU quota on a stable 24/7 bot for no
practical gain. Failures still surface after the three retries.

---

## � Troubleshooting

### 403 Forbidden Webhook Security Blocked

**Problem**: You see error `403 Forbidden webhook security blocked: 172.X.X.X`.

**Cause**: The request reached the bot from an address that is not in `TRUSTED_PROXY_CIDRS`, or the trusted proxy did not send `CF-Connecting-IP` / `X-Forwarded-For`.

**Solution**:
1. Confirm the bot's port is reached through `cloudflared`, not directly
2. Verify the proxy addresses match `.env`:
   ```bash
   # Check gateway and cloudflared address
   docker network inspect hidego-tgbot_hidego-network | grep -A 8 "IPAM"

   # Should match TRUSTED_PROXY_CIDRS in .env
   grep TRUSTED_PROXY_CIDRS ../.env
   ```
3. If you changed the subnet, update both `.env` and the `cloudflared` static IP, then recreate:
   ```bash
   cd docker
   docker compose --env-file ../.env down
   docker compose --env-file ../.env up -d
   ```

### Container Won't Start

**Problem**: Container exits immediately after starting.

**Solutions**:
- Check logs: `docker compose --env-file ../.env logs -f hidego-tgbot`
- Verify all required environment variables in `.env`
- Ensure bot token is valid: `MAIN_BOT_TOKEN=123456:ABC-DEF...`
- Check file permissions: `chmod 600 .env`

### Network Connection Errors

**Problem**: `httpx.ConnectError` or timeout errors in logs.

**Solutions**:
- Verify Cloudflare tunnel is running
- Check webhook URL is accessible: `curl -I https://your-domain.com/webhook`
- Increase timeout values in `.env`:
  ```
  TELEGRAM_REQUEST_TIMEOUT=60
  TELEGRAM_CONNECTION_TIMEOUT=20
  TELEGRAM_READ_TIMEOUT=60
  ```
- Check Docker network connectivity: `docker network inspect hidego-tgbot_hidego-network`

### Database Permission Issues

**Problem**: `OperationalError: unable to open database file`

**Solutions**:
- Ensure data directory exists and has correct permissions
- Check volume mounts in `docker-compose.yml`
- Try recreating the volume:
  ```bash
  docker compose --env-file ../.env down -v
  docker compose --env-file ../.env up -d
  ```

### Port Already in Use

**Problem**: `Bind for 127.0.0.1:13360 failed: port is already allocated`

**Solutions**:
- Change `FASTAPI_PORT` in `.env` to an available port (and update `cloudflared/config.yml`)
- Check what's using the port: `sudo lsof -i :13360`
- Stop conflicting service or use different port

---

## �📞 Support

For issues and questions:
- **GitHub Issues**: [Repository Issues](https://github.com/411A/Telegram-Anonymous-Messaging-Bot-Creator/issues)
- **Documentation**: Check the main [README.md](../README.md)
- **Docker Documentation**: [Official Docker Docs](https://docs.docker.com/)
