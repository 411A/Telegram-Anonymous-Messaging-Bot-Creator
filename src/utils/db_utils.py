"""Encrypted SQLite persistence layer.

Implements the zero-knowledge storage scheme: bot tokens, admin IDs and
message callback payloads are stored encrypted with
ChaCha20-Poly1305 (key derived from the master password via PBKDF2).
Only *partial* hashes of callback payloads are persisted, so decryption is
impossible without the in-message hash fragment.
"""
import asyncio
import base64
import hashlib
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Literal, Optional

import aiosqlite
from cachebox import LRUCache, cached
from cryptography.exceptions import InvalidTag
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

#: PBKDF2 work factor. Unchanged on purpose: existing rows keep their format
#: and the offline-cracking cost stays exactly the same.
_PBKDF2_ITERATIONS = 100_000

#: Public domain-separation salt for non-deterministic encryption.
#:
#: A fresh random salt per message used to force a full PBKDF2 derivation
#: (100k iterations, ~20 ms of CPU) for *every* anonymous message, because the
#: salt was part of the KDF cache key. The salt is stored next to the
#: ciphertext, so it never added secrecy; its only job was uniqueness. The key
#: is now derived from this fixed, cacheable salt, while the stored random salt
#: still randomizes the ciphertext prefix (which is also the database key and
#: the first part of the Telegram callback) and the random 96-bit nonce makes
#: every ciphertext unique. It is deliberately different from the deterministic
#: salt, so the two key/nonce spaces can never collide.
_NONDETERMINISTIC_SALT = hashlib.sha256(b"hidego/nondeterministic/v1").digest()

#: Public, fixed salt and nonce for deterministic encryption.
#:
#: The legacy scheme used the master password itself as both salt and nonce and
#: stored them in every ciphertext, so anyone with the database could recover
#: the password (and decrypt everything). Deterministic lookups only need a
#: stable key, never a secret salt. These are public domain-separation values;
#: deriving the key still requires the master password via PBKDF2.
_DETERMINISTIC_SALT = hashlib.sha256(b"hidego/deterministic/salt/v1").digest()
_DETERMINISTIC_NONCE = hashlib.sha256(
    b"hidego/deterministic/nonce/v1"
).digest()[:12]


