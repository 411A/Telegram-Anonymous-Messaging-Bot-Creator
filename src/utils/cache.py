import asyncio
from typing import Dict, Any, Optional

# High-performance Async-Safe Singleton Cache for Admin Replies
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
            # Use RWLock-like pattern for better performance
            self._write_lock = asyncio.Lock()

    async def set(self, admin_id: int, state: dict) -> None:
        """Set admin reply state with minimal locking."""
        async with self._write_lock:
            self._cache[admin_id] = state

    async def get(self, admin_id: int) -> Optional[Dict[str, Any]]:
        """Get admin reply state without locking for read operations."""
        # Read operations don't need locks in Python due to GIL
        return self._cache.get(admin_id)

    async def remove(self, admin_id: int) -> Optional[Dict[str, Any]]:
        """Remove admin reply state with minimal locking."""
        async with self._write_lock:
            return self._cache.pop(admin_id, None)

    async def exists(self, admin_id: int) -> bool:
        """Check if admin reply state exists without locking."""
        # Read operations don't need locks in Python due to GIL
        return admin_id in self._cache