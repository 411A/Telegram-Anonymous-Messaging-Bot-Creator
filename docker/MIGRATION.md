# Moving HiddenEgo to a New VPS

This is the safe migration path: keep the existing database, encryption key,
Telegram webhook URL, and Cloudflare Tunnel, then run the new host in lean mode.

> **Critical:** run **one** bot and **one** `cloudflared` connector at a time.
> If the old VPS is still running, Cloudflare may route Telegram updates to a
> connector whose bot is stopped, producing intermittent `502`/`1033` errors.

## 1. Stop and back up the old VPS

```bash
cd /path/to/Telegram-Anonymous-Messaging-Bot-Creator

# Stop the bot and tunnel, and prevent the old watchdog from restarting them.
cd docker
./run.sh stop
sudo systemctl disable --now hidego-tgbot-watchdog.timer 2>/dev/null || true
# If cloudflared runs on the host (not Compose), stop it too:
# tmux kill-session -t cloudflared 2>/dev/null || pkill -f 'cloudflared tunnel' || true
cd ..

# Back up state. Include all SQLite sidecars (DATA.db-wal / DATA.db-shm).
files=(.env data logs secret diff)
for f in docker/cloudflared/config.yml docker/cloudflared/credentials.json; do
    [ -f "$f" ] && files+=("$f") || true
done
tar -czf "$HOME/hidego-backup-$(date +%F).tar.gz" "${files[@]}"
```

The archive contains:

| Path | Why it matters |
|------|----------------|
| `.env` | Bot token, `TG_SECRET_TOKEN`, Infisical credentials, port, hostname |
| `data/` | `DATA.db` plus `-wal`/`-shm`; bot/admin/message state |
| `secret/` | `config.secure`; verifies the master password for manual fallback |
| `logs/` | Optional, useful for diagnosing the migration |
| `diff/` | Safety-check differences, optional |
| `docker/cloudflared/` | `config.yml` and `credentials.json` for the existing tunnel |

Copy it to the new VPS:

```bash
scp "$HOME"/hidego-backup-*.tar.gz user@NEW_VPS:/tmp/
```

> **Encryption key:** the database is encrypted with the master password.
> The new VPS must use the same Infisical secret (same `INFISICAL_*` values) or
> the same manual password that matches `secret/config.secure`. Without it,
> existing bot tokens, admins, and messages cannot be decrypted.

Do **not** copy `DATA.db` without stopping the container or without the
`-wal` file; recent transactions can be lost.

## 2. Prepare the new VPS

```bash
sudo apt update
sudo apt install -y git curl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

Log out and back in (or run `newgrp docker`), then verify:

```bash
docker compose version
```

For a **very low-end VPS**, add swap before building (the dependency install can
exceed 512 MB RAM):

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

## 3. Clone and restore

```bash
git clone https://github.com/411A/Telegram-Anonymous-Messaging-Bot-Creator.git
cd Telegram-Anonymous-Messaging-Bot-Creator

# Copy the archive from the old VPS first, then:
tar -xzf "$(ls -t "$HOME"/hidego-backup-*.tar.gz | head -1)"
```

Fix ownership and permissions (the container runs as your host UID/GID):

```bash
sudo chown -R "$USER":"$USER" data logs secret diff .env docker/cloudflared
chmod 700 secret docker/cloudflared
chmod 600 .env docker/cloudflared/credentials.json 2>/dev/null || true
[ -f secret/config.secure ] && chmod 600 secret/config.secure
```

## 4. Update `.env` for the new host

Keep the existing Telegram and Infisical values. Check these lines:

```bash
grep -E 'FASTAPI_PORT|FASTAPI_BIND_ADDR|TRUSTED_PROXY_CIDRS|LEAN_MODE|DOCKER_NETWORK_IP|WEBHOOK_BASE_URL' .env
```

Expected:

```bash
WEBHOOK_BASE_URL=https://webhook.hiddenego.ir   # unchanged domain
FASTAPI_PORT=14143                              # must match cloudflared config
FASTAPI_BIND_ADDR=127.0.0.1
TRUSTED_PROXY_CIDRS=172.30.0.1/32,172.30.0.2/32
LEAN_MODE=1
```

Remove or replace any active legacy line:

```bash
DOCKER_NETWORK_IP=172.30.0.1/24
```

If the new VPS has **512 MB RAM**, lower the caps in `.env`:

```bash
LEAN_MODE=1
BOT_MEM_LIMIT=320m
BOT_MEM_RESERVATION=96m
BOT_CPUS=0.75
TUNNEL_MEM_LIMIT=96m
TUNNEL_MEM_RESERVATION=24m
TUNNEL_CPUS=0.25
```

On a 1 GB VPS the lean defaults (`512m` bot, `128m` tunnel) are usually fine.

If you change the public hostname, update all four places together:
`WEBHOOK_BASE_URL` in `.env`, the tunnel `ingress.hostname`, the Cloudflare DNS
route, and the WAF rule expression.

## 5. Keep the same Cloudflare Tunnel

The archive already contains `docker/cloudflared/config.yml` and
`credentials.json`. Verify the ingress points at the Compose service name and
your current port:

```yaml
ingress:
  - hostname: webhook.hiddenego.ir
    path: ^/webhook/
    service: http://hidego-tgbot:14143
  - service: http_status:404
