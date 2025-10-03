from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes
from telegram import Message, InlineKeyboardButton, InlineKeyboardMarkup, ReactionTypeEmoji
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest
from utils.responses import get_response, ResponseKey
from utils.db_utils import DatabaseManager, Encryptor, AdminManager
from utils.helpers import generate_anonymous_id, check_language_availability
from utils.cache import AdminsReplyCache
from configs.settings import (
    SEP,
    CBD_ANON_NO_HISTORY,
    CBD_ANON_WITH_HISTORY,
    CBD_ANON_FORWARD,
    CBD_READ_MESSAGE,
    CBD_ADMIN_BLOCK,
    CBD_ADMIN_ANSWER,
    CBD_ADMIN_CANCEL_ANSWER,
    BTN_EMOJI_READ,
    BTN_EMOJI_BLOCK,
    BTN_EMOJI_UNBLOCK,
    BTN_EMOJI_ANSWER,
    BTN_EMOJI_NO_HISTORY,
    BTN_EMOJI_WITH_HISTORY,
    BTN_EMOJI_FORWARD,
    ADMIN_REPLY_TIMEOUT
)
import time
import logging
import asyncio

logger = logging.getLogger(__name__)

# Initialize the AdminsReplyCache singleton
admins_reply_cache = AdminsReplyCache()

#region Helpers

def generate_inline_buttons_anonymous(user_lang: str) -> InlineKeyboardMarkup:
    '''
    Generate the inline keyboard markup for anonymous message options.
    
    Creates a keyboard with three buttons:
    1. Send anonymously without history
    2. Send anonymously with history tracking
    3. Forward message with sender name
    
    Args:
        user_lang (str): The language code for button text localization
        
    Returns:
        InlineKeyboardMarkup: The configured keyboard markup with anonymous sending options
    '''
    keyboard = [
        [InlineKeyboardButton(str(get_response(ResponseKey.ANONYMOUS_INLINEBUTTON1, user_lang)), callback_data=CBD_ANON_NO_HISTORY)],
        [InlineKeyboardButton(str(get_response(ResponseKey.ANONYMOUS_INLINEBUTTON2, user_lang)), callback_data=CBD_ANON_WITH_HISTORY)],
        [InlineKeyboardButton(str(get_response(ResponseKey.ANONYMOUS_INLINEBUTTON3, user_lang)), callback_data=CBD_ANON_FORWARD)]
    ]
    return InlineKeyboardMarkup(keyboard)

#endregion Helpers

#region Admin
async def handle_admin_answer(query: CallbackQuery, admin_id: int, sender_user_id: int, original_message_id: int, context: ContextTypes.DEFAULT_TYPE):
    '''
    Handle the admin's answer option for an anonymous message.
    
    Sets up the reply context and initiates a timeout for the admin's response. Creates a cancel button
    for the admin to manually cancel their reply attempt, and stores the reply state in cache.
    
    Args:
        query (CallbackQuery): The callback query from the admin's button press
        admin_id (int): The ID of the admin handling the reply
        sender_user_id (int): The ID of the original message sender
        original_message_id (int): The ID of the original message being replied to
        context (ContextTypes.DEFAULT_TYPE): The context object for the bot
    
    Raises:
        Exception: If there's an error in handling the admin answer process
    '''
    if not query.from_user:
        logger.warning("handle_admin_answer: No user in callback query, returning")
        return
    if not query.message or not isinstance(query.message, Message):
        logger.warning("handle_admin_answer: No valid message in callback query, returning")
        return
    if not query.message.reply_to_message:
        logger.warning("handle_admin_answer: No reply_to_message in callback query message, returning")
        return
        
    user_lang = check_language_availability(query.from_user.language_code or 'en')
    admin_id = int(admin_id)
    try: 
        # Create cancel button keyboard and inform admin
        cancel_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_response(ResponseKey.ADMIN_BUTTON_CANCEL_MANUALLY, user_lang), callback_data=CBD_ADMIN_CANCEL_ANSWER)]
        ])
        # Inform the admin to reply within a specific timeout
        wait_msg = await query.message.reply_to_message.reply_text(
            text=get_response(ResponseKey.ADMIN_REPLY_WAIT, user_lang, minutes=round(ADMIN_REPLY_TIMEOUT / 60)),
            quote=True,
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_keyboard
        )
        
        # Store the reply state in the cache
        await admins_reply_cache.set(admin_id, {
            'target_user_id': sender_user_id,
            'original_message_id': original_message_id,
            'chat_id': query.message.chat_id,
            'wait_msg': wait_msg
        })

        # Start a timeout task for cleaning up state after ADMIN_REPLY_TIMEOUT
        asyncio.create_task(reply_timeout_handler(query, admin_id, context))
        # Optionally notify that the admin action is being processed
        await query.answer(get_response(ResponseKey.ADMIN_REPLY_AWAITING, user_lang), show_alert=False)
    except Exception as e:
        logger.exception(f"Error handling admin answer option:\n{e}")
        await query.answer(get_response(ResponseKey.ADMIN_REPLY_ERROR, user_lang), show_alert=True)


