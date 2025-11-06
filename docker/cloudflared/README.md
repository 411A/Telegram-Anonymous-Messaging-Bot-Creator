# 🌐 Cloudflare Tunnel Docker Setup

This directory contains the Docker configuration for running Cloudflare Tunnel (cloudflared) in a container alongside your Telegram bot.

## 📋 Prerequisites

1. **Cloudflare Account** with a domain registered
2. **Cloudflare Tunnel created** (see setup instructions below)
3. **Tunnel credentials** (`.json` file)
4. **Tunnel configuration** (`config.yml`)

## 🚀 Quick Setup

### 1. Create Cloudflare Tunnel (If You Haven't Already)

If you already have a tunnel at `/home/USER/.cloudflared/`, skip to step 2.

```bash
# Login to Cloudflare
cloudflared tunnel login

# Create a new tunnel
cloudflared tunnel create hidego-tgbot

# This creates:
# - A tunnel with an ID (e.g., 7a3c2e4f-5b1d-4c9a-8e2f-3d6b7a9c1e2f)
# - A credentials file: ~/.cloudflared/<TUNNEL_ID>.json
```

### 2. Copy Your Existing Configuration

```bash
# Navigate to the cloudflared directory
cd docker/cloudflared/

# Copy your tunnel credentials file
cp /home/USER/.cloudflared/7a3c2e4f-5b1d-4c9a-8e2f-3d6b7a9c1e2f.json ./credentials.json

# Copy your config (we'll modify it)
cp /home/USER/.cloudflared/hidego_config.yml ./config.yml

# Optional: Copy certificate if needed
cp /home/USER/.cloudflared/hidego_cert.pem ./cert.pem
```

### 3. Update Configuration for Docker

Edit `config.yml` to use Docker service names:

```yaml
tunnel: 7a3c2e4f-5b1d-4c9a-8e2f-3d6b7a9c1e2f
credentials-file: /etc/cloudflared/credentials.json

ingress:
  - hostname: webhook.yourdomain.ir
    # IMPORTANT: Use container name instead of localhost
    # The port should match your FASTAPI_PORT in .env
    service: http://hidego-tgbot:4114
  # Default rule: all other requests return 404
  - service: http_status:404
```

**Key Changes:**
- `http://localhost:14143` → `http://hidego-tgbot:4114`
- Use the **container name** (`hidego-tgbot`) from `docker-compose.yml`
- Use your actual `FASTAPI_PORT` from `.env` (in your case: `4114`)

### 4. Verify Files

Make sure you have these files in `docker/cloudflared/`:
```
docker/cloudflared/
├── Dockerfile
├── config.yml              # Your tunnel configuration
├── credentials.json        # Your tunnel credentials
├── config.yml.example      # Example file (for reference)
└── README.md              # This file
```

### 5. Start Everything with Docker Compose

```bash
# From the docker/ directory
cd ../
./run.sh start

# Or manually:
docker compose up -d
```

## 🔧 Docker Compose Integration

The `cloudflared` service is now part of your main `docker-compose.yml`:

```yaml
services:
  hidego-tgbot:
    # ... your bot configuration ...
    networks:
      - hidego-network

  cloudflared:
    build:
      context: cloudflared
    container_name: hidego-cloudflared
    restart: unless-stopped
    volumes:
      - ./cloudflared/config.yml:/etc/cloudflared/config.yml:ro
      - ./cloudflared/credentials.json:/etc/cloudflared/credentials.json:ro
    networks:
      - hidego-network
    depends_on:
      - hidego-tgbot
```

## 📱 Management Commands

### Start Services
```bash
cd docker/
docker compose up -d
```

### View Cloudflared Logs
```bash
docker logs -f hidego-cloudflared
```

### Restart Cloudflared Only
```bash
docker compose restart cloudflared
```

### Stop Everything
```bash
docker compose down
```

### Rebuild Cloudflared
```bash
docker compose build cloudflared
docker compose up -d cloudflared
```

## 🔍 Troubleshooting

### Check if Tunnel is Connected
```bash
docker logs hidego-cloudflared | grep -i "registered tunnel connection"
```

You should see:
```
INF Registered tunnel connection connIndex=0 connection=<ID>
```

### Test Webhook Connection
```bash
# From inside the bot container
docker exec -it hidego-tgbot bash
curl http://localhost:4114/health  # Or your FASTAPI_PORT
```

### Check Network Connectivity
```bash
# Verify both containers are on the same network
docker network inspect docker_hidego-network

# Test from cloudflared to bot
docker exec -it hidego-cloudflared wget -O- http://hidego-tgbot:4114/health
```

### Common Issues

**Problem**: Cloudflared can't reach the bot
**Solution**: Ensure both services are on the same Docker network (`hidego-network`)

**Problem**: `connection refused`
**Solution**: 
- Verify `FASTAPI_PORT` in `.env` matches the port in `config.yml`
- Check bot is running: `docker ps | grep hidego-tgbot`

**Problem**: `invalid credentials file`
**Solution**: Verify the credentials file is correctly copied and has correct permissions

## 🔐 Security Notes

1. **Never commit credentials**: The `.gitignore` file prevents committing sensitive files
2. **Read-only mounts**: Configuration files are mounted as read-only (`:ro`)
3. **No privileged access**: Container runs without additional privileges
4. **Isolated network**: Containers communicate on private Docker network

## 🌟 Advantages of Dockerized Cloudflare Tunnel

✅ **Everything in one place**: Bot and tunnel managed together
✅ **Easy deployment**: Single `docker compose up -d` command
✅ **Automatic restart**: Tunnel auto-restarts if it crashes
✅ **No tmux needed**: Container runs as a proper service
✅ **Better logging**: Integrated with Docker logging
✅ **Network isolation**: Secure internal communication
✅ **Portable**: Easy to move to another server

## 📚 Additional Resources

- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [Docker Networking](https://docs.docker.com/network/)
- [Main Project README](../../README.md)

## 🔄 Migration from Standalone Cloudflared

If you were running cloudflared in tmux before:

1. Stop the tmux session:
   ```bash
   tmux kill-session -t cloudflare-anontgmsg
   ```

2. Copy your configuration to Docker (as shown above)

3. Start with Docker Compose:
   ```bash
   cd docker/
   docker compose up -d
   ```

Your tunnel will now run as a proper Docker service! 🎉
