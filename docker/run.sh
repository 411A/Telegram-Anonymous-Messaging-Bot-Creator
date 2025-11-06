#!/bin/bash

# Simple Docker runner for HiddenEgo Bot

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Get current user UID/GID for ownership
export USER_UID=$(id -u)
export USER_GID=$(id -g)

# Parse build flag (can be first or second argument)
BUILD_FLAG=false
COMMAND="start"

if [[ "$1" == "-b" ]]; then
    BUILD_FLAG=true
    COMMAND="${2:-start}"
elif [[ "$2" == "-b" ]]; then
    BUILD_FLAG=true
    COMMAND="$1"
else
    COMMAND="${1:-start}"
fi

case "$COMMAND" in
    "start"|"")
        log_info "Starting HiddenEgo Bot with UID:GID $USER_UID:$USER_GID"
        
        # Ensure directories exist with correct permissions
        mkdir -p ../data ../logs ../secret ../diff
        
        # Fix permissions if they exist but are wrong (common Docker issue)
        if [ ! -w ../diff ]; then
            log_warning "Fixing permissions for diff directory..."
            chmod u+w ../diff 2>/dev/null || log_warning "Could not fix diff permissions - you may need to run: sudo chown -R \$USER:\$USER ../diff && chmod u+w ../diff"
        fi
        
        # Check if cloudflared config exists
        if [ -f "cloudflared/config.yml" ]; then
            log_info "Cloudflare Tunnel configuration detected - will start both bot and tunnel"
            TUNNEL_MODE=true
        else
            log_info "No Cloudflare Tunnel config found - starting bot only"
            log_info "To enable tunnel, see: docker/cloudflared/README.md"
            TUNNEL_MODE=false
        fi
        
        log_info "After entering password, use Ctrl+P then Ctrl+Q to detach"
        log_info "Or close terminal after bot starts - container will keep running"
        
        # Get port from .env file
        FASTAPI_PORT=$(grep "^FASTAPI_PORT=" ../.env 2>/dev/null | cut -d'=' -f2 | tr -d ' "'"'"'')
        FASTAPI_PORT=${FASTAPI_PORT:-13360}
        
        log_info "Bot will run on port $FASTAPI_PORT"
        
        # Build if requested
        if [[ "$BUILD_FLAG" == "true" ]]; then
            log_info "Building image first..."
            docker compose build
        fi
        
        # Start services based on tunnel configuration
        if [[ "$TUNNEL_MODE" == "true" ]]; then
            log_info "Starting bot with Cloudflare Tunnel..."
            docker compose up -d cloudflared
            docker compose run --rm -p "${FASTAPI_PORT}:${FASTAPI_PORT}" hidego-tgbot
        else
            # Run with explicit port mapping for external access
            docker compose run --rm -p "${FASTAPI_PORT}:${FASTAPI_PORT}" hidego-tgbot
        fi
        ;;
    "stop")
        log_info "Stopping HiddenEgo Bot and Cloudflare Tunnel..."
        docker compose down
        # Also stop any containers created by 'run' command
        docker stop $(docker ps -q --filter "name=hidego-tgbot") 2>/dev/null || true
        docker stop $(docker ps -q --filter "name=hidego-cloudflared") 2>/dev/null || true
        ;;
    "logs")
        # Find the running container and show its logs
        CONTAINER_ID=$(docker ps -q --filter "name=hidego-tgbot")
        if [ -n "$CONTAINER_ID" ]; then
            docker logs -f "$CONTAINER_ID"
        else
            log_error "No running hidego-tgbot container found"
            docker ps --filter "name=hidego-tgbot"
        fi
        ;;
    "shell")
        # Connect to the running container
        CONTAINER_ID=$(docker ps -q --filter "name=hidego-tgbot")
        if [ -n "$CONTAINER_ID" ]; then
            docker exec -it "$CONTAINER_ID" /bin/bash
        else
            log_error "No running hidego-tgbot container found"
            docker ps --filter "name=hidego-tgbot"
        fi
        ;;
    "tunnel")
        log_info "Managing Cloudflare Tunnel..."
        if [ ! -f "cloudflared/config.yml" ]; then
            log_error "Cloudflare Tunnel not configured!"
            log_info "Please see: docker/cloudflared/README.md for setup instructions"
            exit 1
        fi
        
        case "${2:-status}" in
            "start")
                log_info "Starting Cloudflare Tunnel..."
                docker compose up -d cloudflared
                log_success "Tunnel started! Check logs with: ./run.sh tunnel logs"
                ;;
            "stop")
                log_info "Stopping Cloudflare Tunnel..."
                docker compose stop cloudflared
                ;;
            "restart")
                log_info "Restarting Cloudflare Tunnel..."
                docker compose restart cloudflared
                ;;
            "logs")
                docker logs -f hidego-cloudflared
                ;;
            "status")
                if docker ps | grep -q hidego-cloudflared; then
                    log_success "Cloudflare Tunnel is running"
                    docker logs --tail 10 hidego-cloudflared
                else
                    log_warning "Cloudflare Tunnel is not running"
                fi
                ;;
            *)
                log_error "Unknown tunnel command: ${2}"
                echo "Usage: ./run.sh tunnel [start|stop|restart|logs|status]"
                ;;
        esac
        ;;
    "cleanup")
        log_info "Cleaning up all containers and rebuilding..."
        docker compose down
        docker stop $(docker ps -q --filter "name=hidego-tgbot") 2>/dev/null || true
        docker rm $(docker ps -aq --filter "name=hidego-tgbot") 2>/dev/null || true
        docker stop $(docker ps -q --filter "name=hidego-cloudflared") 2>/dev/null || true
        docker rm $(docker ps -aq --filter "name=hidego-cloudflared") 2>/dev/null || true
        log_success "Cleanup complete. Ready for fresh start."
        ;;
    *)
        echo "Usage: $0 [-b] [start|stop|logs|shell|tunnel|cleanup]"
        echo ""
        echo "  -b                    - Build image before starting"
        echo "  start (default)       - Start the bot (and tunnel if configured)"
        echo "  stop                  - Stop the bot and tunnel"
        echo "  logs                  - Show bot logs"
        echo "  shell                 - Open shell in bot container"
        echo "  tunnel [cmd]          - Manage Cloudflare Tunnel"
        echo "    start               - Start tunnel only"
        echo "    stop                - Stop tunnel only"
        echo "    restart             - Restart tunnel"
        echo "    logs                - Show tunnel logs"
        echo "    status              - Check tunnel status"
        echo "  cleanup               - Clean up and rebuild everything"
        echo ""
        echo "Examples:"
        echo "  $0                    # Start bot (and tunnel if configured)"
        echo "  $0 start -b           # Build and start"
        echo "  $0 tunnel status      # Check tunnel status"
        echo "  $0 tunnel logs        # View tunnel logs"
        echo "  $0 stop               # Stop everything"
        ;;
esac