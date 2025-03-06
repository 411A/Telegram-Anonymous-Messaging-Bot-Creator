from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes
from telegram import Message, InlineKeyboardButton, InlineKeyboardMarkup, ReactionTypeEmoji
from telegram.constants import ParseMode
from utils.responses import get_response, ResponseKey
from utils.db_utils import DatabaseManager, Encryptor, AdminManager
from utils.other_utils import check_language_availability
from configs.constants import (
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
import base64
import hashlib
import random
import string

logger = logging.getLogger(__name__)

#region Helpers
def generate_anonymous_id(user_id: int, user_fname: str = None, with_history: bool = False) -> str:
    '''Generate a unique, hashtag-friendly anonymous ID.'''
    seed = f"{user_id}{user_fname}"
    if not with_history:
        seed = f"{seed}_{int(time.time())}_{random.randint(1000, 9999)}"

    # Generate a SHA-256 hash
    hash_obj = hashlib.sha256(seed.encode()).digest()

    # Encode using base64, ensuring URL-safe and alphanumeric characters
    encoded = base64.urlsafe_b64encode(hash_obj).decode()

    # Remove non-alphanumeric characters and ensure length
    anon_id = ''.join(filter(str.isalnum, encoded))[:10]

    # Ensure the first character is a letter
    if not anon_id[0].isalpha():
        anon_id = random.choice(string.ascii_letters) + anon_id[1:]

    if with_history:
        return f"#{anon_id}"
    return f"{anon_id}"


def generate_inline_buttons_anonymous(user_lang: str) -> InlineKeyboardMarkup:
    '''
    Generates the InlineKeyboardMarkup for the anonymous message.
    '''
    keyboard = [
        [InlineKeyboardButton(get_response(ResponseKey.ANONYMOUS_INLINEBUTTON1, user_lang), callback_data=CBD_ANON_NO_HISTORY)],
        [InlineKeyboardButton(get_response(ResponseKey.ANONYMOUS_INLINEBUTTON2, user_lang), callback_data=CBD_ANON_WITH_HISTORY)],
        [InlineKeyboardButton(get_response(ResponseKey.ANONYMOUS_INLINEBUTTON3, user_lang), callback_data=CBD_ANON_FORWARD)]
    ]
    return InlineKeyboardMarkup(keyboard)


#region Admin
async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''Handle callback queries for admin options (block/answer) efficiently.'''
    query = update.callback_query
    if query is None:
        return

    query_data = query.data
    user_lang = check_language_availability(query.from_user.language_code)

    # Handle cancel reply button click
    if query_data == CBD_ADMIN_CANCEL_ANSWER:
        if 'waiting_reply_for' not in context.user_data:
            await query.answer(get_response(ResponseKey.ADMIN_NO_ONGOING_REPLY, user_lang))
            return

        # Update the wait message text
        await query.message.edit_text(get_response(ResponseKey.ADMIN_CANCELED_REPLY_MANUALLY, user_lang))

        # Clean up the context data
        for key in ['waiting_reply_for', 'original_message_id', 'chat_id']:
            context.user_data.pop(key, None)
        return

    # Check if there's an ongoing answer operation when trying to start a new one
    if query_data == CBD_ADMIN_ANSWER and 'waiting_reply_for' in context.user_data:
        await query.answer(get_response(ResponseKey.ADMIN_ONGOING_REPLY, user_lang), show_alert=True)
        return


    try:
        # Expecting data in format: operation SEP prefix SEP suffix
        operation, prefix, suffix = query_data.split(SEP)

        db_manager = DatabaseManager()  # Ensure this manager uses connection pooling/WAL if needed
        full_encrypted_hash = await db_manager.get_full_hash_by_prefix(prefix, suffix, 'messages')
        encryptor = Encryptor()

        try:
            raw_admin_callback = encryptor.decrypt(full_encrypted_hash)
            # Expecting raw_admin_callback in format: option SEP admin_id SEP sender_user_id SEP original_message_id SEP timestamp
            option, admin_id, sender_user_id, original_message_id, timestamp = raw_admin_callback.split(SEP)
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
            await query.answer(get_response(ResponseKey.ADMIN_UNKNOWN_OPERATION, user_lang), show_alert=True)

    except Exception as db_error:
        logger.exception(f"Database or processing error in callback:\n{db_error}")
        await query.answer(get_response(ResponseKey.ADMIN_DATABASE_ERROR, user_lang), show_alert=True)


async def handle_admin_answer(query: CallbackQuery, admin_id, sender_user_id, original_message_id, context: ContextTypes.DEFAULT_TYPE):
    '''
    Handle the answer option.
    Here you may set up user context data and schedule a reply timeout.
    '''
    # Get user language
    user_lang = query.from_user.language_code or 'en'
    try:
        # Save state in context.user_data for this admin
        context.user_data['waiting_reply_for'] = sender_user_id
        context.user_data['original_message_id'] = original_message_id
        context.user_data['chat_id'] = query.message.chat_id

        # Create cancel button keyboard
        cancel_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_response(ResponseKey.ADMIN_BUTTON_CANCEL_MANUALLY, user_lang), callback_data="CancelReplyAnswer")]
        ])

        # Inform the admin to reply within a specific timeout
        wait_msg = await query.message.reply_to_message.reply_text(
            text=get_response(ResponseKey.ADMIN_REPLY_WAIT, user_lang, minutes=round(ADMIN_REPLY_TIMEOUT / 60)),
            reply_markup=cancel_keyboard,
            quote=True,
            parse_mode=ParseMode.HTML
        )
        context.user_data['wait_msg'] = wait_msg

        # Start a timeout task for cleaning up state after ADMIN_REPLY_TIMEOUT seconds
        asyncio.create_task(reply_timeout_handler(query, context, timeout=ADMIN_REPLY_TIMEOUT))
        # Optionally notify that the admin action is being processed
        await query.answer(get_response(ResponseKey.ADMIN_REPLY_AWAITING, user_lang), show_alert=False)
    except Exception as e:
        logger.exception(f"Error handling admin answer option:\n{e}")
        await query.answer(get_response(ResponseKey.ADMIN_REPLY_ERROR, user_lang), show_alert=True)


async def reply_timeout_handler(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, timeout=ADMIN_REPLY_TIMEOUT):
    '''Cleanup waiting reply state after a timeout.'''
    await asyncio.sleep(timeout)
    user_lang = query.from_user.language_code or 'en'
    # Check if the waiting state still exists (i.e. admin did not reply)
    if 'waiting_reply_for' in context.user_data:
        # Cleanup user state
        context.user_data.pop('waiting_reply_for', None)
        context.user_data.pop('original_message_id', None)
        context.user_data.pop('chat_id', None)
        wait_msg = context.user_data.pop('wait_msg', None)
        if wait_msg:
            try:
                await wait_msg.delete()
            except Exception:
                pass
        # Inform the admin about the timeout
        await query.message.reply_to_message.reply_text(
            text=get_response(ResponseKey.ADMIN_REPLY_TIMEOUT, user_lang),
            quote=True,
            parse_mode=ParseMode.HTML
        )


async def handle_admin_block(query: CallbackQuery, admin_id, context: ContextTypes.DEFAULT_TYPE):
    '''Handle the block option.'''
    user_lang = query.from_user.language_code or 'en'
    try:
        # Get the bot username
        bot_username = context.bot.username
        
        # Check if the message has a reply markup and buttons
        if not query.message.reply_markup or not query.message.reply_markup.inline_keyboard:
            await query.answer(get_response(ResponseKey.ADMIN_INVALID_MESSAGE_DATA, user_lang), show_alert=True)
            return
        
        #! Extract the inline keyboard from the message.
        keyboard = query.message.reply_markup.inline_keyboard

        if len(keyboard) > 1:
            #! First row contains the read button.
            read_callback_data = keyboard[0][0].callback_data
            raw_admin_callback = keyboard[1][0].callback_data
            answer_callback_data = keyboard[1][1].callback_data
        else:
            #! Only one row is present; assume read is not available.
            read_callback_data = None
            #! Expect two buttons: block and answer.
            raw_admin_callback = keyboard[0][0].callback_data
            answer_callback_data = keyboard[0][1].callback_data

        
        if not raw_admin_callback:
            await query.answer(get_response(ResponseKey.ADMIN_INVALID_MESSAGE_DATA, user_lang), show_alert=True)
            return
        
        operation, prefix, suffix = raw_admin_callback.split(SEP)
        
        # Get the full hash and decrypt it to get sender_user_id
        db_manager = DatabaseManager()
        full_encrypted_hash = await db_manager.get_full_hash_by_prefix(prefix, suffix, 'messages')
        encryptor = Encryptor()
        decrypted_data = encryptor.decrypt(full_encrypted_hash)
        option, admin_id, sender_user_id, original_message_id, timestamp = decrypted_data.split(SEP)
        
        # Convert sender_user_id to integer
        sender_user_id = int(sender_user_id)
        
        # Check if user is already blocked
        is_blocked = await db_manager.is_user_blocked(sender_user_id, bot_username)
        
        # Update block status and message
        message_text = query.message.text
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

#region Messages
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''Handle incoming messages for the created bot, implementing admin and anonymous message routing.'''
    logger.debug(f"Received message from user {update.message.from_user.id}")
    db_manager = DatabaseManager()
    # Get user language code
    user_lang = check_language_availability(update.message.from_user.language_code)
    
    # Get bot's username
    bot_username = context.bot.username
    # Get admin manager singleton instance
    admin_manager = AdminManager()
    
    # Get user ID from the message
    user_id = update.message.from_user.id
    if not user_id:
        return
    
    #* Handle admin message
    # Check if sender is admin using admin_manager's method first
    is_admin = await admin_manager.is_admin(user_id, bot_username)
    
    if is_admin:
        # Check if admin is replying to a message and has proper context
        if 'waiting_reply_for' in context.user_data:
            # Route to admin message handler
            try:
                if 'waiting_reply_for' not in context.user_data:
                    await update.message.reply_text(get_response(ResponseKey.ADMIN_MUST_USE_ANSWER_BUTTON, user_lang), parse_mode=ParseMode.HTML)
                    return

                target_user_id = context.user_data['waiting_reply_for']
                original_message_id = context.user_data['original_message_id']

                # 1. Get sender's id
                sender_user_id = update.message.from_user.id
                # 2. Get message_id
                message_id = update.message.id
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

                # Send the admin's reply to the target user
                await update.message.copy(
                    chat_id=target_user_id,
                    reply_to_message_id=original_message_id,
                    reply_markup=user_markup
                )
                await update.message.reply_text(text=get_response(ResponseKey.ADMIN_REPLY_SENT, user_lang), quote=True, parse_mode=ParseMode.HTML)

                # Store the encrypted message hash using DatabaseManager
                db_manager = DatabaseManager()
                await db_manager.store_partial_hash(read_button_prefix, read_stored_hash, 'reads')

                # Delete the wait message
                wait_msg: Message = context.user_data.get('wait_msg')
                if wait_msg:
                    try:
                        await wait_msg.delete()
                    except Exception:
                        # Ignore deletion errors
                        pass
            except Exception:
                await update.message.reply_text(text=get_response(ResponseKey.ADMIN_REPLY_FAILED, user_lang), quote=True, parse_mode=ParseMode.HTML)
            finally:
                # Cleanup all temporary state
                for key in ['waiting_reply_for', 'original_message_id', 'chat_id', 'wait_msg']:
                    context.user_data.pop(key, None)
        else:
            # Inform admin to use the Answer button
            await update.message.reply_text(get_response(ResponseKey.CANT_SEND_TO_SELF, user_lang), parse_mode=ParseMode.HTML)
        return

    # Check if user is blocked
    if await db_manager.is_user_blocked(user_id, bot_username):
        await update.message.reply_text(get_response(ResponseKey.USER_BLOCKED, user_lang), parse_mode=ParseMode.HTML)
        return

    # Handle anonymous message for non-admin users
    keyboard = generate_inline_buttons_anonymous(user_lang)
    await update.message.reply_text(
        text=get_response(ResponseKey.ANONYMOUS_INLINEBUTTON_REPLY_TEXT, user_lang),
        reply_markup=keyboard,
        reply_to_message_id=update.message.message_id,
        parse_mode=ParseMode.HTML
    )

#region Anon CB
async def handle_anonymous_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''Handle callback queries for anonymous message sending options.'''

    query = update.callback_query
    # Rest of the existing callback handling code
    query_data = query.data
    user_lang = check_language_availability(query.from_user.language_code)
    
    # Show encryption status message to user
    await query.message.edit_text(get_response(ResponseKey.ENCRYPTING_MESSAGE, user_lang))

    original_sender_message: Message = query.message.reply_to_message

    # 1. Get the option (remove 'SendAnon_' prefix)
    option = query.data.replace(f'SendAnon{SEP}', '')
    # 2. Get receiver admin_id using bot username
    bot_username = context.bot.username
    admin_manager = AdminManager()
    admin_id = await admin_manager.get_admin_id_from_bot(bot_username)
    # 3. Get sender's user_id
    sender_user_id = query.from_user.id
    # 4. Get original message_id
    original_message_id = query.message.reply_to_message.message_id
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
    
    # Store the encrypted message hash using DatabaseManager
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
            # Copy the message to admin
            copied_msg = await original_sender_message.copy(
                chat_id=admin_id
            )
            
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

#region Read CB
async def handle_read_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''Handle read callback for messages, marking them as read with a reaction.'''
    try:
        query = update.callback_query
        query_data = query.data

        # Get prefix and suffix from callback data
        _, prefix, suffix = query_data.split(SEP)

        # Convert keyboard to list of lists for modification
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
