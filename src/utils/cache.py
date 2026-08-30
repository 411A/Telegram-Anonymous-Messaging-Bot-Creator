"""In-memory async-safe cache for admin reply state."""
import asyncio
from typing import Any, ClassVar, Optional


class AdminsReplyCache:
    """High-performance async-safe singleton cache for admin replies.

    Maps an admin's user ID to their in-progress reply state. Reads rely on the
    GIL; writes are serialized through an asyncio lock.
    """

    _instance: ClassVar[Optional["AdminsReplyCache"]] = None

    def __new__(cls) -> "AdminsReplyCache":
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._cache = {}
            instance._write_lock = asyncio.Lock()
            cls._instance = instance
        return cls._instance

    _cache: dict[int, dict[str, Any]]
    _write_lock: asyncio.Lock

    async def set(self, admin_id: int, state: dict[str, Any]) -> None:
        """Set admin reply state with minimal locking."""
        async with self._write_lock:
            self._cache[admin_id] = state

    async def get(self, admin_id: int) -> dict[str, Any] | None:
        """Get admin reply state without locking for read operations."""
        # Read operations don't need locks in Python due to GIL
        return self._cache.get(admin_id)

    async def remove(self, admin_id: int) -> dict[str, Any] | None:
        """Remove admin reply state with minimal locking."""
        async with self._write_lock:
            return self._cache.pop(admin_id, None)

    async def exists(self, admin_id: int) -> bool:
        """Check if admin reply state exists without locking."""
        # Read operations don't need locks in Python due to GIL
        return admin_id in self._cache