async def reply_timeout_handler(query: CallbackQuery, admin_id: int, context: ContextTypes.DEFAULT_TYPE, timeout=ADMIN_REPLY_TIMEOUT):
    '''
    Handle the timeout for admin replies by cleaning up the waiting state.
    
    After the specified timeout period, checks if the admin has responded. If not, updates the wait
    message and removes the reply state from cache.
    
    Args:
        query (CallbackQuery): The original callback query that initiated the reply
        admin_id (int): The ID of the admin whose reply is being timed out
        context (ContextTypes.DEFAULT_TYPE): The context object for the bot
        timeout (int, optional): The timeout duration in seconds. Defaults to ADMIN_REPLY_TIMEOUT
    '''
    await asyncio.sleep(timeout)
    if not query.from_user:
        logger.warning("reply_timeout_handler: No user in callback query, returning")
        return
    user_lang = check_language_availability(query.from_user.language_code or 'en')
    # Check if the waiting state still exists (i.e. admin did not reply)
    if await admins_reply_cache.exists(admin_id):
        state = await admins_reply_cache.get(admin_id)
        wait_msg: Message | None = state.get('wait_msg') if state else None
        if wait_msg:
            try:
                await wait_msg.edit_text(
                    text=get_response(ResponseKey.ADMIN_REPLY_TIMEOUT, user_lang),
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
        # Remove the state from cache
        await admins_reply_cache.remove(admin_id)


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Process callback queries for admin control options (block/answer).
    
    Handles the initial processing of admin callback queries, decrypts the callback data,
    and routes to appropriate handlers for specific actions. Manages admin reply states
    and prevents concurrent reply operations.
    
    Args:
        update (Update): The update object containing the callback query
        context (ContextTypes.DEFAULT_TYPE): The context object for the bot
    
    Returns:
        None
    
    Note:
        Expects callback data in format: operation SEP prefix SEP suffix
        For admin callbacks, the decrypted data format is:
        option SEP admin_id SEP sender_user_id SEP original_message_id SEP timestamp
    '''
    query = update.callback_query
    if query is None:
        logger.warning("handle_admin_callback: No callback query found, returning")
        return
    
    if not query.from_user:
        logger.warning("handle_admin_callback: No user in callback query, returning")
        return
    
    if not query.message or not isinstance(query.message, Message):
        logger.warning("handle_admin_callback: No valid message in callback query, returning")
        return
    
    query_data = query.data
    if not query_data:
        logger.warning("handle_admin_callback: No callback data found, returning")
        return
        
    user_lang = check_language_availability(query.from_user.language_code or 'en')
    admin_id = int(query.from_user.id)

    # Handle cancel reply button click
    if query_data == CBD_ADMIN_CANCEL_ANSWER:
        # Check if admin has an ongoing reply operation
        if await admins_reply_cache.exists(admin_id):
            # Update the wait message text
            await query.message.edit_text(get_response(ResponseKey.ADMIN_CANCELED_REPLY_MANUALLY, user_lang))
            # Clean up the reply state from cache
            await admins_reply_cache.remove(admin_id)
            return

    try:
        # Expecting data in format: operation SEP prefix SEP suffix
        operation, prefix, suffix = query_data.split(SEP)
    except Exception as e:
        logger.exception(f"Can't extract prefix and suffix:\n{e}", exc_info=True)
        return

    # Check if there's an ongoing answer operation when trying to start a new one
    if operation == CBD_ADMIN_ANSWER:
        if await admins_reply_cache.exists(admin_id):
            await query.answer(get_response(ResponseKey.ADMIN_ONGOING_REPLY, user_lang), show_alert=True)
            return

    try:

        db_manager = DatabaseManager()
        full_encrypted_hash = await db_manager.get_full_hash_by_prefix(prefix, suffix, 'messages')
        encryptor = Encryptor()

        if not full_encrypted_hash:
            await query.answer(get_response(ResponseKey.ADMIN_INVALID_MESSAGE_DATA, user_lang), show_alert=True)
            logger.warning("handle_admin_callback: No encrypted hash found for prefix/suffix")
            return

        try:
            raw_admin_callback = encryptor.decrypt(full_encrypted_hash)
            # Expecting raw_admin_callback in format: option SEP admin_id SEP sender_user_id SEP original_message_id SEP timestamp
            option, admin_id_str, sender_user_id_str, original_message_id_str, timestamp = raw_admin_callback.split(SEP)
            # Convert IDs to integers
            admin_id = int(admin_id_str)
            sender_user_id = int(sender_user_id_str)
            original_message_id = int(original_message_id_str)
        except Exception as decrypt_error:
            await query.answer(get_response(ResponseKey.ADMIN_INVALID_MESSAGE_DATA, user_lang), show_alert=True)
            logger.exception(f"Error: Invalid message data:\n{decrypt_error}")
            return

        # Offload handling to separate tasks so that this callback can quickly return
        if operation == CBD_ADMIN_ANSWER:
            asyncio.create_task(handle_admin_answer(query, admin_id, sender_user_id, original_message_id, context))
        elif operation == CBD_ADMIN_BLOCK:
            asyncio.create_task(handle_admin_block(query, admin_id, context))
        else:
            logger.error(f"Unknown operation: {operation}")
            await query.answer(get_response(ResponseKey.ADMIN_UNKNOWN_OPERATION, user_lang), show_alert=True)

    except Exception as db_error:
        logger.exception(f"Database or processing error in callback:\n{db_error}")
        await query.answer(get_response(ResponseKey.ADMIN_DATABASE_ERROR, user_lang), show_alert=True)

async def handle_admin_block(query: CallbackQuery, admin_id: int, context: ContextTypes.DEFAULT_TYPE):
    '''
    Process the admin's block/unblock action for a user.
    
    Toggles the block status of a user and updates the message UI accordingly.
    Handles both blocking and unblocking operations, updating the message text
    and keyboard buttons to reflect the current state.
    
    Args:
        query (CallbackQuery): The callback query from the admin's block/unblock action
        admin_id (int): The ID of the admin performing the action
        context (ContextTypes.DEFAULT_TYPE): The context object for the bot
    
    Raises:
        Exception: If there's an error in the blocking/unblocking process
    '''
    if not query.from_user:
        logger.warning("handle_admin_block: No user in callback query, returning")
        return
    if not query.message or not isinstance(query.message, Message):
        logger.warning("handle_admin_block: No valid message in callback query, returning")
        return
        
    user_lang = check_language_availability(query.from_user.language_code or 'en')
    admin_id = int(admin_id)
    try:
        # Get the bot username
        bot_username = context.bot.username
        
        # Check if the message has a reply markup and buttons
        if not query.message.reply_markup or not query.message.reply_markup.inline_keyboard:
            await query.answer(get_response(ResponseKey.ADMIN_INVALID_MESSAGE_DATA, user_lang), show_alert=True)
            return
        
        #! Extract the inline keyboard from the message.
        keyboard = query.message.reply_markup.inline_keyboard

        if len(keyboard) > 1 and len(keyboard[0]) > 0 and len(keyboard[1]) > 1:
            #! First row contains the read button.
            read_callback_data = keyboard[0][0].callback_data
            raw_admin_callback = keyboard[1][0].callback_data
            answer_callback_data = keyboard[1][1].callback_data
        elif len(keyboard) > 0 and len(keyboard[0]) > 1:
            #! Only one row is present; assume read is not available.
            read_callback_data = None
            #! Expect two buttons: block and answer.
            raw_admin_callback = keyboard[0][0].callback_data
            answer_callback_data = keyboard[0][1].callback_data
        else:
            await query.answer(get_response(ResponseKey.ADMIN_INVALID_MESSAGE_DATA, user_lang), show_alert=True)
            logger.warning("handle_admin_block: Invalid keyboard structure")
            return

        if not raw_admin_callback:
            await query.answer(get_response(ResponseKey.ADMIN_INVALID_MESSAGE_DATA, user_lang), show_alert=True)
            return
        
        if not isinstance(raw_admin_callback, str):
            await query.answer(get_response(ResponseKey.ADMIN_INVALID_MESSAGE_DATA, user_lang), show_alert=True)
            logger.warning("handle_admin_block: Invalid callback data type")
            return
        
        operation, prefix, suffix = raw_admin_callback.split(SEP)
        
        # Get the full hash and decrypt it to get sender_user_id
        db_manager = DatabaseManager()
        full_encrypted_hash = await db_manager.get_full_hash_by_prefix(prefix, suffix, 'messages')
        encryptor = Encryptor()
        
        if not full_encrypted_hash:
            await query.answer(get_response(ResponseKey.ADMIN_INVALID_MESSAGE_DATA, user_lang), show_alert=True)
            logger.warning("handle_admin_block: No encrypted hash found for prefix/suffix")
            return
            
        decrypted_data = encryptor.decrypt(full_encrypted_hash)
        option, admin_id_str, sender_user_id_str, original_message_id_str, timestamp = decrypted_data.split(SEP)
        
        # Convert sender_user_id to integer
        sender_user_id = int(sender_user_id_str)

        # Check if user is already blocked
        is_blocked = await db_manager.is_user_blocked(sender_user_id, bot_username)
        
        # Update block status and message
        message_text = query.message.text
        if not message_text:
            await query.answer(get_response(ResponseKey.ADMIN_INVALID_MESSAGE_DATA, user_lang), show_alert=True)
            logger.warning("handle_admin_block: No message text found")
            return
        if is_blocked:
            # Unblock user
            success = await db_manager.unblock_user(sender_user_id, bot_username)
            if success:
                # Remove #BLOCKED from message
                updated_text = message_text.replace("#BLOCKED\n", "")
                await query.answer(get_response(ResponseKey.ADMIN_USER_UNBLOCKED, user_lang), show_alert=True)
                # Update keyboard buttons
                new_keyboard = [
                    [
                        InlineKeyboardButton(f"{BTN_EMOJI_BLOCK} Block", callback_data=raw_admin_callback),
                        InlineKeyboardButton(f"{BTN_EMOJI_ANSWER} Answer", callback_data=answer_callback_data)
                    ]
                ]
                if read_callback_data:
                    new_keyboard.insert(0, [InlineKeyboardButton(f"{BTN_EMOJI_READ} Read", callback_data=read_callback_data)])
                # Update message with new text and keyboard
                await query.message.edit_text(
                    text=updated_text,
                    reply_markup=InlineKeyboardMarkup(new_keyboard)
                )
            else:
                await query.answer(get_response(ResponseKey.ADMIN_UNBLOCK_ERROR, user_lang), show_alert=True)
                return
        else:
            # Block user
            success = await db_manager.block_user(sender_user_id, bot_username)
            if success:
                # Add #BLOCKED to message
                if "#BLOCKED" not in message_text:
                    updated_text = message_text.replace("🎛️ Admin controls:", "#BLOCKED\n🎛️ Admin controls:")
                else:
                    updated_text = message_text

                # Update keyboard buttons
                new_keyboard = [
                    [
                        InlineKeyboardButton(f"{BTN_EMOJI_UNBLOCK} Unblock", callback_data=raw_admin_callback),
                        InlineKeyboardButton(f"{BTN_EMOJI_ANSWER} Answer", callback_data=answer_callback_data)
                    ]
                ]
                if read_callback_data:
                    new_keyboard.insert(0, [InlineKeyboardButton(f"{BTN_EMOJI_READ} Read", callback_data=read_callback_data)])
                # Update message with new text and keyboard
                await query.message.edit_text(
                    text=updated_text,
                    reply_markup=InlineKeyboardMarkup(new_keyboard)
                )
                await query.answer(get_response(ResponseKey.ADMIN_USER_BLOCKED, user_lang), show_alert=True)
            else:
                await query.answer(get_response(ResponseKey.ADMIN_BLOCK_PROCESS_ERROR, user_lang), show_alert=True)
                return
        
    except Exception as e:
        logger.exception(f"Error handling admin block option\n{e}")
        await query.answer(get_response(ResponseKey.ADMIN_BLOCK_PROCESS_ERROR, user_lang), show_alert=True)
#endregion Admin

#region Messages
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Process incoming messages and route them based on sender type (admin/user).
    
    For admin messages, handles ongoing reply operations. For user messages,
    processes them according to user's block status and provides anonymous
    sending options.
    
    Args:
        update (Update): The update object containing the message
        context (ContextTypes.DEFAULT_TYPE): The context object for the bot
    
    Returns:
        None
    '''
    message = update.effective_message
    if not message:
        logger.warning("handle_messages: No effective message found, returning")
        return
    
    user = update.effective_user
    if not user:
        logger.warning("handle_messages: No effective user found, returning")
        return
    
    db_manager = DatabaseManager()
    # Get user language code
    user_lang = check_language_availability(user.language_code or 'en')
    # Get bot's username
    bot_username = context.bot.username
    # Get admin manager singleton instance
    admin_manager = AdminManager()
    
    # Get user ID from the message
    user_id = user.id
    
    
    #* Handle admin message
    # Check if sender is admin
    is_admin = await admin_manager.is_admin(user_id, bot_username)
    
    if is_admin:
        # Check if admin has an active reply context in the cache
        admin_reply_state = await admins_reply_cache.get(user_id)
        
        if admin_reply_state:
            # Route to admin message handler
            try:
                target_user_id = admin_reply_state.get('target_user_id')
                original_message_id = admin_reply_state.get('original_message_id')
                                
                # 1. Get sender's id
                sender_user_id = user.id
                # 2. Get message_id
                message_id = message.message_id
                # 3. Get Unix timestamp with nanoseconds
                timestamp_ns = time.time_ns()
                                
                # Construct the callback string for read callback
                raw_read_callback = f"{sender_user_id}{SEP}{message_id}{SEP}{timestamp_ns}"
                # 4. Encrypt the callback string
                encryptor = Encryptor()
                encrypted_read_callback = encryptor.encrypt(raw_read_callback)
                # Store the encrypted callback in the database (without last 30 characters)
                read_stored_hash = encrypted_read_callback[:-30]
                read_button_prefix = encrypted_read_callback[:30]
                read_button_suffix = encrypted_read_callback[-30:]
                read_callback = f"{CBD_READ_MESSAGE}{SEP}{read_button_prefix}{SEP}{read_button_suffix}"
                
                user_keyboard = [
                    [
                        InlineKeyboardButton(f"{BTN_EMOJI_READ} Read", callback_data=read_callback),
                    ],
                ]
                user_markup = InlineKeyboardMarkup(user_keyboard)

                try:
                    # Ensure target_user_id is an integer
                    target_user_id = int(target_user_id) if target_user_id else None
                    original_message_id = int(original_message_id) if original_message_id else None
                    
                    if not target_user_id or not original_message_id:
                        raise ValueError("Invalid target_user_id or original_message_id")
                    
                    try:
                        # Send the admin's reply to the target user
                        await message.copy(
                            chat_id=target_user_id,
                            reply_to_message_id=original_message_id,
                            reply_markup=user_markup
                        )
                    except Forbidden:
                        # Handle case where the bot is blocked by the user
                        logger.error("Bot is blocked by user. Cannot send reply.")
                        await message.reply_text(
                            text=get_response(ResponseKey.ADMIN_REPLY_FAILED_USER_BLOCKED_BOT, user_lang),
                            quote=True,
                            parse_mode=ParseMode.HTML
                        )
                        # Clean up the reply state from cache
                        await admins_reply_cache.remove(user_id)
                        return

                    # Handle the wait message
                    wait_msg: Message | None = admin_reply_state.get('wait_msg')
                    if wait_msg:
                        try:
                            # Get the original message the wait_msg was replying to
                            original_msg = wait_msg.reply_to_message
                            if original_msg:
                                # Send new message as reply to original
                                await original_msg.reply_text(
                                    text=get_response(ResponseKey.ADMIN_REPLY_SENT, user_lang),
                                    parse_mode=ParseMode.HTML,
                                    quote=True
                                )
                            # Delete the wait message
                            await wait_msg.delete()
                        except Exception as e:
                            logger.error(f"Failed to handle wait message: {e}")
                            pass

                    # Clean up the reply state from cache
                    await admins_reply_cache.remove(user_id)

                    # Store the encrypted message hash
                    db_manager = DatabaseManager()
                    await db_manager.store_partial_hash(read_button_prefix, read_stored_hash, 'reads')
                    
                except Exception as e:
                    logger.error(f"Failed to send admin reply: {str(e)}\nStack trace:", exc_info=True)
                    await message.reply_text(text=get_response(ResponseKey.ADMIN_REPLY_FAILED, user_lang), quote=True, parse_mode=ParseMode.HTML)
                    # Clean up the reply state from cache on error
                    await admins_reply_cache.remove(user_id)
            except Exception as e:
                logger.error(f"Error in admin reply handler: {str(e)}\nStack trace:", exc_info=True)
                await message.reply_text(text=get_response(ResponseKey.ADMIN_REPLY_FAILED, user_lang), quote=True, parse_mode=ParseMode.HTML)
                # Clean up the reply state from cache on error
                await admins_reply_cache.remove(user_id)
        else:
            try:
                # Inform admin to use the Answer button
                await message.reply_text(get_response(ResponseKey.ADMIN_MUST_USE_ANSWER_BUTTON, user_lang), parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.exception(f"Failed to inform admin about reply context, blocked its bot or am I in a group without right permissions?!:\n{str(e)}")
        return

    # Check if user is blocked
    if await db_manager.is_user_blocked(user_id, bot_username):
        await message.reply_text(get_response(ResponseKey.USER_BLOCKED, user_lang), parse_mode=ParseMode.HTML)
        return

    # Handle anonymous message for non-admin users
    keyboard = generate_inline_buttons_anonymous(user_lang)
    await message.reply_text(
        text=get_response(ResponseKey.ANONYMOUS_INLINEBUTTON_REPLY_TEXT, user_lang),
        reply_markup=keyboard,
        reply_to_message_id=message.message_id,
        parse_mode=ParseMode.HTML
    )
#endregion Messages

#region Anon CB
async def handle_anonymous_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Process callback queries for anonymous message sending options.
    
    Handles three types of anonymous sending:
    1. No history - Send message without tracking sender
    2. With history - Send message with anonymous ID for history tracking
    3. Forward - Forward message with sender's name
    
    Implements message encryption, admin control button generation, and
    appropriate message routing based on the selected anonymity option.
    
    Args:
        update (Update): The update object containing the callback query
        context (ContextTypes.DEFAULT_TYPE): The context object for the bot
    
    Returns:
        None
    '''

    query = update.callback_query
    if not query:
        logger.warning("handle_anonymous_callback: No callback query found, returning")
        return
    
    if not query.from_user:
        logger.warning("handle_anonymous_callback: No user in callback query, returning")
        return
    
    if not query.message or not isinstance(query.message, Message):
        logger.warning("handle_anonymous_callback: No valid message in callback query, returning")
        return

    query_data = query.data
    if not query_data:
        logger.warning("handle_anonymous_callback: No callback data found, returning")
        return
        
    user_lang = check_language_availability(query.from_user.language_code or 'en')

    original_sender_message = query.message.reply_to_message
    
    # Check if the original message still exists
    if not original_sender_message:
        await query.message.edit_text(get_response(ResponseKey.USER_ERROR_ORIGINAL_MESSAGE_DELETED, user_lang))
        logger.warning("User tried to use a callback for a deleted message.")
        return

    # Show encryption status message to user
    await query.message.edit_text(get_response(ResponseKey.ENCRYPTING_MESSAGE, user_lang))

    # 1. Get the option (remove 'SendAnon_' prefix)
    option = query_data.replace(f'SendAnon{SEP}', '')
    # 2. Get receiver admin_id using bot username
    bot_username = context.bot.username
    admin_manager = AdminManager()
    admin_id = await admin_manager.get_admin_id_from_bot(bot_username)
    
    if not admin_id:
        await query.message.edit_text(get_response(ResponseKey.ERROR_SENDING_MESSAGE, user_lang))
        logger.error("handle_anonymous_callback: No admin ID found for bot")
        return
    # 3. Get sender's user_id
    sender_user_id = query.from_user.id
    # 4. Get original message_id
    original_message_id = original_sender_message.message_id
    # 5. Get Unix timestamp with nanoseconds
    timestamp_ns = time.time_ns()
    # Construct the callback string for read callback
    raw_read_callback = f"{sender_user_id}{SEP}{original_message_id}{SEP}{timestamp_ns}"
    # Construct the callback string for admin-side
    raw_admin_callback = f"{option}{SEP}{admin_id}{SEP}{sender_user_id}{SEP}{original_message_id}{SEP}{timestamp_ns}"
    # 6. Encrypt the callback string
    encryptor = Encryptor()
    encrypted_read_callback = encryptor.encrypt(raw_read_callback)
    encrypted_admin_callback = encryptor.encrypt(raw_admin_callback)
    # Store the encrypted callback in the database (without last 30 characters)
    read_stored_hash = encrypted_read_callback[:-30]
    read_button_prefix = encrypted_read_callback[:30]
    read_button_suffix = encrypted_read_callback[-30:]
    read_callback = f"{CBD_READ_MESSAGE}{SEP}{read_button_prefix}{SEP}{read_button_suffix}"
    admin_stored_hash = encrypted_admin_callback[:-30]
    admin_button_prefix = encrypted_admin_callback[:30]
    admin_button_suffix = encrypted_admin_callback[-30:]
    block_callback = f"{CBD_ADMIN_BLOCK}{SEP}{admin_button_prefix}{SEP}{admin_button_suffix}"
    #print("Block callback length:", len(block_callback.encode('utf-8')))
    answer_callback = f"{CBD_ADMIN_ANSWER}{SEP}{admin_button_prefix}{SEP}{admin_button_suffix}"
    #print("Answer callback length:", len(answer_callback.encode('utf-8')))
    
    # Store the encrypted message hash
    db_manager = DatabaseManager()
    # Store the year and month the message sent
    year_month = time.strftime("%Y-%m")
    await db_manager.store_partial_hash(admin_button_prefix, admin_stored_hash, 'messages', year_month)
    await db_manager.store_partial_hash(read_button_prefix, read_stored_hash, 'reads')
        
    # Generate admin buttons
    admin_keyboard = [
        [
            InlineKeyboardButton(f"{BTN_EMOJI_READ} Read", callback_data=read_callback),
        ],
        [
            InlineKeyboardButton(f"{BTN_EMOJI_BLOCK} Block", callback_data=block_callback),
            InlineKeyboardButton(f"{BTN_EMOJI_ANSWER} Answer", callback_data=answer_callback)
        ]
    ]
    admin_markup = InlineKeyboardMarkup(admin_keyboard)

    if query_data == CBD_ANON_NO_HISTORY:
        try:
            try:
                # Copy the message to admin
                copied_msg = await original_sender_message.copy(
                    chat_id=admin_id
                )
            except BadRequest as br_e:
                logger.exception(f"Telegram API Error: {str(br_e)}")
                await query.message.edit_text(get_response(ResponseKey.ERROR_SENDING_MESSAGE, user_lang))
                return
            
            try:
                # Send admin controls
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"{BTN_EMOJI_NO_HISTORY}\n🎛️ Admin controls:",
                    reply_markup=admin_markup,
                    reply_to_message_id=copied_msg.message_id,
                    disable_notification=True,
                    parse_mode=ParseMode.HTML
                )
            except Exception as admin_e:
                logger.exception(f"Telegram API Error: {str(admin_e)}")
                raise
            
            # Confirm to user
            await query.message.edit_text(get_response(ResponseKey.MESSAGE_SENT_NO_HISTORY, user_lang))
        except Exception as e:
            logger.exception(f"Error in handle_anonymous_callback (no history): {str(e)}")
            await query.message.edit_text(get_response(ResponseKey.ERROR_SENDING_MESSAGE, user_lang))
        
    elif query_data == CBD_ANON_WITH_HISTORY:
        try:
            # Generate an anonymous ID to let admin track the history with this anonymous user
            sender_user_first_name = query.from_user.first_name
            anon_id = generate_anonymous_id(sender_user_id, sender_user_first_name, with_history=True)
            
            # Copy the message to admin with anonymous ID
            copied_msg = await original_sender_message.copy(
                chat_id=admin_id
            )
            
            try:
                # Send admin controls with anonymous ID
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"{BTN_EMOJI_WITH_HISTORY} {anon_id}\n🎛️ Admin controls:",
                    reply_markup=admin_markup,
                    reply_to_message_id=copied_msg.message_id,
                    disable_notification=True,
                    parse_mode=ParseMode.HTML
                )
            except Exception as admin_e:
                logger.exception(f"Telegram API Error: {str(admin_e)}")
                raise
            
            # Confirm to user
            await query.message.edit_text(get_response(ResponseKey.MESSAGE_SENT_WITH_HISTORY, user_lang))
        except Exception as e:
            logger.exception(f"Error in handle_anonymous_callback (with history): {str(e)}")
            await query.message.edit_text(get_response(ResponseKey.ERROR_SENDING_MESSAGE, user_lang))
        
    elif query_data == CBD_ANON_FORWARD:
        try:
            # Get user's name for forward
            sender_name = f"<code>{query.from_user.first_name} {query.from_user.last_name if query.from_user.last_name else ''}</code>"
            
            # Forward the message to admin
            forwarded_msg = await original_sender_message.forward(admin_id)
            
            try:
                # Send admin controls with user info
                await forwarded_msg.reply_text(
                    f"{BTN_EMOJI_FORWARD} {sender_name}\n🎛️ Admin controls:",
                    reply_markup=admin_markup,
                    disable_notification=True,
                    quote=True,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as admin_e:
                logger.exception(f"Telegram API Error: {str(admin_e)}")
                raise
            
            # Confirm to user
            await query.message.edit_text(get_response(ResponseKey.MESSAGE_FORWARDED, user_lang))
        except Exception as e:
            logger.exception(f"Error in handle_anonymous_callback (forward): {str(e)}")
            await query.message.edit_text(get_response(ResponseKey.ERROR_SENDING_MESSAGE, user_lang))
        
    else:
        # Handle unknown callback data
        await query.message.edit_text(
            text=get_response(ResponseKey.ERROR_SENDING, user_lang)
        )
#endregion Anon CB

#region Read CB
async def handle_read_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Process read callbacks for messages and mark them as read.
    
    Handles the message read status by:
    1. Removing the read button from the message
    2. Decrypting the message details
    3. Sending a read reaction to the original message
    4. Cleaning up the read status data
    
    Args:
        update (Update): The update object containing the callback query
        context (ContextTypes.DEFAULT_TYPE): The context object for the bot
    
    Returns:
        None
    
    Note:
        Uses encrypted message data to maintain sender privacy while
        enabling read status functionality.
    '''
    try:
        query = update.callback_query
        if not query:
            logger.warning("handle_read_callback: No callback query found, returning")
            return
        
        if not query.message or not isinstance(query.message, Message):
            logger.warning("handle_read_callback: No valid message in callback query, returning")
            return
        
        query_data = query.data
        if not query_data:
            logger.warning("handle_read_callback: No callback data found, returning")
            return

        # Get prefix and suffix from callback data
        _, prefix, suffix = query_data.split(SEP)

        # Convert keyboard to list of lists for modification
        if not query.message.reply_markup or not query.message.reply_markup.inline_keyboard:
            logger.warning("handle_read_callback: No reply markup found, returning")
            return
            
        keyboard = list(map(list, query.message.reply_markup.inline_keyboard))
        # Ensure there's a button to remove
        if keyboard and keyboard[0]:
            # Remove the first button from the first row
            keyboard[0].pop(0)

        # Update the message with the modified keyboard
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

        # Get the full hash from database
        db_manager = DatabaseManager()
        full_encrypted_hash = await db_manager.get_full_hash_by_prefix(prefix, suffix, 'reads')
        
        if not full_encrypted_hash:
            return

        # Decrypt the hash to get message details
        encryptor = Encryptor()
        decrypted_data = encryptor.decrypt(full_encrypted_hash)
        sender_user_id, message_id, timestamp = decrypted_data.split(SEP)

        # Convert IDs to integers
        sender_user_id = int(sender_user_id)
        message_id = int(message_id)

        try:
            # Send reaction to mark message as read
            await context.bot.set_message_reaction(
                chat_id=sender_user_id,
                message_id=message_id,
                reaction=[ReactionTypeEmoji(BTN_EMOJI_READ)],
                is_big=False
            )
        except Exception as e:
            logger.exception(e)

        # Delete the hash from database
        await db_manager.remove_partial_hash(prefix, 'reads')

    except Exception as e:
        logger.exception(e)
#endregion Read CB