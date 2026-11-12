#!/bin/bash

# Docker runner and recovery watchdog for HiddenEgo Bot.

set -Eeuo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DISABLE_FILE="$PROJECT_ROOT/data/.hidego-watchdog-disabled"
COMPOSE_PROJECT_NAME="hidego-tgbot"
SYSTEMD_SERVICE="hidego-tgbot-watchdog.service"
SYSTEMD_TIMER="hidego-tgbot-watchdog.timer"

cd "$SCRIPT_DIR"

export USER_UID="${USER_UID:-$(id -u)}"
export USER_GID="${USER_GID:-$(id -g)}"

read_env_value() {
    local key="$1"
    local env_file="$PROJECT_ROOT/.env"
    local env_value

    if env_value="$(printenv "$key" 2>/dev/null)" && [ -n "$env_value" ]; then
        printf '%s\n' "$env_value"
        return 0
    fi

    [ -f "$env_file" ] || return 0

    local line
    line="$(grep -E "^[[:space:]]*${key}=" "$env_file" 2>/dev/null | tail -n 1 || true)"
    [ -n "$line" ] || return 0

    line="${line#*=}"
    printf '%s\n' "$line" | sed \
        -e 's/^[[:space:]]*//' \
        -e 's/[[:space:]]*$//' \
        -e 's/^"//' \
        -e 's/"$//' \
        -e "s/^'//" \
        -e "s/'$//"
}

value_is_real() {
    local value="${1:-}"
    local lowered="${value,,}"

    [ -n "$value" ] || return 1
    [[ "$lowered" != your_* ]] || return 1
    [[ "$lowered" != *placeholder* ]] || return 1
    [[ "$lowered" != "changeme" ]] || return 1
    [[ "$lowered" != "change_me" ]] || return 1
    return 0
}

fastapi_port() {
    local port
    port="$(read_env_value FASTAPI_PORT)"
    printf '%s\n' "${port:-13360}"
}

infisical_configured() {
    local client_id client_secret project_id
    client_id="$(read_env_value INFISICAL_CLIENT_ID)"
    client_secret="$(read_env_value INFISICAL_CLIENT_SECRET)"
    project_id="$(read_env_value INFISICAL_PROJECT_ID)"

    value_is_real "$client_id" && value_is_real "$client_secret" && value_is_real "$project_id"
}

tunnel_config_present() {
    [ -f "$SCRIPT_DIR/cloudflared/config.yml" ]
}

tunnel_configured() {
    [ -f "$SCRIPT_DIR/cloudflared/config.yml" ] && [ -f "$SCRIPT_DIR/cloudflared/credentials.json" ]
}

warn_tunnel_partial() {
    if tunnel_config_present && ! tunnel_configured; then
        log_warning "Cloudflare Tunnel config.yml exists but credentials.json is missing; starting bot only."
    fi
}

docker_compose() {
    build_compose_file_args
    docker compose --project-name "$COMPOSE_PROJECT_NAME" --env-file "$PROJECT_ROOT/.env" "${compose_file_args[@]}" "$@"
}

docker_compose_manual() {
    build_compose_file_args
    docker compose --project-name "$COMPOSE_PROJECT_NAME" --env-file "$PROJECT_ROOT/.env" "${compose_file_args[@]}" -f "$SCRIPT_DIR/docker-compose.manual.yml" "$@"
}

# Compose file stack: base always, lean override only when opted in via
# --lean / -l flag or LEAN_MODE=1 (low-end VPS mode, dynamic per run).
build_compose_file_args() {
    compose_file_args=(-f "$SCRIPT_DIR/docker-compose.yml")
    if [ "${LEAN_FLAG:-false}" = true ]; then
        compose_file_args+=(-f "$SCRIPT_DIR/docker-compose.lean.yml")
    fi
}

ensure_directories() {
    mkdir -p "$PROJECT_ROOT/data" "$PROJECT_ROOT/logs" "$PROJECT_ROOT/secret" "$PROJECT_ROOT/diff"

    for dir in "$PROJECT_ROOT/data" "$PROJECT_ROOT/logs" "$PROJECT_ROOT/secret" "$PROJECT_ROOT/diff"; do
        if [ ! -w "$dir" ]; then
            log_warning "Trying to make $dir writable for the current user."
            chmod u+w "$dir" 2>/dev/null || log_warning "Could not fix $dir permissions automatically."
        fi
    done
}

