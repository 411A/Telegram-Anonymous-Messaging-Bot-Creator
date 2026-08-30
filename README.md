<div align="center">

# 🤖 <b>Hid</b>den<b>Ego</b>
### Telegram Anonymous Messaging Bot Creator

*Launch your own zero-knowledge anonymous messaging bot in minutes — with enterprise-grade security, multi-bot management, and verifiable open-source transparency.*

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/411A/Telegram-Anonymous-Messaging-Bot-Creator)
[![Telegram](https://img.shields.io/badge/Telegram-%40HidEgoBot-2CA5E0?logo=telegram&logoColor=white)](https://t.me/HidEgoBot)

</div>

---

---

## 🌟 **Overview**  
This project provides a comprehensive framework for building Telegram bots that handle anonymous messaging. With built-in features such as message forwarding, history management, and administrative controls, it allows you to deploy a secure and feature-rich messaging system. The project is designed with scalability and maintainability in mind, leveraging clear constants and modular code across configurations, handlers, and utility functions.

---

## 📦 **Features**  
- **Anonymous Messaging**: Send or Forward messages without revealing your identity.  
- **History Management**: Options for sending messages with or without message history.  
- **Interactive Controls**: Inline buttons with emojis for actions like forwarding, blocking, and reading messages.  
- **Webhook Integration**: Seamless integration with Telegram’s webhook API.  
- **Secure Configuration**: Separation of sensitive data using secure configuration files.  
- **Live GitHub Comparison**:
Users can directly inspect and compare the deployed application with its GitHub repository counterpart using the `/safetycheck` command, ensuring complete transparency and fostering community trust.
- **Zero-Knowledge Security:** We only store a **partial hash** of encrypted data in the database, meaning even admins **cannot** decrypt it. Decryption is only possible when users provide their unique hash fragment, and the process happens entirely in memory—without being logged—ensuring ultimate privacy.
- **Strongly Typed & Lint-Clean**: CI-grade `mypy` + `ruff` configuration enforces production-grade code quality.
- **Graceful Resilience**: Circuit breakers, retry with exponential backoff, webhook deduplication, IP allow-listing, and a Docker watchdog keep the service healthy.

---

## 💰 **Donations**
If you find this project helpful, you can support its development through donations on the TON blockchain:

💎 Donate via TON:
```
ton://transfer/TechKraken.ton
```
```
UQCGk4IU5nm6dYWjXTx6vSQVOtKO4LQg3m8cRcq1eQo7vhCl
```

---

## 📋 **Prerequisites**

- **Python 3.10+** (for native installation; Docker uses Python 3.12)
- **Docker & Docker Compose** (for containerized deployment)
- **Telegram Bot Token** from [@BotFather](https://t.me/BotFather)
- **Domain with Cloudflare** (optional, for production with Cloudflare Tunnel)
- **ngrok** (optional, for local development webhook testing)

---

## 🚀 **Quick Start**

Choose your deployment method:

### Option 1: 🐳 Docker (Recommended for Production)

**Best for**: Production deployments, easy management, includes Cloudflare Tunnel support

```bash
# 1. Clone the repository
git clone https://github.com/411A/Telegram-Anonymous-Messaging-Bot-Creator.git
cd Telegram-Anonymous-Messaging-Bot-Creator

# 2. Configure environment
cp .env.example .env
nano .env  # Edit with your bot token and settings

# 3. Start the bot
cd docker/
chmod +x run.sh
./run.sh start
```

See [docker/README.md](docker/README.md) for complete Docker documentation and [docker/cloudflared/README.md](docker/cloudflared/README.md) for Cloudflare Tunnel setup.

### Option 2: 🐍 Python (Development & Testing)

**Best for**: Local development, testing, quick experiments

```bash
# 1. Clone the repository
git clone https://github.com/411A/Telegram-Anonymous-Messaging-Bot-Creator.git
cd Telegram-Anonymous-Messaging-Bot-Creator

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
nano .env  # Edit with your bot token and settings

# 4. Run the bot
cd src/
python bot_creator.py
```

---

## ⚙️ **Configuration**

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

**Required Settings:**

| Variable | Description | Example |
|----------|-------------|---------|
| `BOT_CREATOR_USERNAME` | Your bot's username | `@YourBot` |
| `MAIN_BOT_TOKEN` | Telegram Bot API token from @BotFather | `123456:ABC-DEF...` |
| `WEBHOOK_BASE_URL` | Public HTTPS URL for webhooks | `https://bot.yourdomain.com` |
| `TG_SECRET_TOKEN` | Secret token for webhook security | `random-secure-string` |
| `FASTAPI_PORT` | Port for the FastAPI server | `13360` (default) |
| `LOG_FILENAME` | Log file name | `Logs.log` |
| `LOGGER_TIMEZONE` | Timezone for logs | `Asia/Tehran` or `UTC` |
| `DOCKER_NETWORK_IP` | Docker network gateway (for Docker setup) | `172.30.0.1/24` |

**Getting Your Bot Token:**
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the provided token to `MAIN_BOT_TOKEN`

**Generating Secret Token:**
```bash
# Linux/macOS
openssl rand -base64 32

# Or use any random string generator
```

### Master Password

#### Infisical

Add to `.env` or Docker secrets: `INFISICAL_SECRET_NAME=ANONYMOUS_MASTER_PASSWORD`, `INFISICAL_CLIENT_ID=...`, `INFISICAL_CLIENT_SECRET=...`, `INFISICAL_PROJECT_ID=...`, `INFISICAL_ENVIRONMENT=prod`
Create an Infisical **Machine Identity** with **Viewer** role and generate **Universal Auth** credentials (Copy Client ID & Secret).
Ensure the identity has access to the `prod` environment and store the master password using the secret name above.
Restart the bot — the master password is securely fetched from Infisical at startup (read-only).

Read more here: https://infisical.com/docs/sdks/languages/python

#### Manual

On first run, you'll be prompted to set a **master password** (minimum 12 characters). This password:
- Encrypts all data in the database
- Uses **zero-knowledge security** (partial hash storage)
- Cannot be recovered if lost - keep it safe!

The hashed password is stored in `secret/config.secure`.

Warning for Docker production: manual password mode is not unattended-recoverable. After a host reboot, `docker prune`, `docker compose down`, or a container recreation, the bot can wait for terminal input and stay offline until an operator attaches. Use Infisical for production Docker deployments.

---

## 🔧 **Deployment Guide**

### 🧪 Development Setup (Local Testing)

#### Using ngrok for Webhook Testing

[ngrok](https://ngrok.com/) creates a secure tunnel to your local server for webhook testing.

```bash
# 1. Install ngrok (if not already installed)
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok

# 2. Start ngrok tunnel
ngrok http 13360

# 3. Copy the HTTPS URL (e.g., https://xxxx.ngrok-free.app)
# 4. Update WEBHOOK_BASE_URL in .env with the ngrok URL
```

#### Running the Bot (Python)

```bash
cd src/
python bot_creator.py
```

On first run, set your master password (min. 12 characters).

---

### 🚀 Production Deployment

#### Method 1: Docker + Cloudflare Tunnel (Recommended)

This is the **most secure and manageable** production setup.

##### Step 1: Prepare Cloudflare Tunnel

**Prerequisites:** Domain registered with Cloudflare

```bash
# 1. Install cloudflared
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/

# 2. Login to Cloudflare
cloudflared tunnel login
# Click the authentication link in your browser

# 3. Create tunnel
cloudflared tunnel create hidego-tgbot
# Save the tunnel ID from output
```

##### Step 2: Configure Cloudflare for Docker

```bash
cd docker/cloudflared/

# Copy your tunnel credentials
cp ~/.cloudflared/<TUNNEL_ID>.json ./credentials.json

# Create config.yml
nano config.yml
```

Add to `config.yml`:
```yaml
tunnel: YOUR_TUNNEL_ID_HERE
credentials-file: /etc/cloudflared/credentials.json

ingress:
  - hostname: webhook.yourdomain.com
    # Use container name and your FASTAPI_PORT
    service: http://hidego-tgbot:13360
  - service: http_status:404
```

```bash
# Create DNS route
cloudflared tunnel route dns hidego-tgbot webhook.yourdomain.com
```

##### Step 3: Update .env

```bash
cd ../../
nano .env
```

Update:
```bash
WEBHOOK_BASE_URL=https://webhook.yourdomain.com
FASTAPI_PORT=13360  # Must match config.yml
```

##### Step 4: Start Everything

```bash
cd docker/
./run.sh start
```

**Verify tunnel is connected:**
```bash
./run.sh tunnel status
./run.sh tunnel logs
```

See detailed Docker + Cloudflare guide: [docker/cloudflared/README.md](docker/cloudflared/README.md)

#### Method 2: Docker + nginx + SSL

For deployments with your own reverse proxy:

```bash
# 1. Configure .env with your domain
WEBHOOK_BASE_URL=https://yourdomain.com

# 2. Start bot only (without cloudflared)
cd docker/
./run.sh start

# 3. Configure nginx to proxy to port 13360
# See docker/README.md for nginx configuration example
```

#### Method 3: Python + Cloudflare Tunnel

Traditional setup without Docker:

```bash
# 1. Create and configure Cloudflare Tunnel
cloudflared tunnel create hidego-tgbot

# 2. Create ~/.cloudflared/config.yml
tunnel: YOUR_TUNNEL_ID
credentials-file: /home/user/.cloudflared/YOUR_TUNNEL_ID.json

ingress:
  - hostname: webhook.yourdomain.com
    service: http://localhost:13360
  - service: http_status:404

# 3. Start tunnel in tmux
tmux new -s cloudflared
cloudflared tunnel --config ~/.cloudflared/config.yml run hidego-tgbot
# Ctrl+B, D to detach

# 4. Run bot
cd src/
python bot_creator.py
```

---

## 📊 Management Commands

### Docker Commands

```bash
cd docker/

# Start bot (and tunnel if configured)
./run.sh start

# Install host watchdog recovery after Infisical is configured
./run.sh install-watchdog

# Start with rebuild
./run.sh start -b

# Reconcile/recreate containers immediately
./run.sh recover

# Stop everything
./run.sh stop

# View logs
./run.sh logs                # Bot logs
./run.sh tunnel logs         # Tunnel logs

# Check status
./run.sh status
./run.sh watchdog-status

# Tunnel management
./run.sh tunnel start        # Start tunnel only
./run.sh tunnel stop         # Stop tunnel only
./run.sh tunnel status       # Check status
./run.sh tunnel restart      # Restart tunnel

# Shell access
./run.sh shell              # Open shell in bot container

# Clean up
./run.sh cleanup            # Remove all containers
```

The Docker setup uses a fixed Compose project name (`hidego-tgbot`) so `stop`, `cleanup`, rebuilds, and watchdog recovery only target this bot. If you duplicate this setup for another bot, give that bot its own unique Compose project name and container names.

### Python Commands

```bash
# Run bot
cd src/
python bot_creator.py

# Check logs
tail -f logs/Logs.log

# View database
sqlite3 data/DATA.db
```

---

## 🔄 **Updating from GitHub**

Your configuration files are protected by `.gitignore` and won't be overwritten:

```bash
cd Telegram-Anonymous-Messaging-Bot-Creator

# Fetch and update from GitHub
git fetch origin && git checkout origin/main .

# Your protected files:
# ✅ .env
# ✅ docker/cloudflared/config.yml
# ✅ docker/cloudflared/credentials.json
# ✅ secret/config.secure
# ✅ data/, logs/, diff/
```

---

## 🔍 **Monitoring & Troubleshooting**

### Check Bot Status

```bash
# Docker
docker ps | grep hidego-tgbot
docker logs -f hidego-tgbot

# Python
tail -f logs/Logs.log
```

### Check Tunnel Status

```bash
# Docker
./run.sh tunnel status
docker logs hidego-cloudflared | grep "registered tunnel connection"

# Python + tmux
tmux attach -t cloudflared
```

### Test Webhook

```bash
curl https://webhook.yourdomain.com/health
```

### Common Issues

**Issue**: Bot can't connect to Telegram  
**Solution**: Check `MAIN_BOT_TOKEN` in `.env` is correct

**Issue**: Webhook not receiving updates  
**Solution**: 
- Verify `WEBHOOK_BASE_URL` is publicly accessible
- Check `TG_SECRET_TOKEN` matches
- Ensure HTTPS is working

**Issue**: Cloudflare tunnel connection refused  
**Solution**: 
- Docker: Verify `service: http://hidego-tgbot:PORT` uses correct port
- Python: Verify `service: http://localhost:PORT` uses correct port
- Check `FASTAPI_PORT` in `.env` matches config

**Issue**: Database errors  
**Solution**: Check `data/` directory has write permissions

---

## 📚 **Documentation**

- [Docker Setup Guide](docker/README.md) - Complete Docker documentation
- [Cloudflare Tunnel Setup](docker/cloudflared/README.md) - Dockerized Cloudflare Tunnel

---

## 🤝 **Contributing**  
Contributions are welcome! If you have ideas, bug fixes, or improvements, please open an issue or submit a pull request. Follow standard GitHub practices and ensure your code aligns with the project's guidelines.

### 🧹 Code Quality

The codebase is strictly typed and linted. Configuration lives in `pyproject.toml`.

```bash
# Lint (ruff) and type-check (mypy)
python -m ruff check .
python -m mypy
```

All contributions must pass both checks with zero errors before being merged.

---

## 📞 **Contact & Support**  
For support or any inquiries, please reach out via:  
- **Telegram**: [Contact the Developer](https://t.me/ContactHydraBot)  
- **GitHub Repository**: [Telegram Anonymous Messaging Bot Creator](https://github.com/411A/Telegram-Anonymous-Messaging-Bot-Creator)
