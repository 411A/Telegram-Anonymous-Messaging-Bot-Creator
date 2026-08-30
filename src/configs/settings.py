"""Central application configuration.

Loads environment variables, exposes typed module-level constants used across
the application, and validates that all required environment variables are set
at import time (fail-fast for container restarts).
"""
import ipaddress
import os
from pathlib import Path
from typing import Final, Literal, TypeAlias

from dotenv import load_dotenv

# Base directory = one level up from src/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_FOLDER_NAME = 'data'
SECURE_CONFIG_FOLDER_NAME = 'secret'
LOG_FOLDER_NAME = 'logs'
DIFF_FOLDER_NAME = 'diff'
Path(BASE_DIR / DATA_FOLDER_NAME).mkdir(exist_ok=True)
Path(BASE_DIR / SECURE_CONFIG_FOLDER_NAME).mkdir(exist_ok=True)
Path(BASE_DIR / LOG_FOLDER_NAME).mkdir(exist_ok=True)
Path(BASE_DIR / DIFF_FOLDER_NAME).mkdir(exist_ok=True)

load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

#* Constants used throughout the application
#region Constants
# Log levels: https://docs.python.org/3/library/logging.html#logging-levels
LOGGER_STREAM_LEVEL: Final = os.getenv('LOGGER_STREAM_LEVEL', 'ERROR').upper()
LOGGER_FILE_LEVEL: Final = os.getenv('LOGGER_FILE_LEVEL', 'ERROR').upper()

# Retry settings for Infisical when running headless (no TTY)
# Seconds between retries
INFISICAL_RETRY_DELAY: Final[int] = 60
# Max retries before giving up (30 minutes total)
INFISICAL_MAX_RETRIES: Final[int] = 30

AVAILABLE_LANGUAGES_LITERAL: TypeAlias = Literal['en', 'fa']
AVAILABLE_LANGUAGES_LIST: Final = ['en', 'fa']
# Cache maximum 100 active bots in memory
MAX_IN_MEMORY_ACTIVE_BOTS: Final = 100
# 20 Minutes answer time
ADMIN_REPLY_TIMEOUT: Final = 60 * 20

# Network timeout settings (in seconds)
TELEGRAM_REQUEST_TIMEOUT: Final = 30
TELEGRAM_CONNECTION_TIMEOUT: Final = 10
TELEGRAM_READ_TIMEOUT: Final = 30

# Webhook deduplication settings
# Maximum number of processed updates to cache
WEBHOOK_DEDUP_CACHE_SIZE: Final = 10000
# How long to cache processed update IDs (in seconds)
WEBHOOK_DEDUP_TTL: Final = 240

# Circuit breaker settings for error message handling
# Maximum number of recent failures to track per user
CIRCUIT_BREAKER_CACHE_SIZE: Final = 1000
# Time window for failure tracking (in seconds)
CIRCUIT_BREAKER_TTL: Final = 60
# Number of consecutive failures before circuit opens
CIRCUIT_BREAKER_THRESHOLD: Final = 3

# Separator character used in callback payload serialization
SEP: Final[str] = '|'

SQLITE_DATABASE_NAME: Final[Path] = BASE_DIR / DATA_FOLDER_NAME / 'DATA.db'
SECURE_CONFIG_FILE: Final[Path] = BASE_DIR / SECURE_CONFIG_FOLDER_NAME / 'config.secure'
# The file where safety check differences are stored
DIFFERENCES_FILE_NAME: Final[Path] = BASE_DIR / DIFF_FOLDER_NAME / 'all_differences.md'
GITHUB_CHECKER_FILENAME: Final[Path] = BASE_DIR / 'src' / 'utils' / 'github_checker.py'

# GitHub repository details for the safety checker
DEVELOPER_GITHUB_USERNAME: Final = "411A"
DEVELOPER_GITHUB_REPOSITORY_NAME: Final = "Telegram-Anonymous-Messaging-Bot-Creator"

# Project URL
PROJECT_GITHUB_URL: Final = f"https://github.com/{DEVELOPER_GITHUB_USERNAME}/{DEVELOPER_GITHUB_REPOSITORY_NAME}"

# Emoji on InlineButtons
BTN_EMOJI_NO_HISTORY: Final = '😶‍🌫️'
BTN_EMOJI_WITH_HISTORY: Final = '😶‍🌫️💬'
BTN_EMOJI_FORWARD: Final = '😎'
BTN_EMOJI_READ: Final = '👀'
BTN_EMOJI_BLOCK: Final = '🚫'
BTN_EMOJI_UNBLOCK: Final = '🕊️'
BTN_EMOJI_ANSWER: Final = '👋'
BTN_EMOJI_DELAY: Final = '⏰'

