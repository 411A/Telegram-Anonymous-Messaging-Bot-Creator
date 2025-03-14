"""Utility functions for the application."""
import re
import asyncio
import base64
import hashlib
import random
import string
import time
from configs.constants import AVAILABLE_LANGUAGES_LITERAL, AVAILABLE_LANGUAGES_LIST
from typing import Dict, Any, Optional

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

def check_language_availability(language_code: str) -> AVAILABLE_LANGUAGES_LITERAL:
    """Check if a language code is available in the supported languages list.
    
    Args:
        language_code (str): The language code to check.
        
    Returns:
        Literal['en', 'fa']: The validated language code. Returns 'en' if the input is not supported.
    """
    global AVAILABLE_LANGUAGES_LIST
    return language_code if language_code in AVAILABLE_LANGUAGES_LIST else 'en'

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

# Async-Safe Singleton Cache for Admins Repliesclass
class AdminsReplyCache:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AdminsReplyCache, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Initialize only once
        if not hasattr(self, '_cache'):
            self._cache: Dict[int, Dict[str, Any]] = dict()
            self._lock = asyncio.Lock()

    async def set(self, admin_id: int, state: dict) -> None:
        async with self._lock:
            self._cache[admin_id] = state

    async def get(self, admin_id: int) -> Optional[Dict[str, Any]]:
        async with self._lock:
            return self._cache.get(admin_id)

    async def remove(self, admin_id: int) -> Optional[Dict[str, Any]]:
        async with self._lock:
            return self._cache.pop(admin_id, None)

    async def exists(self, admin_id: int) -> bool:
        async with self._lock:
            return admin_id in self._cache
