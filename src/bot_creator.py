import asyncio
import platform
import sys

# Performance optimization: Use uvloop on Unix systems
if platform.system() != 'Windows':
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass  # Fall back to default event loop

import ipaddress
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from telegram import Bot, Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaDocument
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, CallbackQueryHandler, filters
)
from telegram.error import TimedOut, NetworkError
from telegram.constants import ParseMode
from typing import Dict, List, Optional
from utils.db_utils import DatabaseManager, Encryptor, AdminManager
from utils.secure_config import get_encryption_key
from handlers.anonymous_handler import handle_messages, handle_anonymous_callback, handle_read_callback, handle_admin_callback
from utils.responses import get_response, ResponseKey, get_commands, CommandKey
from utils.log_utils import setup_logging, patch_uvicorn_logging
from utils.github_checker import (
    GitHubChecker,
    DIFFERENCES_FILE_NAME,
)
from utils.helpers import extract_bot_token, shorten_token, check_language_availability
from configs.settings import (
    CORS_SETTINGS, TELEGRAM_IP_RANGES, TRUSTED_PROXY_CIDRS,
    CBD_ANON_NO_HISTORY,
    CBD_ANON_WITH_HISTORY,
    CBD_ANON_FORWARD,
    CBD_READ_MESSAGE,
    CBD_ADMIN_BLOCK,
    CBD_ADMIN_ANSWER,
    CBD_ADMIN_CANCEL_ANSWER,
    MAX_IN_MEMORY_ACTIVE_BOTS,
    MAIN_BOT_TOKEN,
    WEBHOOK_BASE_URL,
    TG_SECRET_TOKEN,
    FASTAPI_PORT,
    DEVELOPER_GITHUB_USERNAME,
    DEVELOPER_GITHUB_REPOSITORY_NAME,
    GITHUB_CHECKER_FILENAME,
    TELEGRAM_REQUEST_TIMEOUT,
    TELEGRAM_CONNECTION_TIMEOUT,
    TELEGRAM_READ_TIMEOUT,
    WEBHOOK_DEDUP_CACHE_SIZE,
    WEBHOOK_DEDUP_TTL
)
import uvicorn
import logging
import time
import io
from pathlib import Path
import aiofiles

#! Import cachetools for LRUCache and prepare a per-bot lock dict.
from cachetools import LRUCache, TTLCache
from collections import defaultdict


# Initialize logging when module is imported
setup_logging()
# Patch uvicorn logging to sanitize bot tokens
patch_uvicorn_logging()

logger = logging.getLogger(__name__)

MAIN_BOT_USERNAME = None
# Global variables for GitHub checker cache and file data
GITHUB_CHECK_RESULTS = dict()
RUNNING_SCRIPT_DATA = None
GITHUB_CHECKER_DATA = None
RUNNING_SCRIPT_SINCE = None

# Update deduplication cache: stores update_id for 60 seconds to prevent duplicate processing
# This prevents webhook retry loops when Telegram resends the same update
PROCESSED_UPDATES = TTLCache(maxsize=WEBHOOK_DEDUP_CACHE_SIZE, ttl=WEBHOOK_DEDUP_TTL)

#! Define a custom LRUCache that calls a cleanup callback on eviction.
class ApplicationLRUCache(LRUCache):
    def __init__(self, maxsize, *args, **kwargs):
        self.on_evicted = kwargs.pop('on_evicted', None)
        super().__init__(maxsize, *args, **kwargs)

    def popitem(self):
        key, value = super().popitem()
        if self.on_evicted:
            # Schedule asynchronous cleanup of the bot application.
            asyncio.create_task(self.on_evicted(key, value))
        return key, value

#! Async cleanup callback when a bot application is evicted from the cache.
async def cleanup_application(token: str, application: Application):
    short_token = shorten_token(token)
    try:
        await application.stop()
    except RuntimeError as e:
        if "not running" in str(e):
            logger.info(f"Bot {short_token} is already stopped.")
        else:
            logger.exception(f"Error stopping bot {short_token}:\n{e}")
    try:
        await application.shutdown()
        logger.info(f"Cleaned up bot {short_token} due to cache eviction.")
    except Exception as e:
        logger.exception(f"Error shutting down bot {short_token} on eviction:\n{e}")