ensure_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        log_error "docker is not installed or not in PATH."
        return 1
    fi

    if ! docker info >/dev/null 2>&1; then
        log_error "Docker daemon is not reachable."
        return 1
    fi

    if ! docker compose version >/dev/null 2>&1; then
        log_error "Docker Compose v2 plugin is not available."
        return 1
    fi
}

up_stack() {
    local build_mode="${1:-normal}"
    local args=(up -d --remove-orphans)

    if [ "$build_mode" = "build" ]; then
        args+=(--build)
    fi

    warn_tunnel_partial
    remove_legacy_named_containers
    if tunnel_configured; then
        log_info "Ensuring bot and Cloudflare Tunnel are up."
        docker_compose "${args[@]}"
    else
        log_info "Ensuring bot is up."
        docker_compose "${args[@]}" hidego-tgbot
    fi

    # Automatic lightweight cleanup: keep this project's footprint to one
    # latest image per service. Scoped to our Compose labels only, so sibling
    # projects are never touched. Failures must not break startup.
    auto_prune_project || true
}

container_state() {
    docker inspect -f '{{.State.Status}}' "$1" 2>/dev/null || true
}

container_health() {
    docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$1" 2>/dev/null || true
}

remove_exact_container() {
    local container_name="$1"
    local id project_label

    id="$(docker inspect -f '{{.Id}}' "$container_name" 2>/dev/null || true)"
    [ -n "$id" ] || return 0

    project_label="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$id" 2>/dev/null || true)"
    if [ "$project_label" != "$COMPOSE_PROJECT_NAME" ]; then
        log_warning "Removing legacy $container_name container from Compose project '${project_label:-none}'."
        docker rm -f "$id" >/dev/null || true
    fi
}

remove_legacy_named_containers() {
    # Migration cleanup only for this app's explicit container names.
    remove_exact_container hidego-tgbot
    remove_exact_container hidego-cloudflared
}

remediate_service() {
    local service="$1"
    local container="$2"
    local state health

    state="$(container_state "$container")"
    if [ -z "$state" ]; then
        log_warning "$container is missing; recreating $service."
        docker_compose up -d --build --force-recreate "$service"
        return 0
    fi

    case "$state" in
        running)
            health="$(container_health "$container")"
            if [ "$health" = "unhealthy" ]; then
                log_warning "$container is unhealthy; restarting it."
                docker restart "$container" >/dev/null || docker_compose up -d --build --force-recreate "$service"
            elif [ "$health" = "starting" ]; then
                log_info "$container is still starting."
            else
                log_success "$container is running (health: $health)."
            fi
            ;;
        restarting)
            log_warning "$container is already restarting."
            ;;
        created|exited|dead)
            log_warning "$container state is $state; recreating $service."
            docker_compose up -d --build --force-recreate "$service"
            ;;
        *)
            log_warning "$container state is $state; asking Compose to reconcile it."
            docker_compose up -d --build "$service"
            ;;
    esac
}

host_health_check() {
    command -v curl >/dev/null 2>&1 || return 0

    local health port
    health="$(container_health hidego-tgbot)"
    [ "$health" = "healthy" ] || return 0

    port="$(fastapi_port)"
    if curl -fsS --max-time 8 "http://127.0.0.1:${port}/health" >/dev/null; then
        log_success "Host health check passed on port $port."
    else
        log_warning "Docker reports healthy, but host health check failed on port $port; recreating bot."
        docker_compose up -d --build --force-recreate hidego-tgbot
    fi
}

