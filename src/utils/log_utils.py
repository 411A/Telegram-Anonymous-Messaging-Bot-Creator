"""Logging configuration: console/file handlers, timezone support, log filters."""
import logging
from datetime import datetime as dt
from logging.handlers import TimedRotatingFileHandler
from typing import Final
from zoneinfo import ZoneInfo

from configs.settings import (
    LOG_FILENAME,
    LOGGER_FILE_LEVEL,
    LOGGER_STREAM_LEVEL,
    LOGGER_TIMEZONE,
)
from utils.helpers import shorten_token

# Log messages with emojis for better visibility
log_messages: Final[dict[str, str]] = {
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

# Mapping from string level names to logging constants
_LOG_LEVELS: Final[dict[str, int]] = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}

def setup_logging() -> None:
    """Configure logging with both console and file handlers using native timezone."""
    # Mapping string levels to logging constants
    STREAM_LEVEL = _LOG_LEVELS.get(LOGGER_STREAM_LEVEL, logging.INFO)
    FILE_LEVEL = _LOG_LEVELS.get(LOGGER_FILE_LEVEL, logging.INFO)

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
    # Rotating File Handler with detailed formatting. Keep previous startup
    # failures so Docker restart loops can be diagnosed from persisted logs.
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
    """A custom logging filter to sanitize bot tokens and filter noisy 404 GET requests."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == 'uvicorn.access' and record.args and len(record.args) >= 5:
            args_list = list(record.args)
            method = args_list[1] if len(args_list) > 1 else ''
            path = args_list[2] if len(args_list) > 2 else ''
            status_code = str(args_list[4]) if len(args_list) > 4 else ''

            # Filter out all 404 GET requests (noisy logs)
            if method == 'GET' and '404' in status_code:
                return False

            # Sanitize webhook tokens in path
            if isinstance(path, str) and path.startswith("/webhook/"):
                args_list[2] = f"/webhook/{shorten_token(path.split('/')[2])}"
                record.args = tuple(args_list)
                if "403" in status_code:
                    record.msg = f"⚠️ Webhook security blocked: {record.msg}"

        return True


def patch_uvicorn_logging() -> None:
    """Patch Uvicorn loggers with our security filter and timezone-aware formatting.

    Finds the Uvicorn access logger and adds our security filter to it.
    Also configures timezone-aware formatting for FastAPI console output.
    """
    # Set timezone converter for all loggers
    logging_tz = ZoneInfo(LOGGER_TIMEZONE)

    # Custom formatter with timezone
    class TimezoneFormatter(logging.Formatter):
        def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
            dt_obj = dt.fromtimestamp(record.created, tz=logging_tz)
            if datefmt:
                return dt_obj.strftime(datefmt)
            return dt_obj.strftime('%Y/%m/%d %H:%M:%S')

    # Get the Uvicorn access logger
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_error_logger = logging.getLogger("uvicorn.error")

    # Add our custom filter to access logger
    uvicorn_access_logger.addFilter(WebhookLogFilter())

    # Configure timezone-aware formatting for console output
    console_format = "[%(levelname)s] %(asctime)s %(name)s: %(message)s"
    console_formatter = TimezoneFormatter(console_format, datefmt='%Y/%m/%d %H:%M:%S')

    # Apply formatter to existing handlers
    for handler in uvicorn_access_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setFormatter(console_formatter)

    for handler in uvicorn_error_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setFormatter(console_formatter)