# Global LRU cache to store active bot applications.
active_bots = ApplicationLRUCache(maxsize=MAX_IN_MEMORY_ACTIVE_BOTS, on_evicted=cleanup_application)

#! Dictionary to hold per-bot locks to avoid concurrent reinitializations.
app_creation_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

security = HTTPBearer()

# Global variables to be initialized in the lifespan context
db_manager: Optional[DatabaseManager] = None
encryptor: Optional[Encryptor] = None
admin_manager: Optional[AdminManager] = None

async def main_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        logger.info(f"main_start: No effective message ({message}), returning")
        return
    user = update.effective_user
    if not user:
        logger.info(f"main_start: No effective user ({user}), returning")
        return
    user_lang = check_language_availability(user.language_code or 'en')
    
    try:
        await message.reply_text(get_response(ResponseKey.WELCOME, user_lang), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except TimedOut as e:
        logger.warning(f"Timeout error in main_start: {e}")
        try:
            await message.reply_text(get_response(ResponseKey.TIMEOUT_ERROR_RETRY, user_lang), parse_mode=ParseMode.HTML)
        except Exception:
            logger.error("Failed to send timeout error message")
    except NetworkError as e:
        logger.warning(f"Network error in main_start: {e}")
        try:
            await message.reply_text(get_response(ResponseKey.NETWORK_ERROR_RETRY, user_lang), parse_mode=ParseMode.HTML)
        except Exception:
            logger.error("Failed to send network error message")
    except Exception as e:
        logger.exception(f"Unexpected error in main_start: {e}")
        try:
            await message.reply_text(get_response(ResponseKey.OPERATION_FAILED_NETWORK, user_lang), parse_mode=ParseMode.HTML)
        except Exception:
            logger.error("Failed to send generic error message")

async def main_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        logger.info(f"main_about: No effective message ({message}), returning")
        return
    user = update.effective_user
    if not user:
        logger.info(f"main_about: No effective user ({user}), returning")
        return
    user_lang = check_language_availability(user.language_code or 'en')
    if user_lang == "fa":
        button_text = "💎 هدیه رمزارز TON به توسعه‌دهنده"
    else:
        button_text = "💎 Donate TON"
    keyboard = [[InlineKeyboardButton(button_text, url="ton://transfer/TechKraken.ton")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(
        get_response(
            ResponseKey.ABOUT_COMMAND,
            user_lang,
        ),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        quote=True,
        reply_markup=reply_markup
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAIN_BOT_USERNAME
    message = update.effective_message
    if not message:
        logger.info(f"start: No effective message ({message}), returning")
        return
    user = update.effective_user
    if not user:
        logger.info(f"start: No effective user ({user}), returning")
        return
    user_lang = check_language_availability(user.language_code or 'en')
    await message.reply_text(get_response(ResponseKey.START_COMMAND, user_lang, BOT_CREATOR_USERNAME=MAIN_BOT_USERNAME), parse_mode=ParseMode.HTML)

async def privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        logger.info(f"privacy: No effective message ({message}), returning")
        return
    user = update.effective_user
    if not user:
        logger.info(f"privacy: No effective user ({user}), returning")
        return
    user_lang = check_language_availability(user.language_code or 'en')
    await message.reply_text(get_response(ResponseKey.PRIVACY_COMMAND, user_lang), parse_mode=ParseMode.HTML, disable_web_page_preview=True, quote=True)

async def safetycheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GITHUB_CHECK_RESULTS, RUNNING_SCRIPT_SINCE, RUNNING_SCRIPT_DATA, GITHUB_CHECKER_DATA, GITHUB_CHECKER_FILENAME
    user = update.effective_user
    if not user:
        logger.info(f"safetycheck: No effective user ({user}), returning")
        return
    user_lang = check_language_availability(user.language_code or 'en')

    if user_lang not in GITHUB_CHECK_RESULTS:
        checker = GitHubChecker(
            repo_owner=DEVELOPER_GITHUB_USERNAME,
            repo_name=DEVELOPER_GITHUB_REPOSITORY_NAME,
            branch='main',
        )
        try:
            # Write differences first since it's used in the check_integrity results
            await checker.write_line_differences()
            # Get integrity check results
            GITHUB_CHECK_RESULTS[user_lang] = await checker.check_integrity(user_lang=user_lang)
            if not GITHUB_CHECK_RESULTS[user_lang]:
                logger.warning("GitHub checker returned empty results")
                GITHUB_CHECK_RESULTS[user_lang] = ["⚠️ No security issues detected"]
        except Exception as e:
            logger.exception(f"GitHub check failed: {str(e)}")
            GITHUB_CHECK_RESULTS[user_lang] = ["⚠️ Safety check unavailable"]

    try:
        # Verify global variables are initialized
        if not all([GITHUB_CHECK_RESULTS, RUNNING_SCRIPT_SINCE, RUNNING_SCRIPT_DATA]):
            raise ValueError("Safety check data not initialized")

        # Get results for current language
        current_results = GITHUB_CHECK_RESULTS[user_lang]

        # Prepare the caption message with an emoji and HTML formatting
        try:
            current_results = "\n".join(current_results)
            caption = get_response(
                ResponseKey.SAFETYCHECK_CAPTION,
                user_lang,
                RUNNING_SCRIPT_SINCE=RUNNING_SCRIPT_SINCE,
                GITHUB_CHECK_RESULTS=current_results
            )
        except Exception as e:
            logger.error(f"Error formatting safety check caption:\n{e}")
            raise ValueError("Failed to format safety check results")

        # Get the filename of the currently running script
        try:
            running_script_filename = Path(__file__).name
        except Exception as e:
            logger.error(f"Error getting script filename:\n{e}")
            running_script_filename = "bot_creator.py"

        # Create a new BytesIO instance from the cached file content
        try:
            if RUNNING_SCRIPT_DATA is None:
                raise ValueError("Running script data not loaded")
            main_file_to_send = io.BytesIO(RUNNING_SCRIPT_DATA)
            main_file_to_send.name = running_script_filename
        except Exception as e:
            logger.error(f"Error preparing file data:\n{e}")
            raise ValueError("Failed to prepare script file data")

        # Prepare the .md differences file using aiofiles
        try:
            diff_file_path = str(DIFFERENCES_FILE_NAME)
            async with aiofiles.open(diff_file_path, "rb") as diff_file:
                diff_file_data = io.BytesIO(await diff_file.read())
                diff_file_data.name = str(DIFFERENCES_FILE_NAME.name)
        except Exception as e:
            logger.error(f"Error reading diff file:\n{e}")
            raise ValueError("Failed to prepare diff file data")

        # Create a media group (album) to send both files in one message
        media_group = [
            InputMediaDocument(media=main_file_to_send, filename=running_script_filename),
        ]

        # Add GitHub checker data file if available
        try:
            if GITHUB_CHECKER_DATA:
                github_checker_file = io.BytesIO(GITHUB_CHECKER_DATA)
                github_checker_file.name = str(GITHUB_CHECKER_FILENAME.name)
                media_group.append(InputMediaDocument(media=github_checker_file, filename=str(GITHUB_CHECKER_FILENAME.name)))
        except Exception as e:
            logger.error(f"Error preparing GitHub checker data file:\n{e}")
            logger.warning("Continuing without GitHub checker data file")
        
        # Only add differences file if there are actual differences
        try:
            diff_file_path = DIFFERENCES_FILE_NAME
            if diff_file_path.exists() and diff_file_path.stat().st_size > 0:
                async with aiofiles.open(diff_file_path, "rb") as diff_file:
                    diff_file_data = io.BytesIO(await diff_file.read())
                    diff_file_data.name = str(DIFFERENCES_FILE_NAME.name)
                media_group.append(InputMediaDocument(media=diff_file_data, filename=str(DIFFERENCES_FILE_NAME.name)))
        except Exception as e:
            logger.error(f"Error reading diff file:\n{e}")
            # Continue without differences file rather than failing completely
            logger.warning("Continuing without differences file")

        # Send media group (both documents together)
        try:
            message = update.effective_message
            if not message:
                raise ValueError("No message to reply to")
            media_msgs = await message.reply_media_group(
                media=media_group,
                quote=True
            )
            
            # Send caption separately since Telegram doesn't allow captions on document groups
            await media_msgs[0].reply_text(
                caption,
                parse_mode=ParseMode.HTML,
                quote=True,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.exception(f"Error sending safety check documents:\n{e}")
            message = update.effective_message
            if message:
                await message.reply_text(
                    get_response(ResponseKey.SAFETYCHECK_ERROR, user_lang),
                    quote=True
                )

    except Exception as e:
        logger.error(f"Safety check failed:\n{e}")
        message = update.effective_message
        if message:
            try:
                await message.reply_text(
                    get_response(ResponseKey.SAFETYCHECK_FAILED, user_lang),
                    quote=True
                )
            except Exception as send_error:
                logger.error(f"Failed to send error message:\n{send_error}")

async def configure_bot_interface(bot: Bot, bot_username: str):
    """Configure bot settings including description and commands."""
    try:
        # Set bot description
        await bot.set_my_short_description(
            short_description=get_response(ResponseKey.CREATED_BOT_SHORT_DESCRIPTION, 'en', BOT_CREATOR_USERNAME=MAIN_BOT_USERNAME),
            language_code='en'
        )
        await bot.set_my_short_description(
            short_description=get_response(ResponseKey.CREATED_BOT_SHORT_DESCRIPTION, 'fa', BOT_CREATOR_USERNAME=MAIN_BOT_USERNAME),
            language_code='fa'
        )
        
        # Set bot commands with proper language code
        en_commands = get_commands(CommandKey.CREATED_BOT_COMMANDS, 'en')
        fa_commands = get_commands(CommandKey.CREATED_BOT_COMMANDS, 'fa')
        en_bot_commands = [BotCommand(command=cmd['command'], description=cmd['description']) for cmd in en_commands]
        fa_bot_commands = [BotCommand(command=cmd['command'], description=cmd['description']) for cmd in fa_commands]
        await bot.set_my_commands(commands=en_bot_commands, language_code='en')
        await bot.set_my_commands(commands=fa_bot_commands, language_code='fa')
        return True
    except Exception as e:
        logger.exception(f"Error configuring bot interface:\n{str(e)}")
        raise

async def create_and_configure_bot(token: str) -> Application:
    global MAIN_BOT_USERNAME
    short_token = shorten_token(token)
    bot_username = None
    webhook_info = None

    try:
        application = (
            Application.builder()
            .token(token)
            .concurrent_updates(10)
            .connection_pool_size(256)
            .pool_timeout(TELEGRAM_REQUEST_TIMEOUT)
            .connect_timeout(TELEGRAM_CONNECTION_TIMEOUT)
            .read_timeout(TELEGRAM_READ_TIMEOUT)
            .write_timeout(TELEGRAM_REQUEST_TIMEOUT)
            .build()
        )
        # Get bot instance
        new_bot = application.bot
        
        # Retry mechanism for bot info retrieval with timeout handling
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                bot_info = await new_bot.get_me()
                bot_username = bot_info.username
                break
            except TimedOut:
                if attempt < max_retries - 1:
                    logger.warning(f"Timeout getting bot info for {short_token}, attempt {attempt + 1}/{max_retries}, retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Failed to get bot info for {short_token} after {max_retries} attempts due to timeout")
                    raise
            except Exception as e:
                logger.error(f"Failed to get bot info for {short_token}: {type(e).__name__}")
                raise

        webhook_url = f'{WEBHOOK_BASE_URL}/webhook/{token}'

        # Get webhook info with retry mechanism
        retry_delay = 2  # Reset delay
        for attempt in range(max_retries):
            try:
                webhook_info = await new_bot.get_webhook_info()
                break
            except TimedOut:
                if attempt < max_retries - 1:
                    logger.warning(f"Timeout getting webhook info for {short_token}, attempt {attempt + 1}/{max_retries}, retrying...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"Failed to get webhook info for {short_token} after {max_retries} attempts due to timeout")
                    raise
            except Exception as e:
                logger.error(f"Failed to get webhook info for {short_token}: {type(e).__name__}")
                raise
                
    except Exception as e:
        logger.exception(f"Failed to initialize bot {short_token}:\n{str(e)}")
        raise

    try:
        if not webhook_info or not webhook_info.url or webhook_info.url != webhook_url:
            await new_bot.delete_webhook()
            # Set new webhook with proper configuration
            await new_bot.set_webhook(
                url=webhook_url,
                allowed_updates=['message', 'callback_query'],
                secret_token=TG_SECRET_TOKEN,
            )
            # Configure bot settings immediately after creation
            if bot_username:
                await configure_bot_interface(new_bot, bot_username)
            logger.info(f'Set new webhook for bot {short_token}')
        else:
            logger.info(f'Webhook already correctly configured for bot {short_token}')
    except Exception as e:
        logger.error(f"Failed to configure webhook for bot {short_token}:\n{str(e)}")
        raise

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('privacy', privacy))
    application.add_handler(CommandHandler('safetycheck', safetycheck))
    # Then add anonymous message handler for non-admin messages
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))
    application.add_handler(CallbackQueryHandler(handle_anonymous_callback, pattern=f'^({CBD_ANON_NO_HISTORY}|{CBD_ANON_WITH_HISTORY}|{CBD_ANON_FORWARD})'))
    application.add_handler(CallbackQueryHandler(handle_read_callback, pattern=f'^{CBD_READ_MESSAGE}'))
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern=f'^({CBD_ADMIN_BLOCK}|{CBD_ADMIN_ANSWER}|{CBD_ADMIN_CANCEL_ANSWER})'))

    await application.initialize()
    await application.start()
    logger.info(f'Bot {bot_username} started.')
    return application

#! Helper function to lazily get (or re-create) the Application for a given token.
async def get_application(bot_token: str) -> Application:
    if bot_token in active_bots:
        return active_bots[bot_token]
    lock = app_creation_locks[bot_token]
    async with lock:
        if bot_token not in active_bots:
            active_bots[bot_token] = await create_and_configure_bot(bot_token)
        return active_bots[bot_token]

async def revoke_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /revoke command to revoke bot access.
    
    Args:
        update (Update): The update containing the command.
        context (ContextTypes.DEFAULT_TYPE): The context object.
    """
    message = update.effective_message
    if not message:
        logger.info(f"revoke_bot: No effective message ({message}), returning")
        return
    chat = update.effective_chat
    if not chat:
        logger.info(f"revoke_bot: No effective chat ({chat}), returning")
        return
    user = update.effective_user
    if not user:
        logger.info(f"revoke_bot: No effective user ({user}), returning")
        return
    user_lang = check_language_availability(user.language_code or 'en')

    # Retrieve the latest chat info which includes the pinned message.
    chat_info = await context.bot.get_chat(chat.id)

    # Check if the command is used as a reply to a pinned message.
    if not message.reply_to_message or not (
        chat_info.pinned_message and chat_info.pinned_message.message_id == message.reply_to_message.message_id
    ):
        await message.reply_text(get_response(ResponseKey.REVOKE_INSTRUCTIONS, user_lang), quote=True, parse_mode=ParseMode.HTML)
        logger.info(f"revoke_bot: Command not used as reply to pinned message ({message.reply_to_message}), returning")
        return

    try:
        # Get the token from the pinned message.
        pinned_msg = message.reply_to_message
        if not pinned_msg or not pinned_msg.text or 'Token:' not in pinned_msg.text:
            await message.reply_text(get_response(ResponseKey.INVALID_PINNED_MESSAGE, user_lang), quote=True, parse_mode=ParseMode.HTML)
            logger.info(f"revoke_bot: Invalid pinned message ({pinned_msg}), returning")
            return

        raw_token = pinned_msg.text.split('Token:')[1].strip()
        token = extract_bot_token(raw_token)
        if not token:
            await message.reply_text(get_response(ResponseKey.INVALID_TOKEN, user_lang), quote=True, parse_mode=ParseMode.HTML)
            logger.info(f"revoke_bot: Invalid token extracted ({raw_token}), returning")
            return

        short_token = shorten_token(token)
        logger.info(f"Revoking bot access for {short_token}")

        # Remove bot from active bots if present.
        if token in active_bots:
            application = active_bots[token]
            try:
                # Revoke token through Telegram API using the Bot instance.
                await application.bot.delete_webhook()
                await application.stop()
                await application.shutdown()
                del active_bots[token]
                logger.info(f"Successfully stopped bot {short_token}")
            except Exception as e:
                logger.error(f"Error stopping bot {short_token}:\n{str(e)}")
                raise

        # Remove bot_token entry from database.
        assert encryptor is not None
        encrypted_bot_token = encryptor.encrypt(token, deterministic=True)
        assert db_manager is not None
        if await db_manager.remove_bot_entry(encrypted_bot_token):
            await pinned_msg.unpin()
            await message.reply_text(get_response(ResponseKey.REVOKE_SUCCESS, user_lang), quote=True, parse_mode=ParseMode.HTML)
        else:
            await message.reply_text(get_response(ResponseKey.REVOKE_ERROR, user_lang), quote=True, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.exception(f"Error revoking bot:\n{e}")
        await message.reply_text(get_response(ResponseKey.REVOKE_ERROR_DETAIL, user_lang, error=str(e)), quote=True, parse_mode=ParseMode.HTML)

async def register_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        logger.info(f"register_bot: No effective message ({message}), returning")
        return
    user = update.effective_user
    if not user:
        logger.info(f"register_bot: No effective user ({user}), returning")
        return
    user_lang = check_language_availability(user.language_code or 'en')
    if not context.args:
        await message.reply_text(get_response(ResponseKey.PROVIDE_TOKEN, user_lang), quote=True, parse_mode=ParseMode.HTML)
        logger.info(f"register_bot: No arguments provided ({context.args}), returning")
        return

    # Extract token using regex
    token = extract_bot_token(context.args[0])
    if not token:
        await message.reply_text(get_response(ResponseKey.INVALID_TOKEN), quote=True, parse_mode=ParseMode.HTML)
        logger.info(f"register_bot: Invalid token ({context.args[0]}), returning")
        return

    if token in active_bots:
        await message.reply_text(get_response(ResponseKey.ALREADY_REGISTERED), quote=True, parse_mode=ParseMode.HTML)
        logger.info("register_bot: Token already registered, returning")
        return

    user_id = user.id

    progress_message = None
    try:
        # Send initial progress message
        progress_message = await message.reply_text(get_response(ResponseKey.WAIT_REGISTERING_BOT, user_lang), quote=True, parse_mode=ParseMode.HTML)
        
        application = await create_and_configure_bot(token)
        new_bot = application.bot
        bot_info = await new_bot.get_me()
        bot_username = bot_info.username

        assert admin_manager is not None
        if await admin_manager.add_admin(token, bot_username, user_id):
            # Update progress message to show success
            await progress_message.edit_text(get_response(ResponseKey.ADMIN_REGISTERED))
        else:
            await progress_message.edit_text(get_response(ResponseKey.ALREADY_ADMIN))

        active_bots[token] = application

        registration_message = await message.reply_text(
            text=get_response(ResponseKey.BOT_REGISTERED_SUCCESS, user_lang, username=bot_username, token=token),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    text=get_response(ResponseKey.BOT_REGISTERED_SUCCESS_BUTTON_TEXT, user_lang),
                    url=f"https://t.me/{bot_username}?start=start"
                )]
            ]),
            parse_mode=ParseMode.HTML
        )
        await registration_message.pin()

    except Exception as e:
        logger.exception(f"Error registering bot:\n{e}")
        if progress_message:
            await progress_message.edit_text(f'Error registering bot:\n{str(e)}')
        else:
            await message.reply_text(f'Error registering bot:\n{str(e)}', parse_mode=ParseMode.HTML)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global RUNNING_SCRIPT_SINCE, RUNNING_SCRIPT_DATA, GITHUB_CHECKER_DATA, GITHUB_CHECKER_FILENAME, MAIN_BOT_USERNAME, db_manager, encryptor, admin_manager

    RUNNING_SCRIPT_SINCE = time.strftime("%Y/%m/%d %H:%M", time.gmtime())

    if RUNNING_SCRIPT_DATA is None:
        try:
            script_path = Path(__file__).resolve()
            logger.info(f"Loading script from: {script_path}")
            with open(script_path, 'rb') as f:
                RUNNING_SCRIPT_DATA = f.read()
            logger.debug(f"Successfully read {len(RUNNING_SCRIPT_DATA)} bytes")
        except Exception as e:
            logger.exception(f"File read error:\n{str(e)}")
            RUNNING_SCRIPT_DATA = None 

    if GITHUB_CHECKER_DATA is None:
        try:
            github_checker_file_path = GITHUB_CHECKER_FILENAME
            logger.info(f"Loading GitHub checker data file from: {github_checker_file_path}")
            async with aiofiles.open(github_checker_file_path, 'rb') as f:
                GITHUB_CHECKER_DATA = await f.read()
            logger.debug(f"Successfully read GitHub checker data, {len(GITHUB_CHECKER_DATA)} bytes")
        except Exception as e:
            logger.exception(f"GitHub checker data file read error:\n{str(e)}")
            GITHUB_CHECKER_DATA = None

    db_manager = DatabaseManager()
    encryption_key = get_encryption_key()
    if encryption_key is None:
        print("Encryption setup cancelled by user. Exiting gracefully.")
        sys.exit(0)
    encryptor = Encryptor(encryption_key)
    admin_manager = AdminManager(db_manager, encryptor)

    # Ensure MAIN_BOT_TOKEN is not None
    assert MAIN_BOT_TOKEN is not None, "MAIN_BOT_TOKEN must be set"

    # Initialize main bot with proper handlers
    main_app = (
        Application.builder()
        .token(MAIN_BOT_TOKEN)
        .connection_pool_size(256)
        .pool_timeout(TELEGRAM_REQUEST_TIMEOUT)
        .connect_timeout(TELEGRAM_CONNECTION_TIMEOUT)
        .read_timeout(TELEGRAM_READ_TIMEOUT)
        .write_timeout(TELEGRAM_REQUEST_TIMEOUT)
        .build()
    )
    main_app.add_handler(CommandHandler('start', main_start))
    main_app.add_handler(CommandHandler('register', register_bot))
    main_app.add_handler(CommandHandler('revoke', revoke_bot))
    main_app.add_handler(CommandHandler('safetycheck', safetycheck))
    main_app.add_handler(CommandHandler('privacy', privacy))
    main_app.add_handler(CommandHandler('about', main_about))

    try:
        if not MAIN_BOT_USERNAME:
            # Retrieve main bot info only once and store the username globally
            bot_info = await main_app.bot.get_me()
            MAIN_BOT_USERNAME = bot_info.username

        # Set webhook for main bot
        webhook_url = f'{WEBHOOK_BASE_URL}/webhook/{MAIN_BOT_TOKEN}'
        webhook_info = await main_app.bot.get_webhook_info()
        if not webhook_info.url or webhook_info.url != webhook_url:
            await main_app.bot.delete_webhook()
            # Set new webhook with proper configuration
            await main_app.bot.set_webhook(
                url=webhook_url,
                allowed_updates=['message'],
                secret_token=TG_SECRET_TOKEN,
            )
        else:
            logger.info('Main bot webhook already correctly configured')

        # Initialize and start the main bot
        await main_app.initialize()
        await main_app.start()
        active_bots[MAIN_BOT_TOKEN] = main_app
        logger.info('Main bot started successfully')

        yield

    except Exception as e:
        logger.exception(f'Error during startup:\n{str(e)}')
        yield
    finally:
        # Cleanup in finally block to ensure it runs even after errors
        logger.warning('Shutting down bots...')
        for token, bot in list(active_bots.items()):
            short_token = shorten_token(token)
            try:
                await bot.stop()
                await bot.shutdown()
                logger.info(f'Successfully stopped bot {short_token}')
            except Exception as e:
                logger.error(f'Error stopping bot {short_token}:\n{str(e)}')
        active_bots.clear()
        await db_manager.close_all()
        logger.warning('Cleanup completed.')

logger.warning("Starting FastAPI app...")
app = FastAPI(lifespan=lifespan)
logger.warning("FastAPI initialized.")

@app.post('/webhook/{bot_token}')
async def webhook_handler(bot_token: str, request: Request):
    def is_telegram_ip(ip_str: str, networks: List[str]) -> bool:
        try:
            ip = ipaddress.ip_address(ip_str)
            return any(ip in ipaddress.ip_network(net) for net in networks)
        except ValueError:
            return False

    def _parse_ip(ip_str: Optional[str]) -> Optional[ipaddress._BaseAddress]:
        if not ip_str:
            return None
        s = ip_str.strip()
        if s.startswith('[') and ']' in s:
            s = s.split(']')[0].lstrip('[')
        elif ':' in s and s.count(':') == 1:
            s = s.split(':')[0]
        try:
            return ipaddress.ip_address(s)
        except ValueError:
            return None

    client_host = request.client.host if request.client else None
    short_token = shorten_token(bot_token)
    
    if not client_host:
        logger.warning(f"Webhook access denied for {short_token}: Invalid client")
        raise HTTPException(status_code=403, detail="Access denied: Invalid client")
    
    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if received_secret != TG_SECRET_TOKEN:
        logger.warning(f"Webhook access denied for {short_token}: Invalid secret token from {client_host}")
        raise HTTPException(status_code=403, detail="Invalid secret token")
    
    peer_ip = _parse_ip(client_host)
    effective_ip: Optional[str] = None
    if peer_ip:
        trusted = any(
            peer_ip in (net if not isinstance(net, str) else ipaddress.ip_network(net, strict=False))
            for net in TRUSTED_PROXY_CIDRS
        )
        if trusted:
            xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
            if xff:
                first = xff.split(",")[0].strip()
                parsed = _parse_ip(first)
                if parsed:
                    effective_ip = str(parsed)
    if effective_ip is None and peer_ip is not None:
        effective_ip = str(peer_ip)

    is_telegram = is_telegram_ip(effective_ip, TELEGRAM_IP_RANGES) if effective_ip else False
    is_localhost = effective_ip in ['127.0.0.1', '::1']
    is_trusted_proxy = False
    if effective_ip:
        ip_obj = ipaddress.ip_address(effective_ip)
        is_trusted_proxy = any(
            ip_obj in (net if not isinstance(net, str) else ipaddress.ip_network(net, strict=False))
            for net in TRUSTED_PROXY_CIDRS
        )

    if not (is_telegram or is_localhost or is_trusted_proxy):
        logger.warning(f"Webhook access denied for {short_token}: Suspicious IP {client_host} with valid token")
        raise HTTPException(status_code=403, detail="Access denied: Suspicious origin")

    try:
        application = await get_application(bot_token)
    except Exception as e:
        logger.error(f"Bot application creation failed for {short_token}: {type(e).__name__}")
        return {"status": "error", "message": "Bot creation failed"}

    update_data = await request.json()
    update_obj = Update.de_json(update_data, application.bot)

    # Deduplicate updates to prevent processing the same webhook multiple times
    # Telegram may retry webhooks if it doesn't receive a timely response
    update_id = update_obj.update_id
    update_key = f"{short_token}:{update_id}"
    
    if update_key in PROCESSED_UPDATES:
        logger.debug(f"Skipping duplicate update {update_id} for bot {short_token}")
        return {"status": "ok", "message": "duplicate"}
    
    # Mark this update as processed (TTL cache will auto-expire after 60 seconds)
    PROCESSED_UPDATES[update_key] = time.time()

    try:
        application.update_queue.put_nowait(update_obj)
    except asyncio.QueueFull:
        logger.warning(f"Update queue full for bot {short_token}")
        # Remove from processed cache if we couldn't queue it
        PROCESSED_UPDATES.pop(update_key, None)
        return {"status": "error", "message": "Queue overloaded"}

    return {"status": "ok"}

app.add_middleware(CORSMiddleware, **CORS_SETTINGS)
logger.warning("Middleware added.")

if __name__ == '__main__':
    logger.warning("Starting Uvicorn server...")
    uvicorn.run("bot_creator:app", host="0.0.0.0", port=FASTAPI_PORT, reload=False, lifespan="on")
