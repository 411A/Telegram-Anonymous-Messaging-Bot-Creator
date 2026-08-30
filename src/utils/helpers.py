"""Utility functions for the application."""

import base64
import hashlib
import random
import re
import string
import time
from typing import cast

from configs.settings import AVAILABLE_LANGUAGES_LIST, AVAILABLE_LANGUAGES_LITERAL


def extract_bot_token(text: str) -> str:
    """Extract a valid bot token from text using regex.

    Args:
        text (str): The text containing the bot token.

    Returns:
        str: The extracted bot token if found, empty string otherwise.
    """
    # Pattern matches: digits, followed by ':', followed by allowed chars
    # Stops at first invalid character
    pattern = r'\d+:[A-Za-z0-9_-]+'
    match = re.search(pattern, text)
    return match.group(0) if match else ''


def shorten_token(token: str) -> str:
    """Return the token in a shortened format: first 3 chars, '…', last 3 chars."""
    if len(token) <= 6:
        return token
    return f"{token[:3]}…{token[-3:]}"


def check_language_availability(language_code: str | None) -> AVAILABLE_LANGUAGES_LITERAL:
    """Validate a language code against the supported languages list.

    Args:
        language_code: The language code to check (may be None or unsupported).

    Returns:
        The validated language code; falls back to 'en' when unsupported.
    """
    return cast(AVAILABLE_LANGUAGES_LITERAL, language_code) if language_code in AVAILABLE_LANGUAGES_LIST else 'en'


def generate_anonymous_id(user_id: int, user_fname: str | None = None, with_history: bool = False) -> str:
    """Generate a unique, hashtag-friendly anonymous ID.

    Args:
        user_id: Telegram user ID used as hash seed.
        user_fname: Optional first name, mixed into the seed.
        with_history: When True the ID is deterministic (stable per user) and
            prefixed with '#'; otherwise it is randomized per message.

    Returns:
        The anonymous ID (10 alphanumeric chars, optionally '#'-prefixed).
    """
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
