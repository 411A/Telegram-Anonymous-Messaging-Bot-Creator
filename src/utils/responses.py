from enum import Enum
from dataclasses import dataclass
from typing import Union, List, Dict, Any
from configs.settings import (
    BTN_EMOJI_NO_HISTORY, BTN_EMOJI_WITH_HISTORY, BTN_EMOJI_FORWARD,
    BTN_EMOJI_BLOCK, BTN_EMOJI_UNBLOCK,
    PROJECT_GITHUB_URL, DEVELOPER_CONTACT_URL
)

# Use Union to support both string responses and list/dict responses.
@dataclass(frozen=True)
class Response:
    en: Union[str, List[Dict[str, Any]]]
    fa: Union[str, List[Dict[str, Any]]]

class ResponseKey(Enum):
    INVALID_TOKEN = Response(
        en="⚠️ Invalid bot token. Please register using a valid token.",
        fa="⚠️ توکن ربات نامعتبر است. لطفاً با استفاده از توکن صحیح ثبت کنید."
    )

    WAIT_REGISTERING_BOT = Response(
        en="⏳ Please wait while the bot is being registered...",
        fa="⏳ لطفاً منتظر بمانید تا ربات ثبت شود..."
    )
    ENCRYPTING_MESSAGE = Response(
        en="🤖🔒 Encrypting your message and preparing it for sending...",
        fa="🤖🔒 در حال رمزگذاری پیام شما و آماده‌سازی جهت ارسال..."
    )
    USER_BLOCKED = Response(
        en="🤖🛑 You have been blocked by the admin.",
        fa="🤖🛑 ادمین شما را بلاک کرده است."
    )
    MESSAGE_SENT_NO_HISTORY = Response(
        en=f"🤖✅ {BTN_EMOJI_NO_HISTORY}\nMessage sent anonymously without history!",
        fa=f"🤖✅ {BTN_EMOJI_NO_HISTORY}\nپیام به صورت ناشناس و بدون تاریخچه ارسال شد!"
    )
    MESSAGE_SENT_WITH_HISTORY = Response(
        en=f"🤖✅ {BTN_EMOJI_WITH_HISTORY}\nMessage sent anonymously with history!",
        fa=f"🤖✅ {BTN_EMOJI_WITH_HISTORY}\nپیام به صورت ناشناس با تاریخچه ارسال شد!"
    )
    MESSAGE_FORWARDED = Response(
        en=f"🤖✅ {BTN_EMOJI_FORWARD}\nMessage forwarded to admin!",
        fa=f"🤖✅ {BTN_EMOJI_FORWARD}\nپیام به ادمین فوروارد شد!"
    )
    ERROR_SENDING_MESSAGE = Response(
        en="🤖⚠️ Error sending message. Please try again.",
        fa="🤖⚠️ خطا در ارسال پیام. لطفاً دوباره تلاش کنید."
    )
    WELCOME = Response(
        en=("Welcome!\n"
            "Please send your bot token to create a new anonymous messaging bot.\n"
            "Use the format:\n<code>/register BOT_TOKEN</code>\n"
            "❗ Note: The person who provides the bot token will become the bot's admin. Do not share your token with anyone.\n"
            "To disable your bot, reply to the pinned message with /revoke.\n\n"
            "<a href=\"https://rose-charming-mouse-358.mypinata.cloud/ipfs/bafybeifdj5jccidlti3illgucltkzhdqfhzuh3edvb2ksj6f34fqw6jm34\">📺 Bot Creation Guide Video</a>\n"
            "<blockquote expandable>"
            "📝 <b>How to Create a Bot</b>\n"
            "1. <b><a href=\"https://t.me/BotFather\">Open & Start BotFather</a></b>\n"
            "2. From the bottom-left, tap the ≡ menu and select <code>/newbot</code> or type and send it.\n"
            "3. Choose a name for your bot.\n"
            "4. Choose a unique username for your bot.\n"
            "5. If successful, you'll see a \"Done!\" message. Tap the token shown after \"HTTP API:\" to copy it.\n"
            "6. <b><a href=\"https://t.me/HidEgoBot\">Open HidEgo</a></b> and start.\n"
            "7. Type <code>/register</code>, paste your copied token, and send it.\n"
            "8. If successful, you'll see a button with 🟢. Click it and ask someone to message your anonymous bot. Done!\n"
            "</blockquote>"
        ),
        fa=("خوش آمدید!\n"
            "لطفاً توکن ربات خود را برای ایجاد یک ربات پیام ناشناس جدید ارسال کنید.\n"
            "فرمت دستور:\n<code>/register BOT_TOKEN</code>\n"
            "❗ توجه: هرکسی که توکن ربات را ارائه دهد، به عنوان مدیر آن ربات در نظر گرفته می‌شود. توکن خود را با هیچ‌کس به اشتراک نگذارید.\n"
            "برای غیرفعال‌سازی ربات، به پیام پین‌شده ریپلای کرده و /revoke را ارسال کنید.\n\n"
            "<a href=\"https://rose-charming-mouse-358.mypinata.cloud/ipfs/bafybeifdj5jccidlti3illgucltkzhdqfhzuh3edvb2ksj6f34fqw6jm34\">📺 راهنمای ویدیویی ساخت ربات</a>\n"
            "<blockquote expandable>"
            "📝 <b>راهنمای متنی ساخت ربات</b>\n"
            "1. <b><a href=\"https://t.me/BotFather\">باز کردن و Start کردن BotFather</a></b>\n"
            "2. از پایین سمت چپ، روی منوی ≡ بزنید و <code>/newbot</code> را انتخاب کنید یا تایپ کرده و ارسال کنید.\n"
            "3. نامی برای ربات خود انتخاب کنید.\n"
            "4. یک نام کاربری منحصر‌به‌فرد برای ربات خود انتخاب کنید.\n"
            "5. در صورت موفقیت، پیام \"Done!\" نمایش داده می‌شود. روی توکنی که پس از \"HTTP API:\" نشان داده شده بزنید تا کپی شود.\n"
            "6. <b><a href=\"https://t.me/HidEgoBot\">باز کردن و استارت کردن HidEgoBot</a></b>\n"
            "7. دستور <code>/register</code> را تایپ کنید و با یک فاصله، توکن کپی‌شده را الصاق و ارسال کنید.\n"
            "8. در صورت موفقیت، دکمه‌ای با 🟢 نمایش داده می‌شود. روی آن بزنید و از کسی بخواهید به ربات ناشناس شما پیام بفرستد. تمام!\n"
            "</blockquote>"
        )
    )
    PROVIDE_TOKEN = Response(
        en="Please provide a bot token:\n<code>/register BOT_TOKEN</code>",
        fa="لطفاً توکن ربات را وارد کنید:\n<code>/register BOT_TOKEN</code>"
    )
    ALREADY_REGISTERED = Response(
        en="This bot is already registered!",
        fa="این ربات قبلاً ثبت شده است!"
    )
    ADMIN_REGISTERED = Response(
        en="You have been registered as an admin.",
        fa="شما به عنوان ادمین ثبت شده‌اید."
    )
    REVOKE_INSTRUCTIONS = Response(
        en=("Please reply to the pinned message to revoke access.\n"
            "⚠️ Note that once revoked, users will not be able to send you messages until you provide a new token!\n"
            "Old buttons may also stop working."),
        fa=("لطفاً برای لغو دسترسی، به پیام پین‌شده پاسخ دهید.\n"
            "⚠️ توجه داشته باشید که پس از لغو، کاربران تا زمانی که توکن جدید دریافت نکنند، دیگر نمی‌توانند برای شما پیام ارسال کنند!\n"
            "دکمه‌های قدیمی نیز ممکن است کار نکنند.")
    )
    INVALID_PINNED_MESSAGE = Response(
        en="Invalid pinned message format.",
        fa="فرمت پیام پین شده نامعتبر است."
    )
    REVOKE_SUCCESS = Response(
        en="⛓️‍💥 Bot access revoked successfully.",
        fa="⛓️‍💥 دسترسی ربات با موفقیت لغو شد."
    )
    REVOKE_ERROR = Response(
        en="Error revoking bot access.",
        fa="خطا در لغو دسترسی ربات."
    )
    REVOKE_ERROR_DETAIL = Response(
        en="Error revoking bot access:\n<code>{error}</code>",
        fa="خطا در لغو دسترسی ربات:\n<code>{error}</code>"
    )
    ALREADY_ADMIN = Response(
        en="You are already registered as an admin.",
        fa="شما قبلاً به عنوان ادمین ثبت شده‌اید."
    )
    BOT_REGISTERED_SUCCESS = Response(
        en="Successfully registered bot @{username}!\nToken:\n<code>{token}</code>\nTo start receiving messages, you need to launch the bot yourself. Click the button below.",
        fa="ربات @{username} با موفقیت ثبت شد!\nToken:\n<code>{token}</code>\nبرای دریافت پیام‌ها، ابتدا باید خودتان ربات را راه‌اندازی کنید. روی دکمه زیر کلیک کنید."
    )
    BOT_REGISTERED_SUCCESS_BUTTON_TEXT = Response(
        en="🟢 Start Using",
        fa="🟢 شروع استفاده"
    )
    CANT_SEND_TO_SELF = Response(
        en="You cannot send a message to yourself; please click the answer button and then reply.",
        fa="شما نمی‌توانید به خودتان پیام ارسال کنید؛ لطفاً روی دکمه پاسخ کلیک کرده و سپس پیام خود را ارسال کنید."
    )
    ERROR_SENDING = Response(
        en="🤖 Error sending your message",
        fa="🤖 خطا در ارسال پیام"
    )
    ANONYMOUS_INLINEBUTTON1 = Response(
        en=f"{BTN_EMOJI_NO_HISTORY} Anonymous without history",
        fa=f"{BTN_EMOJI_NO_HISTORY} ناشناس بدون تاریخچه"
    )
    ANONYMOUS_INLINEBUTTON2 = Response(
        en=f"{BTN_EMOJI_WITH_HISTORY} Anonymous with history",
        fa=f"{BTN_EMOJI_WITH_HISTORY} ناشناس با تاریخچه"
    )
    ANONYMOUS_INLINEBUTTON3 = Response(
        en=f"{BTN_EMOJI_FORWARD} Forward",
        fa=f"{BTN_EMOJI_FORWARD} فوروارد"
    )
    ANONYMOUS_INLINEBUTTON_REPLY_TEXT = Response(
        en="📝 Choose how to send your message:",
        fa="📝 انتخاب کنید پیامتان چطور ارسال شود:"
    )
    ADMIN_INVALID_MESSAGE_DATA = Response(
        en="Error: Invalid message data",
        fa="خطا: داده‌های پیام نامعتبر است"
    )
    ADMIN_UNKNOWN_OPERATION = Response(
        en="Error: Unknown operation",
        fa="خطا: عملیات ناشناخته"
    )
    ADMIN_DATABASE_ERROR = Response(
        en="Error: Database operation failed",
        fa="خطا: عملیات پایگاه داده ناموفق بود"
    )
    ADMIN_ONGOING_REPLY = Response(
        en="⏳ You have an ongoing reply operation! Please cancel it first.",
        fa="⏳ شما یک عملیات پاسخ در حال انجام دارید! لطفاً ابتدا آن را لغو کنید."
    )
    ADMIN_BUTTON_CANCEL_MANUALLY = Response(
        en="❌ Cancel Reply",
        fa="❌ لغو پاسخ"
    )
    ADMIN_CANCELED_REPLY_MANUALLY = Response(
        en="❌ Reply canceled by you.",
        fa="❌ پاسخ توسط شما لغو شد."
    )
    ADMIN_REPLY_WAIT = Response(
        en="⏳ Send your reply message within {minutes} minutes...",
        fa="⏳ پاسخ خود را ظرف {minutes} دقیقه ارسال کنید..."
    )
    ADMIN_REPLY_AWAITING = Response(
        en="Awaiting your reply...",
        fa="در انتظار پاسخ شما..."
    )
    ADMIN_REPLY_ERROR = Response(
        en="Error processing your reply request.",
        fa="خطا در پردازش درخواست پاسخ شما."
    )
    ADMIN_REPLY_TIMEOUT = Response(
        en="⚠️ Reply timeout. Please use the Answer button again.",
        fa="⚠️ زمان پاسخ به پایان رسید. لطفاً دوباره از دکمه پاسخ استفاده کنید."
    )
    ADMIN_MUST_USE_ANSWER_BUTTON = Response(
        en="❌ You must use the Answer button to reply to messages.",
        fa="❌ برای پاسخ به پیام‌ها باید از دکمه پاسخ استفاده کنید."
    )
    ADMIN_REPLY_SENT = Response(
        en="✅ Reply sent successfully!",
        fa="✅ پاسخ با موفقیت ارسال شد!"
    )
    ADMIN_REPLY_FAILED = Response(
        en="❌ Failed to send reply!",
        fa="❌ ارسال پاسخ ناموفق بود!"
    )
    ADMIN_USER_BLOCKED = Response(
        en=f"{BTN_EMOJI_BLOCK} User blocked successfully!",
        fa=f"{BTN_EMOJI_BLOCK} کاربر با موفقیت بلاک شد!"
    )
    ADMIN_USER_UNBLOCKED = Response(
        en=f"{BTN_EMOJI_UNBLOCK} User unblocked successfully!",
        fa=f"{BTN_EMOJI_UNBLOCK} کاربر با موفقیت آنبلاک شد!"
    )
    ADMIN_BLOCK_ERROR = Response(
        en="Failed to block user",
        fa="بلاک کردن کاربر ناموفق بود"
    )
    ADMIN_UNBLOCK_ERROR = Response(
        en="Failed to unblock user",
        fa="آنبلاک کردن کاربر ناموفق بود"
    )
    ADMIN_BLOCK_PROCESS_ERROR = Response(
        en="Error processing block request",
        fa="خطا در پردازش درخواست بلاک"
    )
    CREATED_BOT_SHORT_DESCRIPTION = Response(
        en="🤖 Secure & anonymous messaging bot created by @{BOT_CREATOR_USERNAME}",
        fa="🤖 ربات پیام‌رسان امن و ناشناس ایجاد شده توسط @{BOT_CREATOR_USERNAME}"
    )
    MAIN_BOT_COMMANDS = Response(
        en=[
            {
                'command': 'start',
                'description': '🔰 Guide'
            },
            {
                'command': 'register',
                'description': '🔮 Register a new bot'
            },
            {
                'command': 'revoke',
                'description': "⛓️‍💥 Disable running bot"
            },
            {
                'command': 'safetycheck',
                'description': "🛡️ Check the bot's safety"
            },
            {
                'command': 'privacy',
                'description': "🔏 Privacy Policy"
            },
            {
                'command': 'about',
                'description': "👨🏻‍💻 About Developer"
            }
        ],
        fa=[
            {
                'command': 'start',
                'description': '🔰 راهنما'
            },
            {
                'command': 'register',
                'description': '🔮 ثبت یک ربات جدید'
            },
            {
                'command': 'revoke',
                'description': "⛓️‍💥 غیرفعال‌سازی ربات درحال اجرا"
            },
            {
                'command': 'safetycheck',
                'description': "🛡️ چک‌کردن امنیت ربات"
            },
            {
                'command': 'privacy',
                'description': "🔏 سیاست حفظ حریم خصوصی"
            },
            {
                'command': 'about',
                'description': "👨🏻‍💻 درباره توسعه‌دهنده"
            }
        ]
    )
    BOT_NAME = Response(
        en='HidEgo | Anonymous messaging',
        fa='ربات‌سازِ پیام ناشناس HidEgo'
    )
    BOT_SHORT_DESCRIPTION = Response(
        en='Fully open source and secure anonymous messaging bot creator',
        fa='ربات‌سازِ پیام ناشناس، کاملاً متن‌باز و امن'
    )

    BOT_DESCRIPTION = Response(
        en="""🔸 Create your own unique anonymous messaging bot.
🔸 Send anonymous messages securely.
🔸 Manage message history easily.
🔸 Use interactive buttons for quick actions.
🔸 Open-source and transparent.
🔸 Verify safety with /safetycheck.""",
        fa="""🔸 ایجاد رباتِ اختصاصی پیام ناشناس برای شما.
🔸 ارسال پیام‌های ناشناس ایمن.
🔸 مدیریت آسان تاریخچه پیام‌ها.
🔸 استفاده از دکمه‌های تعاملی برای اقدامات سریع.
🔸 متن‌باز و شفاف.
🔸 بررسی امنیت با /safetycheck."""
)
    CREATED_BOT_COMMANDS = Response(
        en=[
            {
                'command': 'start',
                'description': '🔰 Guide'
            },
            {
                'command': 'privacy',
                'description': '🔏 Privacy Policy'
            },
            {
                'command': 'safetycheck',
                'description': "🛡️ Check the bot's safety"
            }
        ],
        fa=[
            {
                'command': 'start',
                'description': '🔰 راهنما'
            },
            {
                'command': 'privacy',
                'description': '🔏 سیاست حفظ حریم خصوصی'
            },
            {
                'command': 'safetycheck',
                'description': "🛡️ چک‌کردن امنیت ربات"
            }
        ]
    )
    START_COMMAND = Response(
        en='''👋 Welcome!
This bot offers secure, anonymous messaging, created by @{BOT_CREATOR_USERNAME}.
Please use it respectfully and kindly.
The developer isn't responsible for messages from anonymous users and cannot identify them.
Users can contact the admin in three ways:''' + f'''
1️⃣ {BTN_EMOJI_NO_HISTORY} <b>Anonymous without history</b>
2️⃣ {BTN_EMOJI_WITH_HISTORY} <b>Anonymous with history</b>
3️⃣ {BTN_EMOJI_FORWARD} <b>Forward</b>

<b>Description</b>:<blockquote expandable>
1️⃣ {BTN_EMOJI_NO_HISTORY} <b>Anonymous without history</b>
• Each message is sent completely anonymously.
• The admin cannot identify you or link your messages together.
• Best for one-time messages.

2️⃣ {BTN_EMOJI_WITH_HISTORY} <b>Anonymous with history</b>
• You receive a consistent anonymous ID (generated using irreversible encryption of your first name; changing your first name will alter your ID).
• The admin cannot identify you but can follow your conversation.
• Ideal for ongoing discussions.

3️⃣ {BTN_EMOJI_FORWARD} <b>Forward</b>
• Your message is forwarded directly to the admin.
• The admin can view your profile (if <i>Forwarded Messages</i> is set to <i>Everybody</i> in your settings).
• Suitable for direct communication.</blockquote>

To start, simply send your message and select your preferred mode.''',
        fa='''👋 خوش آمدید! این ربات امکان ارسال پیام‌های امن و ناشناس را فراهم می‌کند و توسط @{BOT_CREATOR_USERNAME} ایجاد شده است.
لطفاً از این ربات به صورت مسئولانه و محترمانه استفاده کنید.
توسعه‌دهنده یا ربات هیچ مسئولیتی در قبال پیام‌هایی که ممکن است از کاربران ناشناس دریافت کنید، ندارد.
توسعه‌دهنده قادر به شناسایی هویت کاربران نیست.
به‌عنوانِ کاربر، شما می‌توانید به سه روش مختلف با ادمین ارتباط برقرار کنید:''' + f'''
1️⃣ {BTN_EMOJI_NO_HISTORY} <b>ناشناس بدون تاریخچه</b>
2️⃣ {BTN_EMOJI_WITH_HISTORY} <b>ناشناس با تاریخچه</b>
3️⃣ {BTN_EMOJI_FORWARD} <b>ارسال مستقیم</b>

<b>توضیحات</b>:<blockquote expandable>
1️⃣ {BTN_EMOJI_NO_HISTORY} <b>ناشناس بدون تاریخچه</b>
• هر پیام به‌صورت کاملاً ناشناس ارسال خواهد شد.
• ادمین نمی‌تواند شما را شناسایی کند یا پیام‌های شما را به هم پیوند دهد.
• مناسب برای پیام‌های یک‌بار مصرف.

2️⃣ {BTN_EMOJI_WITH_HISTORY} <b>ناشناس با تاریخچه</b>
• شما یک شناسه ناشناس ثابت دریافت می‌کنید (که با استفاده از رمزگذاری غیرقابل برگشت از نام کوچک شما تولید می‌شود؛ تغییر نام کوچک شما باعث تغییر شناسه می‌شود).
• ادمین نمی‌تواند شما را شناسایی کند، اما می‌تواند مکالمه شما را دنبال کند.
• مناسب برای گفتگوهای ادامه‌دار.

3️⃣ {BTN_EMOJI_FORWARD} <b>ارسال مستقیم</b>
• پیام شما مستقیماً به ادمین ارسال می‌شود.
• ادمین می‌تواند پروفایل شما را مشاهده کند (در صورتی که تنظیمات <i>Forwarded Messages</i> روی <i>Everybody</i> قرار داشته باشد).
• مناسب برای ارتباط مستقیم.</blockquote>

برای شروع، کافی است پیام خود را ارسال کرده و روش دلخواه خود را انتخاب کنید.'''
    )
    PRIVACY_COMMAND = Response(
        en=f'''💽 <b>What Data We Store</b>:<blockquote expandable>
This bot is fully open-source, and you can view its source code <a href="{PROJECT_GITHUB_URL}">here</a>.
You can check the bot's safety using the /safetycheck command.
We do not store messages or their relationships.
All data is encrypted with a strong master password and stored with restricted access.
Some data is only completely hashed upon user interactions (e.g., via callbacks), and even the admin cannot access the user's identities.

🔸 <b>Admin-Side</b>:
• Encrypted admin ID 
• Encrypted bot username
• Encrypted bot token

🔸 <b>User-Side</b>:
• Encrypted user ID (only a portion of the encrypted hash is stored; decryption occurs when the user provides the callback data)</blockquote>

🔎 <b>How We Collect It</b>:
• Data is securely collected directly from Telegram servers through user interactions with our bot (e.g., when a user sends a message).
• The data is encrypted and split into two parts: one part is stored in the database, and the other part is sent by users. Without the user-provided part, decryption is impossible.

🧑‍💻 <b>What We Use Data For</b>:
• To send messages between the user and the admin securely and anonymously.''',
        fa=f'''💽 <b>داده‌هایی که ذخیره می‌کنیم</b>:<blockquote expandable>
این ربات کاملاً متن‌باز است و شما می‌توانید کد منبع آن را <a href="{PROJECT_GITHUB_URL}">اینجا</a> مشاهده کنید.
شما می‌توانید امنیت ربات را با دستور /safetycheck چک کنید.
ما پیام‌ها یا روابط آن‌ها را ذخیره نمی‌کنیم.
تمام داده‌ها با یک رمز عبور اصلی قوی رمزگذاری شده و با دسترسی محدود ذخیره می‌شوند.
برخی داده‌ها فقط پس از تعاملات کاربر (مثلاً از طریق بازخوردها) به طور کامل هش می‌شوند و حتی ادمین نمی‌تواند به هویت کاربران دسترسی پیدا کند.

🔸 <b>سمت ادمین</b>:
• شناسه ادمین رمزگذاری‌شده  
• نام کاربری ربات رمزگذاری‌شده
• توکن ربات رمزگذاری‌شده

🔸 <b>سمت کاربر</b>:
• شناسه کاربر رمزگذاری‌شده (فقط بخشی از هش رمزگذاری‌شده ذخیره می‌شود؛ رمزگشایی زمانی انجام می‌شود که کاربر داده‌های بازخورد را ارائه دهد)</blockquote>

🔎 <b>چطور داده‌ها را جمع‌آوری می‌کنیم</b>:
• داده‌ها به صورت امن و مستقیم از سرورهای تلگرام از طریق تعاملات کاربر با ربات ما جمع‌آوری می‌شوند (مثلاً وقتی کاربر پیامی ارسال می‌کند).
• داده‌ها رمزگذاری شده و به دو بخش تقسیم می‌شوند: یک بخش در پایگاه داده ذخیره می‌شود و بخش دیگر توسط کاربر ارائه می‌شود. بدون بخش ارائه‌شده، رمزگشایی غیرممکن است.

🧑‍💻 <b>از داده‌ها برای چه استفاده می‌کنیم</b>:
• برای ارسال پیام‌ها بین کاربر و ادمین به صورت امن و ناشناس.''',
    )

    ABOUT_COMMAND = Response(
        en=f'''🤖 <b>About the Bot</b><blockquote expandable>
This bot is fully open-source, and its source code is available on <a href="{PROJECT_GITHUB_URL}">GitHub</a>.  
It is designed as a <b>zero-knowledge anonymous messaging solution</b>, meaning that no one - not even the developer - can ever access the identity of users or admins.
Only the minimal encrypted data required to deliver messages is stored, using the ChaCha20-Poly1305 encryption algorithm for confidentiality and authenticity.
The encrypted data is split into two independent parts through <b>dual control</b>: one part is stored in the database, while the other is held by the user or admin.
Both parts must be combined temporarily to decrypt a message - and this combination occurs for each individual message.
Since the bot is open-source and offers a /safetycheck command, you can verify that what you're using matches the public source code - with no hidden data logging.
When you use /safetycheck, the bot fetches the currently running source code (it can't be anything else!), then downloads the code from GitHub, hashes both versions, and compares them. If they match (identical), you know for sure there's no trickery involved.
When you own your bot, you own your data. If you revoke your bot from the bot creator or change your bot token, not even the developer can retrieve it.  
And while using it? Still impossible - the code (which you can review yourself) simply doesn't have that functionality.</blockquote>

👨🏻‍💻 <b>About the Developer</b>  
This bot is developed by <a href="https://abditory.vercel.app">Ali Abdi</a>.  
📬 <a href="{DEVELOPER_CONTACT_URL}">Contact the developer</a> for any questions, suggestions, or issues.  
📢 You can also join the <a href="https://t.me/TechNila">developer's channel</a> for bot news, tech updates, and science content.  

💙 If you'd like to support the project, you can donate via the TON crypto button below. Your donations help keep the bot free and fund future improvements.
''',
        fa=f'''🤖 <b>دربارهٔ ربات</b><blockquote expandable>
این ربات به‌طور کامل متن‌باز است و کد منبع آن در <a href="{PROJECT_GITHUB_URL}">GitHub</a> در دسترس می‌باشد.
این ربات به‌عنوان یک <b>راهکار پیام‌رسانی ناشناس با دانش صفر</b> طراحی شده است، به این معنی که هیچ‌کس - حتی توسعه‌دهنده - نمی‌تواند به هویت کاربران یا مدیران دسترسی پیدا کند.
فقط حداقل داده‌های رمزنگاری شده مورد نیاز برای تحویل پیام‌ها ذخیره می‌شود، که برای حفظ محرمانگی و صحت از الگوریتم رمزنگاری ChaCha20-Poly1305 استفاده می‌شود.
داده‌های رمزنگاری شده به دو بخش مستقل تقسیم می‌شوند از طریق <b>کنترل دوگانه</b>؛ یک بخش در پایگاه داده ذخیره می‌شود و بخش دیگر نزد کاربر یا مدیر نگه داشته می‌شود.
برای رمزگشایی هر پیام، هر دو بخش باید به‌صورت موقت ترکیب شوند و این ترکیب فقط برای همان پیام خاص انجام می‌شود.
از آنجا که ربات متن‌باز است و دستور /safetycheck را ارائه می‌دهد، می‌توانید بررسی کنید که نسخه‌ای که استفاده می‌کنید دقیقاً با کد منبع عمومی مطابقت دارد - بدون هیچ‌گونه ثبت داده مخفی.
وقتی دستور /safetycheck را اجرا می‌کنید، ربات کد منبع در حال اجرا را می‌گیرد (و نمی‌تواند چیز دیگری باشد!)، سپس کد را از GitHub دانلود می‌کند، هر دو نسخه را هش می‌کند و با هم مقایسه می‌کند. اگر هش‌ها برابر باشند (کاملاً یکسان)، مطمئن باشید هیچ تقلبی وجود ندارد.
وقتی مالک ربات خود باشید، مالک داده‌های خود نیز هستید. اگر دسترسی ربات را از سازندهٔ آن لغو کنید یا توکن ربات را تغییر دهید، حتی توسعه‌دهنده هم نمی‌تواند به داده‌ها دسترسی پیدا کند.
و هنگام استفاده؟ همچنان غیرممکن است - کد (که می‌توانید خودتان بررسی کنید) اصلاً چنین قابلیتی ندارد.</blockquote>

👨🏻‍💻 <b>دربارهٔ توسعه‌دهنده</b>
این ربات توسط <a href="https://abditory.vercel.app">علی عبدی</a> توسعه داده شده است.
📬 برای هرگونه سؤال، پیشنهاد یا گزارش مشکل می‌توانید از طریق <a href="{DEVELOPER_CONTACT_URL}">ارتباط با توسعه‌دهنده</a> اقدام کنید.
📢 همچنین می‌توانید به <a href="https://t.me/TechNila">کانال توسعه‌دهنده</a> بپیوندید تا از اخبار ربات، به‌روزرسانی‌های فناوری و محتوای علمی مطلع شوید.

💙 اگر مایل به حمایت از این پروژه هستید، می‌توانید از طریق دکمهٔ رمزارز TON در پایین صفحه کمک مالی کنید. کمک‌های شما به حفظ رایگان بودن ربات و تأمین هزینهٔ بهبودهای آینده کمک خواهد کرد.
'''
    )

    FETCHING_LOCAL_FILES = Response(
        en='🔄 Fetching and hashing local files...',
        fa='🔄 در حال دریافت و هَش‌کردن فایل‌های محلی...'
    )

    LOCAL_FILES_HASHED = Response(
        en='✅ Local files hashed: <b>{0}</b>',
        fa='✅ فایل‌های محلی هَش شدند: <b>{0}</b>'
    )

    FETCHING_GITHUB_FILES = Response(
        en='🔄 Fetching and hashing GitHub files...',
        fa='🔄 در حال دریافت و هَش‌کردن فایل‌های گیت‌هاب...'
    )

    GITHUB_FILES_HASHED = Response(
        en='✅ <b><a href="{PROJECT_GITHUB_URL}">GitHub</a></b> files hashed: <b>{number}</b>',
        fa='✅ فایل‌های <b><a href="{PROJECT_GITHUB_URL}">گیت‌هاب</a></b> هَش شدند: <b>{number}</b>'
    )

    SOURCE_IDENTICAL = Response(
        en='✅ The local source code is <b>IDENTICAL</b> to GitHub!',
        fa='✅ کد منبع محلی با گیت‌هاب <b>یکسان</b> است!'
    )

    SOURCE_DIFFERS = Response(
        en='❌ The local source code differs from GitHub!',
        fa='❌ کد منبع محلی با گیت‌هاب متفاوت است!'
    )

    EXTRA_FILE = Response(
        en='🛑 Extra file: <b>{0}</b>',
        fa='🛑 فایل اضافه: <b>{0}</b>'
    )

    MODIFIED_FILE = Response(
        en='⚠️ Modified file: <b>{0}</b>',
        fa='⚠️ فایل تغییر یافته: <b>{0}</b>'
    )

    MISSING_FILE = Response(
        en='🛑 Missing file: <b>{0}</b>',
        fa='🛑 فایل مفقود: <b>{0}</b>'
    )
    SAFETYCHECK_COMMAND = Response(
        en='''🔍 <b>Safety Check</b>
This bot is open-source and follows strict privacy standards.
You can review the source code <a href="{PROJECT_GITHUB_URL}">here</a>.
No private messages or user data are stored.''' + f'''You can contact developer <a href="{DEVELOPER_CONTACT_URL}">here</a>.
''',
        fa='''🔍 <b>بررسی امنیت</b>
این ربات متن‌باز است و از استانداردهای سختگیرانه حریم خصوصی پیروی می‌کند.
می‌توانید کد منبع را <a href="{PROJECT_GITHUB_URL}">اینجا</a> بررسی کنید.
هیچ پیام خصوصی یا اطلاعات کاربری ذخیره نمی‌شود.''' + f'''می‌توانید از <a href="{DEVELOPER_CONTACT_URL}">اینجا</a> به توسعه‌دهنده پیام دهید.''',
    )
    SAFETYCHECK_CAPTION = Response(
    en='''🛡️ <b>Safety Check Results</b>:\n
Script running since:\n{RUNNING_SCRIPT_SINCE} UTC\n
{GITHUB_CHECK_RESULTS}''',
    fa='''🛡️ <b>نتایج بررسی امنیت</b>:\n
اسکریپت از زمان زیر در حال اجرا است:\n{RUNNING_SCRIPT_SINCE} UTC\n
{GITHUB_CHECK_RESULTS}'''
    )
    SAFETYCHECK_ERROR = Response(
        en='⚠️ Failed to send safety check results. Please try again later.',
        fa='⚠️ خطا در ارسال نتایج بررسی امنیت. لطفاً دوباره تلاش کنید.'
    )
    SAFETYCHECK_FAILED = Response(
        en='❌ Safety check failed. Please contact the administrator.',
        fa='❌ بررسی امنیت ناموفق بود. لطفاً با ادمین تماس بگیرید.'
    )


def get_response(key: ResponseKey, lang: str = 'en', **kwargs: Any) -> Union[str, List[Dict[str, Any]]]:
    """
    Retrieve a formatted response message.

    Args:
        key: A member of ResponseKey enum.
        lang: Language code ('en' or 'fa').
        **kwargs: Formatting parameters for the message.

    Returns:
        The formatted message string (or original value for non-string responses).
    """
    response_obj = key.value
    message = response_obj.en if lang == 'en' else response_obj.fa
    if isinstance(message, str):
        return message.format(**kwargs) if kwargs else message
    return message
