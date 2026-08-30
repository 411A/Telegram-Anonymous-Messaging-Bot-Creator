"""Encrypted SQLite persistence layer.

Implements the zero-knowledge storage scheme: bot tokens, admin IDs and
message callback payloads are stored encrypted with
ChaCha20-Poly1305 (key derived from the master password via PBKDF2).
Only *partial* hashes of callback payloads are persisted, so decryption is
impossible without the in-message hash fragment.
"""
import asyncio
import base64
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal, Optional

import aiosqlite
from cachebox import LRUCache, cached
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from configs.settings import SQLITE_DATABASE_NAME

logger = logging.getLogger(__name__)

#: Tables that store partial callback hashes, and their column names.
HashTableName = Literal["messages", "reads"]

_PREFIX_COLUMN_BY_TABLE: dict[HashTableName, tuple[str, str | None]] = {
    "messages": ("prefixed_msg_hash", "partial_msg_hash"),
    "reads": ("prefixed_hash", "partial_hash"),
}


def _resolve_prefix_column(table_name: HashTableName) -> tuple[str, str | None]:
    """Return ``(prefix_column, hash_column)`` for a partial-hash table.

    Args:
        table_name: Either ``"messages"`` or ``"reads"``.

    Raises:
        ValueError: If the table name is not supported.
    """
    try:
        return _PREFIX_COLUMN_BY_TABLE[table_name]
    except KeyError:
        raise ValueError("Invalid table name. Use 'messages' or 'reads'.") from None


