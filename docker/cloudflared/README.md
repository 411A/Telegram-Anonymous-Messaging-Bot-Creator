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
    # Telegram only calls /webhook/<bot_token>. Everything else is rejected.
    path: ^/webhook/
    # IMPORTANT: Use the Compose service name, not localhost.
    # The port must match FASTAPI_PORT in .env (default: 13360).
    service: http://hidego-tgbot:13360
  # Default rule: reject all other hosts and paths
  - service: http_status:404
```

**Key Changes:**
- `http://localhost:PORT` (host-run cloudflared) → `http://hidego-tgbot:PORT` (Dockerized cloudflared)
- Use the **service name** (`hidego-tgbot`) from `docker-compose.yml`
- Use your actual `FASTAPI_PORT` from `.env` (for example, `14143`)
- Keep the `path: ^/webhook/` rule so `/health` and future routes are not public

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
docker compose --env-file ../.env up -d
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
    restart: always
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
docker compose --env-file ../.env up -d
```

### View Cloudflared Logs
```bash
docker logs -f hidego-cloudflared
```

### Restart Cloudflared Only
```bash
docker compose --env-file ../.env restart cloudflared
```

### Stop Everything
```bash
docker compose --env-file ../.env down
```

### Rebuild Cloudflared
```bash
docker compose --env-file ../.env build cloudflared
docker compose --env-file ../.env up -d cloudflared
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
# The cloudflared image is minimal (no shell); test from the bot container.
docker exec -it hidego-tgbot sh -c 'curl -fsS "http://127.0.0.1:${FASTAPI_PORT}/health"'
```

### Check Network Connectivity
```bash
# Verify both containers are on the same network
docker network inspect hidego-tgbot_hidego-network

# Test the Compose service name from inside the bot container
docker exec -it hidego-tgbot sh -c 'curl -fsS "http://hidego-tgbot:${FASTAPI_PORT}/health"'
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

**Problem**: Cloudflare returns `error code: 1033`
**Solution**: The tunnel is not connected. Check `docker ps` and
`docker logs hidego-cloudflared`; the tunnel must be `Healthy` in the Cloudflare
dashboard. Also verify outbound `7844/tcp` and `7844/udp` are allowed.

## 🔐 Security Notes

1. **No inbound port**: `cloudflared` only makes outbound connections to Cloudflare on `7844/tcp+udp`. The VPS does not need `80` or `443` open.
2. **Loopback-only bot port**: Compose publishes `FASTAPI_PORT` on `127.0.0.1`, so even a misconfigured firewall cannot expose it publicly. The tunnel uses the Compose service name, not that host port.
3. **Path-restricted ingress**: `path: ^/webhook/` means only Telegram's webhook path is routed; every other path returns 404.
4. **One public port**: Telegram and Cloudflare clients only need `https://webhook.yourdomain.ir` on `443`. Cloudflare's edge also listens on other supported ports for all customers, but you can reject those requests for this hostname with a WAF custom rule:
   - Expression: `(http.host eq "webhook.yourdomain.ir" and not cf.edge.server_port in {443})`
   - Action: **Block**
5. **Protect tunnel credentials**: `chmod 600 credentials.json` and keep it out of Git. Anyone who obtains it can run another connector on the same tunnel and receive webhook traffic (including bot tokens). Rotate the tunnel credentials if they leak.
6. **Never commit credentials**: The `.gitignore` file prevents committing sensitive files
7. **Read-only mounts**: Configuration files are mounted as read-only (`:ro`)
8. **No privileged access**: Container runs without additional privileges
9. **Isolated network**: Containers communicate on private Docker network; only `172.30.0.1` and `172.30.0.2` are trusted proxies

## 🌟 Advantages of Dockerized Cloudflare Tunnel

✅ **Everything in one place**: Bot and tunnel managed together
✅ **Easy deployment**: Single `./run.sh start` command
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
   docker compose --env-file ../.env up -d
   ```

Your tunnel will now run as a proper Docker service! 🎉
