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
- **Port availability** (default: 8000, configurable via `.env`)

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
FASTAPI_PORT=8000

# Docker Network Configuration
DOCKER_NETWORK_IP=172.21.0.0/16

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
ngrok http 8000

# Copy the HTTPS URL to WEBHOOK_BASE_URL in .env
```

**For Production:**
- Use a reverse proxy (nginx, Cloudflare Tunnel)
- Ensure HTTPS is enabled
- Point to your server's public IP/domain

## 🌐 Docker Network Configuration

### DOCKER_NETWORK_IP Field

The `DOCKER_NETWORK_IP` field in your `.env` file configures the Docker network subnet for the bot container:

```bash
DOCKER_NETWORK_IP=172.21.0.0/16
```

**Purpose:**
- Defines the IP range for the Docker bridge network
- Ensures network isolation and security
- Prevents conflicts with existing network ranges
- Used by webhook validation and trusted proxy settings

**Configuration Options:**
```bash
# Default (recommended)
DOCKER_NETWORK_IP=172.21.0.0/16

# Alternative ranges
DOCKER_NETWORK_IP=172.20.0.0/16
DOCKER_NETWORK_IP=10.0.0.0/16
DOCKER_NETWORK_IP=192.168.100.0/24
```

**Important Notes:**
- Choose a range that doesn't conflict with your host network
- Use CIDR notation (e.g., `/16`, `/24`)
- Private IP ranges are recommended (10.x.x.x, 172.16-31.x.x, 192.168.x.x)

### 🔍 Finding Your Docker Network IP

**Step 1: Start Docker Container**
```bash
cd docker/
./run.sh start
# or
docker compose up -d
```

**Step 2: Inspect the Docker Network**
```bash
# Find your network name (usually ends with _hidego-network)
docker network ls

# Inspect the network to get the subnet
docker network inspect docker_hidego-network
# or if the network name is different:
docker network inspect <network-name>
```

**Step 3: Update .env File**
Look for the `"Subnet"` field in the network inspection output and copy that value to your `.env` file:

```json
"IPAM": {
    "Config": [
        {
            "Subnet": "172.21.0.0/16"  # Copy this value
        }
    ]
}
```

Then update your `.env` file:
```bash
DOCKER_NETWORK_IP=172.21.0.0/16
```

**Step 4: Restart Container**
```bash
./run.sh stop
./run.sh start
```

### Network Security

The Docker network configuration includes:
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
sudo netstat -tlnp | grep :8000

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
        proxy_pass http://localhost:8000;
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
  test: ["CMD", "curl", "-f", "http://localhost:${FASTAPI_PORT:-8000}/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

---

## 📞 Support

For issues and questions:
- **GitHub Issues**: [Repository Issues](https://github.com/411A/Telegram-Anonymous-Messaging-Bot-Creator/issues)
- **Documentation**: Check the main [README.md](../README.md)
- **Docker Documentation**: [Official Docker Docs](https://docs.docker.com/)
