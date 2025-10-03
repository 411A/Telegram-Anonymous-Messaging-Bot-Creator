from datetime import datetime as dt
from zoneinfo import ZoneInfo
import logging
from logging.handlers import TimedRotatingFileHandler
from typing import Dict
from configs.settings import LOG_FILENAME, LOGGER_TIMEZONE, LOGGER_STREAM_LEVEL, LOGGER_FILE_LEVEL
from utils.helpers import shorten_token

# Log messages with emojis for better visibility
log_messages: Dict[str, str] = {
    'bot_registered': '🤖 Bot registered successfully',
    'admin_added': '👑 New admin registered',
    'admin_exists': '👤 Admin already exists',
    'token_retrieved': '🔑 Retrieved bot token from pinned message',
    'webhook_set': '🔗 Webhook configured',
    'bot_started': '▶️ Bot started and initialized',
    'error_register': '❌ Error during bot registration',
    'error_token': '⚠️ Invalid or missing bot token',
    'already_registered': '🟢 Bot is already registered',
    'error_webhook': '🔥 Webhook setup failed',
    'error_admin': '⛔ Admin operation failed'
}

def setup_logging():

    # Mapping string levels to logging constants
    level_mapping = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
        "NOTSET": logging.NOTSET
    }

    STREAM_LEVEL = level_mapping.get(LOGGER_STREAM_LEVEL, logging.INFO)
    FILE_LEVEL = level_mapping.get(LOGGER_FILE_LEVEL, logging.INFO)

    """Configure logging with both console and file handlers using native timezone."""
    # CLI Fonts for console output
    cli_fonts = {
        "RESET": "\033[0m",
        "BOLD": "\033[1m",
        "YELLOW": "\033[33m",
    }

    # Formats and settings
    file_logging_format = f"\n{'─'*5}\n📅 %(asctime)s.%(msecs)03d 💥%(levelname)s💥 📁 %(filename)s 🔢%(lineno)d\n📝 %(message)s"
    logging_date_format = r"%Y/%m/%d %H:%M:%S"
    logging_tz = ZoneInfo(LOGGER_TIMEZONE)

    # Set timezone converter using native Python timezone
    logging.Formatter.converter = lambda *args: dt.now(tz=logging_tz).timetuple()

    # Get logger instance
    logger = logging.getLogger()
    logger.setLevel(STREAM_LEVEL)

    # Remove existing handlers to avoid duplication
    for handler in logger.handlers:
        logger.removeHandler(handler)

    # Console Handler with colored output
    stream_logging = logging.StreamHandler()
    stream_logging.setFormatter(logging.Formatter(
        f"{cli_fonts['BOLD']}{cli_fonts['YELLOW']}[%(asctime)s.%(msecs)03d]{cli_fonts['RESET']} %(message)s",
        logging_date_format
    ))
    logger.addHandler(stream_logging)
    # Rotating File Handler with detailed formatting
    # Clear the log file before setting up the handler
    try:
        with open(LOG_FILENAME, 'w', encoding='utf-8') as f:
            f.truncate(0)
    except FileNotFoundError:
        pass
    file_logging = TimedRotatingFileHandler(
        filename=LOG_FILENAME,
        encoding='utf-8',
        # Rotation happens at midnight
        when='midnight',
        # Rotate every 3 days
        interval=3,
        # Keep 2 backup files
        backupCount=2,
    )
    file_logging.setLevel(FILE_LEVEL)
    file_logging.setFormatter(logging.Formatter(file_logging_format, logging_date_format))
    logger.addHandler(file_logging)

class WebhookLogFilter(logging.Filter):
    """A custom logging filter to sanitize bot tokens from webhook URLs."""
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == 'uvicorn.access' and record.args and len(record.args) >= 5:
            # Convert args to list for safe indexing
            args_list = list(record.args)
            if len(args_list) > 2:
                path = args_list[2]

                # Type-check to ensure 'path' is a string
                if isinstance(path, str) and path.startswith("/webhook/"):
                    token = path.split('/')[2]
                    sanitized_path = f"/webhook/{shorten_token(token)}"
                    
                    args_list[2] = sanitized_path
                    record.args = tuple(args_list)
        
        return True


def patch_uvicorn_logging():
    """
    Finds the Uvicorn access logger and adds our security filter to it.
    """
    # Get ONLY the logger that handles access messages
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    
    # Add our custom filter to it
    uvicorn_access_logger.addFilter(WebhookLogFilter())
