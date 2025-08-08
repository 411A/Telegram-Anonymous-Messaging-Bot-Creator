from typing import Final, Literal
import os
from dotenv import load_dotenv


load_dotenv(override=True)

#* Constants used throughout the application
#region Constants
# Log levels: https://docs.python.org/3/library/logging.html#logging-levels
LOGGER_STREAM_LEVEL: Final = 'ERROR'
LOGGER_FILE_LEVEL: Final = 'ERROR'

AVAILABLE_LANGUAGES_LITERAL: Final = Literal['en', 'fa']
AVAILABLE_LANGUAGES_LIST: Final = ['en', 'fa']
# Cache maximum 100 active bots in memory
MAX_IN_MEMORY_ACTIVE_BOTS: Final = 100
# 20 Minutes answer time
ADMIN_REPLY_TIMEOUT: Final = 60 * 20

# Separator character
SEP = '|'

SQLITE_DATABASE_NAME = 'DATA.db'
SECURE_CONFIG_FILE = 'config.secure'

# Emoji on InlineButtons
BTN_EMOJI_NO_HISTORY: Final = '😶‍🌫️'
BTN_EMOJI_WITH_HISTORY: Final = '😶‍🌫️💬'
BTN_EMOJI_FORWARD: Final = '😎'
BTN_EMOJI_READ: Final = '👀'
BTN_EMOJI_BLOCK: Final = '🚫'
BTN_EMOJI_UNBLOCK: Final = '🕊️'
BTN_EMOJI_ANSWER: Final = '👋'

# Callback data constants
CBD_ANON_NO_HISTORY: Final = f"SendAnon{SEP}NoHistory"
CBD_ANON_WITH_HISTORY: Final = f"SendAnon{SEP}WithHistory"
CBD_ANON_FORWARD: Final = f"SendAnon{SEP}Forward"
CBD_ADMIN_BLOCK: Final = "b"
CBD_ADMIN_ANSWER: Final = "a"
CBD_ADMIN_CANCEL_ANSWER: Final = "CancelReplyAnswer"
CBD_READ_MESSAGE: Final = "r"

# Telegram webhook IP ranges
# https://core.telegram.org/resources/cidr.txt
TELEGRAM_IP_RANGES = [
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

# CORS settings
CORS_SETTINGS = {
    'allow_origins': [],  # No origins allowed by default
    'allow_credentials': False,
    'allow_methods': ["POST"],  # Only allow POST for webhooks
    'allow_headers': ['*']
}
#endregion Constants

#region Environment Variables
MAIN_BOT_TOKEN = os.getenv('MAIN_BOT_TOKEN')
WEBHOOK_BASE_URL = os.getenv('WEBHOOK_BASE_URL')
TG_SECRET_TOKEN = os.getenv('TG_SECRET_TOKEN')
FASTAPI_PORT = int(os.getenv('FASTAPI_PORT') or 8000)
#endregion Environment Variables