start_stack() {
    ensure_docker
    ensure_directories
    rm -f "$DISABLE_FILE"

    local port
    port="$(fastapi_port)"
    log_info "Starting HiddenEgo Bot with UID:GID $USER_UID:$USER_GID"
    if [ "${LEAN_FLAG:-false}" = true ]; then
        log_info "Lean mode enabled for this run (RAM/CPU caps + lean uvicorn)."
    fi
    log_info "Bot will run on port $port."

    if infisical_configured; then
        log_info "Infisical detected; password retrieval is non-interactive."
        if [ "$BUILD_FLAG" = "true" ]; then
            log_info "Rebuilding image without cache."
            docker_compose build --no-cache
        fi
        up_stack normal
        log_success "Bot started. Following logs; press Ctrl+C to stop watching."
        docker logs -f hidego-tgbot
    else
        log_warning "Infisical is not fully configured. Docker manual password mode is not unattended-recoverable."
        log_info "After entering the password, use Ctrl+P then Ctrl+Q to detach."

        if [ "$BUILD_FLAG" = "true" ]; then
            log_info "Rebuilding image without cache."
            docker_compose_manual build --no-cache
        fi

        warn_tunnel_partial
        if tunnel_configured; then
            docker_compose_manual up -d --remove-orphans
        else
            docker_compose_manual up -d --remove-orphans hidego-tgbot
        fi
        log_info "Attaching to bot container for password input."
        docker attach hidego-tgbot
    fi
}

recover_stack() {
    ensure_docker
    ensure_directories

    if [ -f "$DISABLE_FILE" ]; then
        log_info "Watchdog disabled by $DISABLE_FILE; leaving stack stopped."
        return 0
    fi

    if ! infisical_configured; then
        log_error "Automated recovery requires Infisical. Manual password mode cannot recover unattended."
        return 2
    fi

    if ! up_stack normal; then
        log_warning "Normal Compose reconciliation failed; retrying with image build."
        up_stack build
    fi
    remediate_service hidego-tgbot hidego-tgbot

    if tunnel_configured; then
        remediate_service cloudflared hidego-cloudflared
    fi

    host_health_check
}

stop_stack() {
    ensure_docker
    ensure_directories
    touch "$DISABLE_FILE"

    log_info "Stopping HiddenEgo Bot and Cloudflare Tunnel. Watchdog disabled until the next start."
    docker_compose down --remove-orphans
    remove_legacy_named_containers
}

# --- Project-scoped intelligent cleanup -------------------------------------
# Finds images, containers, volumes, networks and build cache that belong to
# THIS compose project (label com.docker.compose.project=hidego-tgbot or the
# exact image names from `docker compose config --images`) and removes
# outdated ones, keeping exactly ONE LATEST per image repository.
# Nothing outside this scope is ever touched, so sibling Docker projects
# sharing the host / base layers / pip cache are safe.
#   prune_project [safe|full]
#     safe: exited containers, superseded images, dangling scoped images,
#           unused scoped volumes/networks. Runs automatically after up/recover.
#     full: safe + evicts unused builder cache (shared, least-recently-used
#           only, bounded by --keep-storage) for a FULL cleanup.

project_expected_images() {
    docker_compose config --images 2>/dev/null || true
}

project_images_in_use() {
    {
        docker_compose ps -q 2>/dev/null | xargs -r docker inspect --format '{{.Image}}' 2>/dev/null || true
        docker ps --format '{{.Image}}' 2>/dev/null || true
    } | sort -u
}