```

If you are creating a **new** tunnel instead of moving the old one:

```bash
cloudflared tunnel create hidego-tgbot
cloudflared tunnel route dns hidego-tgbot webhook.hiddenego.ir
# then copy the new credentials.json and set its tunnel UUID in config.yml
```

Do not start the new connector until the old VPS connector is stopped.
The account-level WAF rule (`not cf.edge.server_port in {443}`) stays in place;
recreate it only if you change the hostname.

## 6. Start in lean mode

```bash
cd docker
chmod +x run.sh
./run.sh start --lean
```

Because `LEAN_MODE=1` is in `.env`, every later `./run.sh recover` — including
the systemd watchdog — keeps the lean override.

If Infisical is configured, startup is unattended. In manual password mode,
enter the password, then detach with `Ctrl+P`, `Ctrl+Q`.

## 7. Install the watchdog

```bash
./run.sh install-watchdog
```

This is safe only after Infisical is configured. In manual password mode a
recreated container cannot prompt for the password, so unattended recovery is
not possible.

## 8. Verify

```bash
./run.sh status
./run.sh security-check
docker stats --no-stream

# Tunnel connected?
./run.sh tunnel status
docker logs --tail 30 hidego-cloudflared | grep -i "registered tunnel connection"

# OOM check (must be false)
docker inspect -f '{{.State.OOMKilled}}' hidego-tgbot
```

Public checks:

```bash
# /health is tunnel-blocked now -> 404
curl -sS -o /dev/null -w '%{http_code}\n' https://webhook.hiddenego.ir/health

# Webhook path is public but unsigned -> 403
curl -sS -o /dev/null -w '%{http_code}\n' https://webhook.hiddenego.ir/webhook/test

# Non-443 edge port should be blocked by the WAF rule
curl -sS -o /dev/null -w '%{http_code}\n' https://webhook.hiddenego.ir:8443/webhook/test
```

Finally, test inside Telegram: send `/start` to the main bot, create/reuse a
test bot, send a message, and confirm `docker logs -f hidego-tgbot` shows the
webhook update.

## 9. Finish the old VPS

Once the new host works, keep the old VPS stopped (its watchdog is disabled), or
destroy it after confirming the backup is valid. Never leave both connectors
running against the same tunnel.

## If something is wrong

| Symptom | Check |
|---------|-------|
| `telegram.error.TimedOut` on reply (`ConnectTimeout` to `api.telegram.org`) but webhooks return `200` | Ingress is fine; outbound egress is slow/filtered. From VPS: `time curl -4 -o /dev/null -w "connect=%{time_connect} total=%{time_total}\n" https://api.telegram.org`. If default `curl` fails with `Connection reset` but `-4` works, IPv6 is being reset — the bot container now uses explicit `1.1.1.1/8.8.8.8` DNS (`docker/docker-compose.yml`) to avoid the 2s+ stub-resolver delay. If both are slow/reset, set `TELEGRAM_PROXY=` (or `HTTPS_PROXY=`) in `.env` and restart. Lean mode already caps the Bot API pool to 32 (`TELEGRAM_POOL_SIZE`). |
| `error code: 1033` | `cloudflared` not connected, or two connectors where one is dead. `./run.sh tunnel status`, `docker logs hidego-cloudflared` |
| `502` from Cloudflare | Tunnel is up but `service:` port/host is wrong, or bot container is down |
| `403` on every webhook | `TG_SECRET_TOKEN` mismatch, or `TRUSTED_PROXY_CIDRS` missing `172.30.0.2/32` |
| Bots/admins disappeared | Wrong master password or wrong Infisical project/environment; encrypted rows cannot be decrypted |
| Container restarts / OOM | `docker inspect -f '{{.State.OOMKilled}}' hidego-tgbot`; lower `BOT_MEM_LIMIT`, add swap |
| Disk full during build | Add swap, build elsewhere, or run `./run.sh prune --full` after startup |
