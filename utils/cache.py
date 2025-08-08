import asyncio
from typing import Dict, Any, Optional

# Async-Safe Singleton Cache for Admins Replies class
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