@lru_cache(maxsize=1024)
def _derive_key_cached(password: str, salt: bytes) -> bytes:
    """Derive (and memoize) the ChaCha20 key for one password/salt pair.

    One PBKDF2-HMAC-SHA256 derivation at 100k iterations costs tens of
    milliseconds of pure CPU. The application re-derived the *same* key for
    every deterministic lookup (admin ID, user ID, bot username) and for every
    callback decrypt, so the KDF dominated CPU usage on a small VPS.

    Caching the 32-byte result changes neither the stored format nor any
    ciphertext: identical KDF inputs produce identical keys. The password is
    part of the cache key, so a changed master password can never reuse a
    stale entry. At most 1024 recent salts are retained (~100 KiB).
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode())


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
            # Overwrite deleted cell content instead of leaving it in free
            # pages. Deletes are rare (revoke/block/read), so the cost is tiny
            # and old ciphertext cannot linger on disk.
            await conn.execute("PRAGMA secure_delete = ON")
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
            # Only the indexes a query actually uses. The PRIMARY KEY already
            # indexes admins.bot_token, messages.prefixed_msg_hash,
            # blocks.blocked_user_id and reads.prefixed_hash, so the old
            # duplicate indexes only added a B-tree write to every insert.
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_aid ON admins(admin_id)")
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_bu_admins ON admins(bot_username)"
            )
            for redundant_index in (
                "idx_bt",
                "idx_pemh",
                "idx_year_month",
                "idx_peh",
                "idx_uib",
                "idx_bu_blocks",
                "idx_composite_blocks",
            ):
                await conn.execute(f"DROP INDEX IF EXISTS {redundant_index}")
            # One-time, idempotent: move deterministic rows off the legacy
            # password-as-salt format before any bot can query them.
            migrated = await self._migrate_deterministic_columns(conn)
            await conn.commit()
            if migrated:
                # Updating a row does not necessarily erase the old bytes:
                # they can survive in free pages and the WAL. Rewrite the DB
                # and truncate the WAL so no legacy password-bearing
                # ciphertext remains on disk.
                logger.info(
                    "Deterministic rows migrated; compacting database to "
                    "purge legacy ciphertext"
                )
                try:
                    async with conn.execute(
                        "PRAGMA wal_checkpoint(TRUNCATE)"
                    ) as cursor:
                        await cursor.fetchall()
                    await conn.execute("VACUUM")
                    async with conn.execute(
                        "PRAGMA wal_checkpoint(TRUNCATE)"
                    ) as cursor:
                        await cursor.fetchall()
                except Exception:
                    logger.exception(
                        "Post-migration VACUUM failed; run VACUUM manually "
                        "to purge legacy pages"
                    )

    async def _migrate_deterministic_columns(
        self, conn: aiosqlite.Connection
    ) -> bool:
        """Re-encrypt deterministic columns with the public salt/nonce.

        Older rows used the master password itself as salt and nonce, and
        stored both next to the ciphertext. Re-encrypting with the new public
        values removes that leak. The operation is idempotent: a row already
        in the new format decrypts and re-encrypts to the same bytes.

        Returns:
            True when at least one row was rewritten, False otherwise.
        """
        if self.encryptor.master_password is None:
            logger.warning(
                "Skipping deterministic-column migration: master password not set"
            )
            return False

        changed = False

        def reencrypt(value: str | None) -> str | None:
            if value is None:
                return None
            return self.encryptor.encrypt(
                self.encryptor.decrypt(value), deterministic=True
            )

        async with conn.execute(
            "SELECT bot_token, bot_username, admin_id FROM admins"
        ) as cursor:
            admin_rows = await cursor.fetchall()
        for old_token, old_username, old_admin in admin_rows:
            try:
                new_token = reencrypt(old_token)
                new_username = reencrypt(old_username)
                new_admin = reencrypt(old_admin)
                if (new_token, new_username, new_admin) != (
                    old_token,
                    old_username,
                    old_admin,
                ):
                    await conn.execute(
                        "UPDATE admins SET bot_token=?, bot_username=?, admin_id=?"
                        " WHERE bot_token=?",
                        (new_token, new_username, new_admin, old_token),
                    )
                    changed = True
            except aiosqlite.IntegrityError:
                # A migrated copy already exists for this plaintext; drop the
                # legacy duplicate so the password-bearing row cannot remain.
                logger.warning("Removing a duplicate legacy admin row")
                await conn.execute(
                    "DELETE FROM admins WHERE bot_token=?", (old_token,)
                )
                changed = True
            except Exception:
                logger.exception(
                    "Failed to migrate an admin row; leaving it unchanged"
                )

        async with conn.execute(
            "SELECT blocked_user_id, bot_username FROM blocks"
        ) as cursor:
            block_rows = await cursor.fetchall()
        for old_blocked_id, old_bot_username in block_rows:
            try:
                new_blocked_id = reencrypt(old_blocked_id)
                new_bot_username = reencrypt(old_bot_username)
                if (new_blocked_id, new_bot_username) != (
                    old_blocked_id,
                    old_bot_username,
                ):
                    await conn.execute(
                        "UPDATE blocks SET blocked_user_id=?, bot_username=?"
                        " WHERE blocked_user_id=?",
                        (new_blocked_id, new_bot_username, old_blocked_id),
                    )
                    changed = True
            except aiosqlite.IntegrityError:
                logger.warning("Removing a duplicate legacy block row")
                await conn.execute(
                    "DELETE FROM blocks WHERE blocked_user_id=?",
                    (old_blocked_id,),
                )
                changed = True
            except Exception:
                logger.exception(
                    "Failed to migrate a block row; leaving it unchanged"
                )

        return changed

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
        return _derive_key_cached(self.master_password, salt)

    def encrypt(self, data: str, deterministic: bool = False) -> str:
        """Encrypt a string, returning base64(salt + nonce + ciphertext).

        Args:
            data: Plaintext to encrypt.
            deterministic: When True, use the public fixed salt/nonce so equal
                inputs produce equal ciphertexts (needed for encrypted
                lookups). Use only for low-entropy identifiers.
                When False, reuse the cached key with a random 96-bit nonce,
                so every ciphertext is unique without repeated KDF work.
        """
        if self.master_password is None:
            logger.error("encrypt: Master password not set, cannot encrypt data")
            raise ValueError("Master password must be set before encryption")

        if deterministic:
            # Public fixed salt + nonce keep lookups stable without ever
            # storing (or deriving from) the master password as key material.
            salt = _DETERMINISTIC_SALT
            nonce = _DETERMINISTIC_NONCE
            key = self._derive_key(salt)
        else:
            # Random salt keeps the stored ciphertext prefix unique (it is
            # the database key and the start of the Telegram callback). The
            # key itself comes from the cached domain-separated salt, so a
            # send never pays PBKDF2; the random nonce keeps ciphertexts
            # unique even for identical plaintext.
            salt = os.urandom(32)
            nonce = os.urandom(12)
            key = self._derive_key(_NONDETERMINISTIC_SALT)
        chacha = ChaCha20Poly1305(key)
        ciphertext = chacha.encrypt(nonce, data.encode(), None)
        # Combine salt + nonce + ciphertext for storage
        combined = salt + nonce + ciphertext
        return base64.b64encode(combined).decode('utf-8')

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt a value produced by :meth:`encrypt`.

        New non-deterministic blobs use the cached fixed key. Rows written by
        older versions used the random salt (non-deterministic) or the master
        password (deterministic) as the KDF salt, so they fall back to that
        derivation (once per old salt) and keep working unchanged.

        Raises:
            ValueError: If the data cannot be decrypted.
        """
        try:
            data = base64.b64decode(encrypted_data.encode('utf-8'))
            salt = data[:32]
            nonce = data[32:44]
            ciphertext = data[44:]

            # The legacy deterministic format used the password itself as the
            # salt; keep that derivation readable for rows not yet migrated.
            legacy_deterministic_salt = (
                self.master_password.encode()[:32].ljust(32, b'0')
                if self.master_password is not None else b''
            )
            candidate_keys: tuple[bytes, ...]
            if salt == _DETERMINISTIC_SALT:
                candidate_keys = (
                    self._derive_key(_DETERMINISTIC_SALT),
                    self._derive_key(_NONDETERMINISTIC_SALT),
                )
            elif salt == legacy_deterministic_salt:
                candidate_keys = (
                    self._derive_key(legacy_deterministic_salt),
                    self._derive_key(_NONDETERMINISTIC_SALT),
                )
            else:
                candidate_keys = (self._derive_key(_NONDETERMINISTIC_SALT),)

            for key in candidate_keys:
                try:
                    return ChaCha20Poly1305(key).decrypt(
                        nonce, ciphertext, None
                    ).decode('utf-8')
                except InvalidTag:
                    continue

            # Legacy non-deterministic row: the stored random salt was the
            # actual KDF salt. This is only reached for pre-upgrade data.
            return ChaCha20Poly1305(
                self._derive_key(salt)
            ).decrypt(nonce, ciphertext, None).decode('utf-8')
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