# Callback data constants
CBD_ANON_NO_HISTORY: Final = f"SendAnon{SEP}NoHistory"
CBD_ANON_WITH_HISTORY: Final = f"SendAnon{SEP}WithHistory"
CBD_ANON_FORWARD: Final = f"SendAnon{SEP}Forward"
CBD_ADMIN_BLOCK: Final = "b"
CBD_ADMIN_ANSWER: Final = "a"
CBD_ADMIN_CANCEL_ANSWER: Final = "CancelReplyAnswer"
CBD_READ_MESSAGE: Final = "r"
CBD_DELAY_INFO: Final = "d"
CBD_RETRY_REGISTER: Final = "retry_register"

# Telegram webhook IP ranges
# https://core.telegram.org/resources/cidr.txt
TELEGRAM_IP_RANGES: Final[list[str]] = [
    # IPv4 ranges
    '91.108.56.0/22',
    '91.108.4.0/22',
    '91.108.8.0/22',
    '91.108.16.0/22',
    '91.108.12.0/22',
    '149.154.160.0/20',
    '91.105.192.0/23',
    '91.108.20.0/22',
    '185.76.151.0/24',
    # IPv6 ranges
    '2001:b28:f23d::/48',
    '2001:b28:f23f::/48',
    '2001:67c:4e8::/48',
    '2001:b28:f23c::/48',
    '2a0a:f280::/32'
]

# Replace with exact IPs/CIDRs of proxies you control (cloudflared container, nginx, etc.)
DOCKER_NETWORK_IP: Final[str] = os.getenv('DOCKER_NETWORK_IP', '').strip()


def _parse_trusted_proxy_cidrs(raw: str) -> list[ipaddress._BaseNetwork]:
    """Parse a comma-separated list of IPs/CIDRs into trusted proxy networks.

    Bare IPs are treated as ``/32`` hosts; invalid entries are skipped.
    Loopback is always trusted (container-internal traffic).
    """
    networks: list[ipaddress._BaseNetwork] = []
    for part in (p.strip() for p in raw.split(',') if p.strip()):
        try:
            networks.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            try:
                networks.append(ipaddress.ip_network(part + '/32', strict=False))
            except ValueError:
                continue
    networks.append(ipaddress.ip_network('127.0.0.1/32'))
    return networks


TRUSTED_PROXY_CIDRS: Final[list[ipaddress._BaseNetwork]] = _parse_trusted_proxy_cidrs(DOCKER_NETWORK_IP)

# CORS settings
CORS_SETTINGS: Final[dict] = {
    'allow_origins': [],  # No origins allowed by default
    'allow_credentials': False,
    'allow_methods': ["POST"],  # Only allow POST for webhooks
    'allow_headers': ['*']
}
#endregion Constants

#region Environment Variables
MAIN_BOT_TOKEN: Final = os.getenv('MAIN_BOT_TOKEN')
WEBHOOK_BASE_URL: Final = os.getenv('WEBHOOK_BASE_URL')
TG_SECRET_TOKEN: Final = os.getenv('TG_SECRET_TOKEN')
FASTAPI_PORT: Final[int] = int(os.getenv('FASTAPI_PORT') or 13360)
LOG_FILENAME: Final[Path] = BASE_DIR / LOG_FOLDER_NAME / (os.getenv('LOG_FILENAME') or 'Logs.log')
LOGGER_TIMEZONE: Final[str] = os.getenv('LOGGER_TIMEZONE') or 'UTC'
DEVELOPER_CONTACT_URL: Final[str] = os.getenv('DEVELOPER_CONTACT_URL') or 'https://t.me/ContactHydraBot'

# Validate required environment variables at startup
_REQUIRED_ENV_VARS: Final = {
    'MAIN_BOT_TOKEN': MAIN_BOT_TOKEN,
    'WEBHOOK_BASE_URL': WEBHOOK_BASE_URL,
    'TG_SECRET_TOKEN': TG_SECRET_TOKEN,
}
_MISSING_ENV_VARS: Final[list[str]] = [name for name, value in _REQUIRED_ENV_VARS.items() if not value]

if _MISSING_ENV_VARS:
    import sys
    print(f"❌ FATAL: Missing required environment variables: {', '.join(_MISSING_ENV_VARS)}")
    print("Please check your .env file and ensure all required variables are set.")
    sys.exit(1)  # Exit with error code to trigger Docker restart
#endregion Environment Variables
