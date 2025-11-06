# 🐳 Docker Setup Guide for HiddenEgo Telegram Bot

This guide provides comprehensive instructions for deploying the HiddenEgo Telegram Anonymous Messaging Bot using Docker.

## 📋 Table of Contents
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Environment Configuration](#environment-configuration)
- [Docker Network Configuration](#docker-network-configuration)
- [Manual Setup](#manual-setup)
- [Container Management](#container-management)
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
chmod +x run.sh
./run.sh start
```

### 4. Alternative: Direct Docker Compose
```bash
cd docker/
docker compose run --rm hidego-tgbot
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

# Docker Network Configuration (Fixed Network)
# This MUST match the gateway IP in docker-compose.yml
# Default: 172.30.0.1/24 (subnet: 172.30.0.0/24)
DOCKER_NETWORK_IP=172.30.0.1/24

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
- **Driver**: bridge

**Why Fixed Network?**
- Prevents IP conflicts with other Docker projects
- Consistent security configuration
- No need to update `DOCKER_NETWORK_IP` when creating new projects
- Easier to configure firewall rules

### DOCKER_NETWORK_IP Field

The `DOCKER_NETWORK_IP` field in your `.env` file specifies the trusted gateway IP for webhook security:

```bash
# This MUST match the gateway IP in docker-compose.yml
DOCKER_NETWORK_IP=172.30.0.1/24
```

**Purpose:**
- Validates incoming webhook requests from Cloudflare Tunnel or other proxies
- Ensures only requests from the Docker gateway are accepted
- Prevents unauthorized webhook access
- Works with the fixed network configuration in `docker-compose.yml`

**Important Notes:**
- ⚠️ **Must match the gateway IP** defined in `docker-compose.yml` (default: `172.30.0.1`)
- The `/24` subnet mask allows the entire `172.30.0.0/24` range
- Changing this requires updating both `.env` and `docker-compose.yml`

**Troubleshooting:**
If you see `403 Forbidden` errors with webhook security blocked:
1. Check that `DOCKER_NETWORK_IP` matches the gateway in `docker-compose.yml`
2. Verify with: `docker network inspect docker_hidego-network | grep Gateway`
3. Update `.env` if the gateway IP is different

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
DOCKER_NETWORK_IP=172.31.0.1/24      # Must match gateway above
```

**Recommended Subnet Ranges:**
- `172.30.0.0/24` (default) - Gateway: `172.30.0.1`
- `172.31.0.0/24` - Gateway: `172.31.0.1`
- `10.0.0.0/24` - Gateway: `10.0.0.1`
- `192.168.100.0/24` - Gateway: `192.168.100.1`

### 🔍 Verifying Your Network Configuration

**Check Current Network Settings:**
```bash
# List all Docker networks
docker network ls

# Inspect the hidego network
docker network inspect docker_hidego-network

# Quick gateway check
docker network inspect docker_hidego-network | grep -A 5 "IPAM"
```

**Verify Settings Match:**
```bash
# 1. Check docker-compose.yml gateway
grep -A 5 "hidego-network" docker-compose.yml

# 2. Check .env setting
grep "DOCKER_NETWORK_IP" ../.env

# 3. These should match!
```

## 🔒 Network Security

The fixed Docker network configuration provides several security benefits:

**Security Features:**
- Webhook validation against known Docker gateway IP
- Protection from unauthorized webhook sources
- Consistent security rules across deployments
- Easy firewall configuration with fixed IPs

**Trusted Sources:**
The bot accepts webhooks from:
1. **Telegram's official IP ranges** (automatically validated)
2. **Docker gateway IP** (configured in `.env`)
3. **Localhost** (`127.0.0.1`) for testing

**Security Best Practices:**
- Never expose the bot port directly to the internet
- Always use a reverse proxy (Cloudflare Tunnel, nginx)
- Keep `TG_SECRET_TOKEN` secure and unique
- Regularly update the Docker images
- Monitor logs for suspicious activity
- **Isolated bridge network** for container communication
- **Webhook IP validation** using Telegram's official IP ranges
- **Proxy trust configuration** for reverse proxy setups

## 🔧 Manual Setup

### 1. Build the Image
```bash
cd docker/
docker compose build
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
docker compose run --rm hidego-tgbot

# Detached mode
docker compose up -d
```

## 📱 Container Management

### Using the Helper Script

The `run.sh` script provides convenient container management:

```bash
# Start the bot (interactive)
./run.sh start

# Start with rebuild
./run.sh start -b

# Stop all containers
./run.sh stop

# View logs
./run.sh logs

# Open shell in running container
./run.sh shell

# Clean up unused resources
./run.sh cleanup
```

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
docker compose build --no-cache
```

**Database Issues:**
```bash
# Remove corrupted database
rm -f data/DATA.db*

# Restart container to recreate
docker compose restart
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
docker network inspect docker_hidego-network

# Test connectivity
docker exec hidego-tgbot ping 8.8.8.8
```

## 🔒 Security Considerations

### Container Security

- **Non-root user**: Container runs as host user (UID/GID mapping)
- **No new privileges**: Security option prevents privilege escalation
- **Read-only .env**: Environment file mounted as read-only
- **No resource limits**: Unrestricted CPU and memory for optimal performance (Can be restricted by uncommenting the resource limits in `docker-compose.yml`)

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
3. **Set up monitoring** (container health checks)
4. **Configure log rotation** to prevent disk space issues
5. **Set up automated backups**
6. **Use a dedicated server** or VPS
7. **Configure firewall** to allow only necessary ports

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

Add health check to `docker-compose.yml`:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:${FASTAPI_PORT:-13360}/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

---

## � Troubleshooting

### 403 Forbidden Webhook Security Blocked

**Problem**: You see error `403 Forbidden webhook security blocked: 172.X.X.X` after creating other Docker projects on the same host.

**Cause**: Docker assigns sequential network IP ranges (172.17.0.0/16, 172.18.0.0/16, etc.) to new projects. When you create another Docker project, your bot's network IP changes, but `DOCKER_NETWORK_IP` in `.env` still has the old value.

**Solution**:
1. Use the fixed network configuration (already implemented in this project)
2. Verify your network IP matches `.env`:
   ```bash
   # Check current network IP
   docker inspect telegram-bot-network | grep Subnet
   
   # Should match DOCKER_NETWORK_IP in .env
   cat .env | grep DOCKER_NETWORK_IP
   ```
3. If mismatched, restart containers to apply fixed network:
   ```bash
   cd docker
   docker-compose down
   docker-compose up -d
   ```

### Container Won't Start

**Problem**: Container exits immediately after starting.

**Solutions**:
- Check logs: `docker-compose logs -f telegram-bot`
- Verify all required environment variables in `.env`
- Ensure bot token is valid: `TELEGRAM_BOT_TOKEN=123456:ABC-DEF...`
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
- Check Docker network connectivity: `docker network inspect telegram-bot-network`

### Database Permission Issues

**Problem**: `OperationalError: unable to open database file`

**Solutions**:
- Ensure data directory exists and has correct permissions
- Check volume mounts in `docker-compose.yml`
- Try recreating the volume:
  ```bash
  docker-compose down -v
  docker-compose up -d
  ```

### Port Already in Use

**Problem**: `Bind for 0.0.0.0:13360 failed: port is already allocated`

**Solutions**:
- Change `FASTAPI_PORT` in `.env` to an available port
- Check what's using the port: `sudo lsof -i :13360`
- Stop conflicting service or use different port

---

## �📞 Support

For issues and questions:
- **GitHub Issues**: [Repository Issues](https://github.com/411A/Telegram-Anonymous-Messaging-Bot-Creator/issues)
- **Documentation**: Check the main [README.md](../README.md)
- **Docker Documentation**: [Official Docker Docs](https://docs.docker.com/)