prune_project() {
    local mode="${1:-safe}"
    ensure_docker

    log_info "Pruning HiddenEgo Docker resources (mode: $mode, scope: project '$COMPOSE_PROJECT_NAME' only)."

    # 1. Stopped containers of this project (keep running ones untouched).
    local stopped
    stopped="$(docker ps -a --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" --filter status=exited --filter status=created --filter status=dead --format '{{.ID}}' 2>/dev/null || true)"
    if [ -n "$stopped" ]; then
        # shellcheck disable=SC2086
        docker rm $stopped >/dev/null 2>&1 || true
        log_info "Removed stopped project containers."
    fi

    # 2. Superseded images: keep ONE LATEST per repository.
    local in_use repos repo
    in_use="$(project_images_in_use)"
    repos="$(project_expected_images | sort -u)"
    # Fallback: also cover locally-built images carrying our project label.
    if [ -z "$repos" ]; then
        repos="$(docker images --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" --format '{{.Repository}}' 2>/dev/null | sort -u || true)"
    fi
    for repo in $repos; do
        [ -n "$repo" ] && [ "$repo" != "<none>" ] || continue
        local ids keep rest id
        ids="$(docker images --format '{{.Repository}} {{.ID}} {{.CreatedAt}}' 2>/dev/null | awk -v r="$repo" '$1==r {print $2" "$3" "$4" "$5}' | sort -k2,3 -r | awk '{print $1}' | uniq || true)"
        [ -n "$ids" ] || continue
        keep="$(printf '%s\n' "$ids" | head -n 1 || true)"
        rest="$(printf '%s\n' "$ids" | tail -n +2 || true)"
        for id in $rest; do
            if printf '%s\n' "$in_use" | grep -qx "$id"; then
                continue
            fi
            # Never delete an image a running sibling container uses (by tag too).
            if docker ps --format '{{.Image}}' 2>/dev/null | grep -qx "$id"; then
                continue
            fi
            docker rmi "$id" >/dev/null 2>&1 || true
        done
        if [ -n "$rest" ]; then
            log_info "Kept latest $repo ($keep), removed superseded copies."
        fi
    done

    # 3. Dangling images scoped to this project.
    local dangling
    dangling="$(docker images --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" --filter "dangling=true" --format '{{.ID}}' 2>/dev/null || true)"
    if [ -n "$dangling" ]; then
        # shellcheck disable=SC2086
        docker rmi $dangling >/dev/null 2>&1 || true
        log_info "Removed dangling project images."
    fi

    # 4. Unused volumes scoped to this project (bind mounts are unaffected).
    local vol attached
    for vol in $(docker volume ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" --format '{{.Name}}' 2>/dev/null || true); do
        attached="$(docker ps -q --filter "volume=$vol" 2>/dev/null || true)"
        if [ -z "$attached" ]; then
            docker volume rm "$vol" >/dev/null 2>&1 || true
            log_info "Removed unused volume $vol."
        fi
    done

    # 5. Unused networks scoped to this project (never the active one).
    local net count
    for net in $(docker network ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" --format '{{.ID}}' 2>/dev/null || true); do
        count="$(docker network inspect -f '{{len .Containers}}' "$net" 2>/dev/null || echo 1)"
        if [ "$count" = "0" ] || [ "$count" = "<no value>" ]; then
            docker network rm "$net" >/dev/null 2>&1 || true
            log_info "Removed unused network $net."
        fi
    done

    # 6. Full mode only: evict least-recently-used build cache (shared cache
    #    is daemon-global; --keep-storage bounds it without harming the
    #    fresh layers sibling projects need).
    if [ "$mode" = "full" ]; then
        docker builder prune -f --keep-storage 1GB >/dev/null 2>&1 || true
        log_info "Evicted stale builder cache (kept 1GB of most-recent)."
    fi

    log_success "Prune complete: one latest image per service, scope '$COMPOSE_PROJECT_NAME' only."
}

# Silent light prune after successful up/recover: never fail the caller.
auto_prune_project() {
    prune_project safe >/dev/null 2>&1 || true
}

cleanup_stack() {
    ensure_docker
    ensure_directories
    touch "$DISABLE_FILE"

    log_warning "Cleaning containers. Watchdog disabled until the next start."
    docker_compose down --remove-orphans
    remove_legacy_named_containers
    # Follow with scoped prune so old images/volumes/networks of this project
    # do not linger next to sibling projects.
    prune_project safe || true

    log_success "Cleanup complete. Run ./run.sh start to enable and recreate the stack."
}

show_status() {
    ensure_docker
    docker_compose ps || true
    echo

    for container in hidego-tgbot hidego-cloudflared; do
        local state health
        state="$(container_state "$container")"
        if [ -z "$state" ]; then
            echo "$container: missing"
            continue
        fi
        health="$(container_health "$container")"
        echo "$container: state=$state health=$health"
    done

    if [ -f "$DISABLE_FILE" ]; then
        echo "watchdog: disabled ($DISABLE_FILE exists)"
    else
        echo "watchdog: enabled"
    fi
}

security_check() {
    ensure_docker

    if [ -z "$(container_state hidego-tgbot)" ]; then
        log_warning "hidego-tgbot is not created yet; start it with ./run.sh start."
        return 0
    fi

    local port mapping proxies failed=0
    port="$(fastapi_port)"
    mapping="$(docker port hidego-tgbot "${port}/tcp" 2>/dev/null || true)"

    if [ -z "$mapping" ]; then
        log_success "Bot port ${port} is not published on the host (tunnel-only)."
    elif printf '%s\n' "$mapping" | grep -Evq '^(127\.0\.0\.1|\[::1\]):'; then
        log_error "Bot port ${port} is reachable from a non-loopback address:"
        printf '  %s\n' "$mapping"
        log_info "Set FASTAPI_BIND_ADDR=127.0.0.1 in .env and recreate the container."
        failed=1
    else
        log_success "Bot port ${port} is loopback-only:"
        printf '  %s\n' "$mapping"
    fi

    if [ -n "$(docker port hidego-cloudflared 2>/dev/null || true)" ]; then
        log_warning "cloudflared publishes host ports; it only needs outbound 7844/tcp+udp:"
        docker port hidego-cloudflared || true
        failed=1
    else
        log_success "cloudflared publishes no host ports (outbound-only tunnel)."
    fi

    proxies="$(read_env_value TRUSTED_PROXY_CIDRS)"
    [ -n "$proxies" ] || proxies="$(read_env_value DOCKER_NETWORK_IP)"
    if [ -n "$proxies" ]; then
        log_info "Trusted proxy IPs/CIDRs: ${proxies}"
        case "$proxies" in
            *"/8"*|*"/16"*|*"/24"*)
                log_warning "Trusted proxy range is wider than necessary; prefer /32 entries."
                ;;
        esac
    fi

    if [ "$failed" -ne 0 ]; then
        return 1
    fi
    log_success "No public bot port detected."
}

