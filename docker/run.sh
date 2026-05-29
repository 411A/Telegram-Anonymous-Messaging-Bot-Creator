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
    docker compose --project-name "$COMPOSE_PROJECT_NAME" --env-file "$PROJECT_ROOT/.env" -f "$SCRIPT_DIR/docker-compose.yml" "$@"
}

docker_compose_manual() {
    docker compose --project-name "$COMPOSE_PROJECT_NAME" --env-file "$PROJECT_ROOT/.env" -f "$SCRIPT_DIR/docker-compose.yml" -f "$SCRIPT_DIR/docker-compose.manual.yml" "$@"
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

cleanup_stack() {
    ensure_docker
    ensure_directories
    touch "$DISABLE_FILE"

    log_warning "Cleaning containers. Watchdog disabled until the next start."
    docker_compose down --remove-orphans
    remove_legacy_named_containers

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
  logs                   Follow bot logs
  shell                  Open a shell in the bot container
  tunnel [cmd]           Manage tunnel: start|stop|restart|logs|status
  install-watchdog [user] Install a systemd timer that runs recover every 2 minutes
  uninstall-watchdog     Remove the systemd timer/service
  watchdog-status        Show systemd watchdog status
  cleanup                Remove bot/tunnel containers and disable watchdog

Options:
  -b, --build            Rebuild image without cache before start
EOF
}

BUILD_FLAG=false
COMMAND="${1:-start}"

if [[ "$COMMAND" == "-b" || "$COMMAND" == "--build" ]]; then
    BUILD_FLAG=true
    COMMAND="${2:-start}"
elif [[ "${2:-}" == "-b" || "${2:-}" == "--build" ]]; then
    BUILD_FLAG=true
fi

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
    help|-h|--help)
        usage
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