class DatabaseManager:
    """Singleton async SQLite manager with a simple connection pool."""

    _instance: Optional["DatabaseManager"] = None

    db_path: str
    _pool: dict[str, aiosqlite.Connection]
    _init_task: "asyncio.Task[None]"
    encryptor: "Encryptor"

    def __new__(cls, db_path: str = str(SQLITE_DATABASE_NAME)) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.db_path = db_path
            cls._instance._pool = {}
            cls._instance.encryptor = Encryptor()
            # Initialize database tables asynchronously (keep a task reference)
            cls._instance._init_task = asyncio.create_task(cls._instance._init_db())
        return cls._instance

    @asynccontextmanager
    async def _get_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Get a connection from the pool or create a new one."""
        if self.db_path not in self._pool:
            conn = await aiosqlite.connect(self.db_path)
            # Optimize SQLite settings for better performance
            await conn.execute("PRAGMA journal_mode = WAL")
            await conn.execute("PRAGMA synchronous = NORMAL")
            # 64MB cache
            await conn.execute("PRAGMA cache_size = -64000")
            await conn.execute("PRAGMA temp_store = MEMORY")
            # 256MB memory map
            await conn.execute("PRAGMA mmap_size = 268435456")
            await conn.execute("PRAGMA foreign_keys = ON")
            # Handle contention when the database is locked (5 second timeout)
            await conn.execute("PRAGMA busy_timeout = 5000")
            self._pool[self.db_path] = conn
        try:
            yield self._pool[self.db_path]
        except Exception as e:
            logger.exception(f"Database operation failed: {e}")
            raise

    async def _init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        async with self._get_connection() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    bot_token TEXT PRIMARY KEY UNIQUE,
                    bot_username TEXT,
                    admin_id TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    prefixed_msg_hash PRIMARY KEY UNIQUE,
                    partial_msg_hash TEXT,
                    year_month TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS blocks (
                    blocked_user_id PRIMARY KEY,
                    bot_username TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS reads (
                    prefixed_hash TEXT PRIMARY KEY UNIQUE,
                    partial_hash TEXT
                )
            """)
            # Create optimized indexes for faster queries
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_aid ON admins(admin_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bu_admins ON admins(bot_username)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bt ON admins(bot_token)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_pemh ON messages(prefixed_msg_hash)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_year_month ON messages(year_month)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_peh ON reads(prefixed_hash)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_uib ON blocks(blocked_user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bu_blocks ON blocks(bot_username)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_composite_blocks ON blocks(blocked_user_id, bot_username)")
            await conn.commit()
    async def get_full_hash_by_prefix(self, prefix: str, suffix: str, table_name: HashTableName) -> str | None:
        """Retrieve and reconstruct the full hash using prefix and suffix.

        Args:
            prefix: The prefix part of the hash used as the database key.
            suffix: The suffix part of the hash to be appended.
            table_name: The database table to query ("messages" or "reads").

        Returns:
            The full reconstructed hash if found, None otherwise.
        """
        try:
            prefix_col, hash_col = _resolve_prefix_column(table_name)
            assert hash_col is not None  # Both supported tables have a hash column

            async with self._get_connection() as conn:
                # Table/column names come from an internal whitelist, never user input.
                query = f"SELECT {hash_col} FROM {table_name} WHERE {prefix_col} = ? LIMIT 1"
                async with conn.execute(query, (prefix,)) as cursor:
                    result = await cursor.fetchone()
                    if not result:
                        return None
                    # Reconstruct the full encrypted hash from its stored part
                    return result[0] + suffix
        except ValueError as ve:
            logger.error("Validation Error: %s", str(ve))
            return None
        except Exception as e:
            logger.exception(f"Error retrieving hash: {e}")
            return None
    async def remove_bot_entry(self, encrypted_bot_token: str) -> bool:
        """Remove a bot entry from the database using the encrypted bot_token.

        Args:
            encrypted_bot_token (str): The encrypted bot_token to remove from the database.

        Returns:
            bool: True if the entry was successfully removed, False otherwise.
        """
        try:
            async with self._get_connection() as conn:
                # Delete the bot entry directly using the encrypted token
                cursor = await conn.execute('DELETE FROM admins WHERE bot_token = ?', (encrypted_bot_token,))
                await conn.commit()

                # Return True if any rows were affected
                return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error removing bot entry: {e}")
            return False

    async def store_partial_hash(self, prefix_hash: str, stored_hash: str, table_name: HashTableName, year_month: str | None = None) -> bool:
        """Store an encrypted partial hash in the given table.

        Args:
            prefix_hash: The hash prefix, used as the primary key.
            stored_hash: The middle portion of the hash kept in the database.
            table_name: The database table ("messages" or "reads").
            year_month: Optional ``YYYY-MM`` grouping value (messages only).

        Returns:
            True on success, False otherwise.
        """
        try:
            prefix_col, hash_col = _resolve_prefix_column(table_name)
            async with self._get_connection() as conn:
                if table_name == 'messages':
                    await conn.execute(
                        f'INSERT INTO messages ({prefix_col}, {hash_col}, year_month) VALUES (?, ?, ?)',
                        (prefix_hash, stored_hash, year_month),
                    )
                else:  # 'reads'
                    await conn.execute(
                        f'INSERT INTO reads ({prefix_col}, {hash_col}) VALUES (?, ?)',
                        (prefix_hash, stored_hash),
                    )
                await conn.commit()
                return True
        except Exception as e:
            logger.exception(f"Error storing message hash: {e}")
            return False

    def _encrypt_block_key(self, user_id: int, bot_username: str) -> tuple[str, str]:
        """Deterministically encrypt a (user_id, bot_username) block-table key pair."""
        return (
            self.encryptor.encrypt(str(user_id), deterministic=True),
            self.encryptor.encrypt(bot_username, deterministic=True),
        )

    async def close_all(self) -> None:
        """Close all database connections in the pool."""
        for conn in self._pool.values():
            await conn.close()
        self._pool.clear()

    async def get_decrypted_bot_tokens(self) -> list[str]:
        """Get a list of decrypted bot tokens from the database.

        Returns:
            List[str]: A list of decrypted bot tokens.
        """
        decrypted_tokens: list[str] = []
        try:
            async with self._get_connection() as conn, conn.execute('SELECT bot_token FROM admins') as cursor:
                encrypted_tokens = await cursor.fetchall()

                for (encrypted_token,) in encrypted_tokens:
                    try:
                        bot_token = self.encryptor.decrypt(encrypted_token)
                        decrypted_tokens.append(bot_token)
                    except Exception as e:
                        logger.exception(f"Error decrypting bot_token {encrypted_token}\n{e}")
                        continue
            return decrypted_tokens
        except Exception as e:
            logger.exception(f"Error retrieving bot tokens: {e}")
            return []

    async def block_user(self, user_id: int, bot_username: str) -> bool:
        """Block a user for a specific bot.

        Args:
            user_id (int): The ID of the user to block
            bot_username (str): The username of the bot

        Returns:
            bool: True if the user was successfully blocked, False otherwise
        """
        try:
            encrypted_id, encrypted_bu = self._encrypt_block_key(user_id, bot_username)
            async with self._get_connection() as conn:
                await conn.execute('INSERT INTO blocks (blocked_user_id, bot_username) VALUES (?, ?)', (encrypted_id, encrypted_bu))
                await conn.commit()
                return True
        except Exception as e:
            logger.exception(f"Error blocking user: {e}")
            return False

    async def unblock_user(self, user_id: int, bot_username: str) -> bool:
        """Unblock a user for a specific bot.

        Args:
            user_id (int): The ID of the user to unblock
            bot_username (str): The username of the bot

        Returns:
            bool: True if the user was successfully unblocked, False otherwise
        """
        try:
            encrypted_id, encrypted_bu = self._encrypt_block_key(user_id, bot_username)
            async with self._get_connection() as conn:
                cursor = await conn.execute('DELETE FROM blocks WHERE blocked_user_id = ? AND bot_username = ?', (encrypted_id, encrypted_bu))
                await conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error unblocking user: {e}")
            return False
    async def is_user_blocked(self, user_id: int, bot_username: str) -> bool:
        """Check if a user is blocked for a specific bot.

        Args:
            user_id (int): The ID of the user to check
            bot_username (str): The username of the bot

        Returns:
            bool: True if the user is blocked, False otherwise
        """
        try:
            encrypted_id, encrypted_bu = self._encrypt_block_key(user_id, bot_username)
            async with self._get_connection() as conn, conn.execute('SELECT 1 FROM blocks WHERE blocked_user_id = ? AND bot_username = ? LIMIT 1', (encrypted_id, encrypted_bu)) as cursor:
                return await cursor.fetchone() is not None
        except Exception as e:
            logger.exception(f"Error checking if user is blocked: {e}")
            return False

    async def remove_partial_hash(self, prefix_hash: str, table_name: HashTableName) -> bool:
        """Remove a row from the specified table using the prefix hash.

        Args:
            prefix_hash: The prefix hash used as the primary key.
            table_name: The database table to remove from ("messages" or "reads").

        Returns:
            True if the row was successfully removed, False otherwise.
        """
        try:
            prefix_col, _ = _resolve_prefix_column(table_name)

            async with self._get_connection() as conn:
                cursor = await conn.execute(f'DELETE FROM {table_name} WHERE {prefix_col} = ?', (prefix_hash,))
                await conn.commit()
                return cursor.rowcount > 0
        except ValueError as ve:
            logger.error(f"Validation Error: {ve}")
            return False
        except Exception as e:
            logger.exception(f"Error removing hash from {table_name}\n{e}")
            return False

class Encryptor:
    """Singleton ChaCha20-Poly1305 encryptor keyed by the master password.

    Supports non-deterministic encryption (random salt/nonce, for one-off
    secrets like bot tokens) and deterministic encryption (stable salt/nonce,
    required for consistent database lookups).
    """

    _instance: Optional["Encryptor"] = None
    master_password: str | None

    def __init__(self, password: str | None = None):
        if password is not None:
            self.master_password = password

    def __new__(cls, password: str | None = None) -> "Encryptor":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.master_password = password
        return cls._instance

    def _derive_key(self, salt: bytes) -> bytes:
        if self.master_password is None:
            logger.error("_derive_key: Master password not set, cannot derive key")
            raise ValueError("Master password must be set before encryption/decryption")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return kdf.derive(self.master_password.encode())

    def encrypt(self, data: str, deterministic: bool = False) -> str:
        """Encrypt a string, returning base64(salt + nonce + ciphertext).

        Args:
            data: Plaintext to encrypt.
            deterministic: When True, derive salt/nonce from the master
                password so equal inputs produce equal ciphertexts (needed
                for encrypted lookups). Use only for low-entropy identifiers.
        """
        if self.master_password is None:
            logger.error("encrypt: Master password not set, cannot encrypt data")
            raise ValueError("Master password must be set before encryption")

        if deterministic:
            # Use master password as salt for deterministic encryption
            salt = self.master_password.encode()[:32].ljust(32, b'0')
        else:
            salt = os.urandom(32)  # Generate a unique salt for this encryption
        key = self._derive_key(salt)
        chacha = ChaCha20Poly1305(key)
        if deterministic:
            # Use a fixed nonce derived from master password for deterministic encryption
            nonce = self.master_password.encode()[:12].ljust(12, b'0')
        else:
            nonce = os.urandom(12)
        ciphertext = chacha.encrypt(nonce, data.encode(), None)
        # Combine salt + nonce + ciphertext for storage
        combined = salt + nonce + ciphertext
        return base64.b64encode(combined).decode('utf-8')

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt a value produced by :meth:`encrypt`.

        Raises:
            ValueError: If the data cannot be decrypted.
        """
        try:
            data = base64.b64decode(encrypted_data.encode('utf-8'))
            salt = data[:32]
            nonce = data[32:44]
            ciphertext = data[44:]
            key = self._derive_key(salt)
            chacha = ChaCha20Poly1305(key)
            plaintext = chacha.decrypt(nonce, ciphertext, None)
            return plaintext.decode('utf-8')
        except Exception as e:
            raise ValueError(f'Decryption failed: {e!s}') from e

class AdminManager:
    """Singleton service for admin registration and lookup operations."""

    _instance: Optional["AdminManager"] = None
    db: DatabaseManager
    encryptor: Encryptor

    def __init__(self, db_manager: DatabaseManager | None = None, encryptor: Encryptor | None = None):
        if db_manager is not None:
            self.db = db_manager
        if encryptor is not None:
            self.encryptor = encryptor

    def __new__(cls, db_manager: DatabaseManager | None = None, encryptor: Encryptor | None = None) -> "AdminManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.db = db_manager or DatabaseManager()
            cls._instance.encryptor = encryptor or Encryptor()
        return cls._instance

    async def add_admin(self, bot_token: str, bot_username: str, user_id: int) -> bool:
        """Register a bot token with its owner as admin.

        Returns:
            True when inserted, False if the token was already registered.
        """
        encrypted_bt = self.encryptor.encrypt(bot_token, deterministic=True)
        encrypted_bu = self.encryptor.encrypt(bot_username, deterministic=True)
        encrypted_id = self.encryptor.encrypt(str(user_id), deterministic=True)
        try:
            async with self.db._get_connection() as conn:
                await conn.execute('INSERT INTO admins (bot_token, bot_username, admin_id) VALUES (?, ?, ?)', (encrypted_bt, encrypted_bu, encrypted_id))
                await conn.commit()
                return True
        except aiosqlite.IntegrityError:
            return False

    async def is_admin(self, user_id: int, bot_username: str | None = None) -> bool:
        """Check whether a user is registered as an admin (optionally of a specific bot)."""
        # Use deterministic encryption for consistent lookups
        encrypted_id = self.encryptor.encrypt(str(user_id), deterministic=True)

        # Query database with optimized query
        async with self.db._get_connection() as conn:
            if bot_username:
                # Encrypt bot_username for database query
                encrypted_bu = self.encryptor.encrypt(bot_username, deterministic=True)
                # Use composite index for faster lookup
                async with conn.execute('SELECT 1 FROM admins WHERE admin_id = ? AND bot_username = ? LIMIT 1', (encrypted_id, encrypted_bu)) as cursor:
                    return await cursor.fetchone() is not None
            else:
                # Use index for faster lookup
                async with conn.execute('SELECT 1 FROM admins WHERE admin_id = ? LIMIT 1', (encrypted_id,)) as cursor:
                    return await cursor.fetchone() is not None

    # cachebox passes the bound `self` as the first positional argument,
    # so the cache key must be derived from the `bot_username` argument.
    @cached(LRUCache(maxsize=1000), key_maker=lambda *args, **kwargs: args[1] if len(args) > 1 else kwargs.get('bot_username', 'default'))
    async def get_admin_id_from_bot(self, bot_username: str) -> int | None:
        """Return the decrypted admin user ID for a bot username (LRU-cached)."""
        try:
            # Use deterministic encryption for bot username to ensure consistent lookup
            encrypted_bu = self.encryptor.encrypt(bot_username, deterministic=True)

            # Query the admin record directly using the encrypted bot username with LIMIT
            async with self.db._get_connection() as conn, conn.execute('SELECT admin_id FROM admins WHERE bot_username = ? LIMIT 1', (encrypted_bu,)) as cursor:
                result = await cursor.fetchone()

                if not result:
                    return None

                # Decrypt and return the admin ID
                decrypted_id = self.encryptor.decrypt(result[0])
                return int(decrypted_id)
        except Exception:
            return None