run_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

write_root_file() {
    local path="$1"
    if [ "$(id -u)" -eq 0 ]; then
        tee "$path"
    else
        sudo tee "$path"
    fi
}

install_watchdog() {
    if ! command -v systemctl >/dev/null 2>&1; then
        log_error "systemctl was not found. Install the watchdog on a Linux host with systemd."
        exit 1
    fi

    local target_user target_group target_uid target_gid service_path timer_path
    target_user="${1:-${SUDO_USER:-$(id -un)}}"
    target_group="$(id -gn "$target_user")"
    target_uid="$(id -u "$target_user")"
    target_gid="$(id -g "$target_user")"
    service_path="/etc/systemd/system/$SYSTEMD_SERVICE"
    timer_path="/etc/systemd/system/$SYSTEMD_TIMER"

    log_info "Installing watchdog as user $target_user."

    cat <<EOF | write_root_file "$service_path" >/dev/null
[Unit]
Description=HiddenEgo Telegram bot Docker recovery watchdog
Wants=docker.service network-online.target
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
User=$target_user
Group=$target_group
WorkingDirectory=$SCRIPT_DIR
Environment=USER_UID=$target_uid
Environment=USER_GID=$target_gid
ExecStart=$SCRIPT_DIR/run.sh recover
TimeoutStartSec=15min
EOF

    cat <<EOF | write_root_file "$timer_path" >/dev/null
[Unit]
Description=Run HiddenEgo Telegram bot Docker recovery watchdog

[Timer]
OnBootSec=90s
OnUnitActiveSec=2min
AccuracySec=30s
RandomizedDelaySec=15s
Persistent=true
Unit=$SYSTEMD_SERVICE

[Install]
WantedBy=timers.target
EOF

    run_root systemctl daemon-reload
    run_root systemctl enable --now "$SYSTEMD_TIMER"
    log_success "Watchdog installed and started."
    log_info "Check it with: systemctl status $SYSTEMD_TIMER"
}

uninstall_watchdog() {
    if ! command -v systemctl >/dev/null 2>&1; then
        log_error "systemctl was not found."
        exit 1
    fi

    run_root systemctl disable --now "$SYSTEMD_TIMER" 2>/dev/null || true
    run_root rm -f "/etc/systemd/system/$SYSTEMD_SERVICE" "/etc/systemd/system/$SYSTEMD_TIMER"
    run_root systemctl daemon-reload
    log_success "Watchdog uninstalled."
}

watchdog_status() {
    if command -v systemctl >/dev/null 2>&1; then
        systemctl --no-pager status "$SYSTEMD_TIMER" || true
        systemctl --no-pager status "$SYSTEMD_SERVICE" || true
    else
        log_error "systemctl was not found."
    fi
}

manage_tunnel() {
    ensure_docker

    if [ "${2:-status}" != "status" ] && ! tunnel_configured; then
        log_error "Cloudflare Tunnel is not fully configured."
        log_info "Expected docker/cloudflared/config.yml and docker/cloudflared/credentials.json"
        exit 1
    fi

    case "${2:-status}" in
        start)
            log_info "Starting Cloudflare Tunnel."
            docker_compose up -d cloudflared
            ;;
        stop)
            log_warning "Stopping Cloudflare Tunnel. The watchdog will restart it while tunnel config exists."
            docker_compose stop cloudflared
            ;;
        restart)
            log_info "Restarting Cloudflare Tunnel."
            docker_compose restart cloudflared
            ;;
        logs)
            docker logs -f hidego-cloudflared
            ;;
        status)
            show_status
            docker logs --tail 20 hidego-cloudflared 2>/dev/null || true
            ;;
        *)
            log_error "Unknown tunnel command: ${2:-}"
            echo "Usage: ./run.sh tunnel [start|stop|restart|logs|status]"
            ;;
    esac
}

usage() {
    cat <<'EOF'
Usage: ./run.sh [-b] [command]

Commands:
  start                  Start the bot and enable watchdog recovery
  recover                Reconcile/recreate the stack; intended for systemd watchdog
  stop                   Stop the stack and disable watchdog recovery
  restart                Restart via stop + start
  status                 Show compose/container/watchdog state
  security-check         Verify the bot port is not publicly exposed
  logs                   Follow bot logs
  shell                  Open a shell in the bot container
  tunnel [cmd]           Manage tunnel: start|stop|restart|logs|status
  install-watchdog [user] Install a systemd timer that runs recover every 2 minutes
  uninstall-watchdog     Remove the systemd timer/service
  watchdog-status        Show systemd watchdog status
  cleanup                Remove bot/tunnel containers + scoped prune, disable watchdog
  prune [--full]         Scoped cleanup: keep ONE LATEST image per service, drop
                         stopped containers, dangling images, unused volumes and
                         networks of THIS project only (--full also evicts stale
                         builder cache; sibling projects are never touched)

Options:
  -b, --build            Rebuild image without cache before start
  -l, --lean             Low-end VPS mode for this run: apply
                         docker-compose.lean.yml caps (RAM/CPU, tmpfs, lean
                         uvicorn). Also via LEAN_MODE=1 env. Nothing is
                         hardcoded; default runs stay full-performance.
EOF
}

BUILD_FLAG=false
LEAN_FLAG=false
# Opt-in lean (low-end VPS) mode, dynamic per run - no branches, no file edits:
#   ./run.sh start --lean   |   ./run.sh --lean start   |   LEAN_MODE=1 ./run.sh start
# LEAN_MODE=1 in .env is persistent, so the systemd watchdog (run.sh recover)
# keeps applying the lean override after reboots and container recreation.
if [ "${LEAN_MODE:-0}" = "1" ] || [ "$(read_env_value LEAN_MODE)" = "1" ]; then
    LEAN_FLAG=true
fi

# Normalize optional flags from any position into COMMAND + spare args,
# so downstream "$@" / "${2:-}" handling stays consistent.
NORMALIZED_ARGS=()
for _tok in "$@"; do
    case "$_tok" in
        -b|--build) BUILD_FLAG=true ;;
        -l|--lean) LEAN_FLAG=true ;;
        *) NORMALIZED_ARGS+=("$_tok") ;;
    esac
done
COMMAND="${NORMALIZED_ARGS[0]:-start}"
set -- "${NORMALIZED_ARGS[@]:-start}"

case "$COMMAND" in
    start|"")
        start_stack
        ;;
    recover)
        recover_stack
        ;;
    stop)
        stop_stack
        ;;
    restart)
        stop_stack
        start_stack
        ;;
    status|doctor)
        show_status
        ;;
    security-check|audit)
        security_check
        ;;
    logs)
        ensure_docker
        docker logs -f hidego-tgbot
        ;;
    shell)
        ensure_docker
        docker exec -it hidego-tgbot /bin/bash
        ;;
    tunnel)
        manage_tunnel "$@"
        ;;
    install-watchdog)
        install_watchdog "${2:-}"
        ;;
    uninstall-watchdog)
        uninstall_watchdog
        ;;
    watchdog-status)
        watchdog_status
        ;;
    cleanup)
        cleanup_stack
        ;;
    prune)
        if [ "${2:-}" = "--full" ] || [ "${2:-}" = "full" ]; then
            prune_project full
        else
            prune_project safe
        fi
        ;;
    help|-h|--help)
        usage
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
