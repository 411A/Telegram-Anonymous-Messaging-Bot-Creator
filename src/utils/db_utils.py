import aiosqlite
import os
from typing import Optional, List
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
from contextlib import asynccontextmanager
import asyncio
from configs.settings import SQLITE_DATABASE_NAME
import logging
from cachebox import cached, LRUCache

logger = logging.getLogger(__name__)

class DatabaseManager:
    _instance = None
    
    def __init__(self):
        # These attributes are set in __new__, but declared here for type checking
        self.db_path: str
        self._pool: dict
        self.encryptor: Encryptor

    def __new__(cls, db_path: str = str(SQLITE_DATABASE_NAME)):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.db_path = db_path
            cls._instance._pool = dict()
            cls._instance.encryptor = Encryptor()
            # Initialize database tables asynchronously
            asyncio.create_task(cls._instance._init_db())
        return cls._instance

    @asynccontextmanager
    async def _get_connection(self):
        """Get a connection from the pool or create a new one."""
        if self.db_path not in self._pool:
            self._pool[self.db_path] = await aiosqlite.connect(self.db_path)
        try:
            yield self._pool[self.db_path]
        except Exception as e:
            logger.exception(f"Database connection error: {e}")
            raise

    async def _init_db(self):
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
            await conn.execute("PRAGMA journal_mode=WAL;")
            await conn.execute("PRAGMA cache_size=1000;")
            # Handle contention when the database is locked by another connection, wait up to 5000ms
            await conn.execute("PRAGMA busy_timeout=5000;")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_aid ON admins(admin_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bu ON admins(bot_username)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bt ON admins(bot_token)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_pemh ON messages(prefixed_msg_hash)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_peh ON reads(prefixed_hash)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_uib ON blocks(blocked_user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bu ON blocks(bot_username)")

            await conn.commit()
    async def get_full_hash_by_prefix(self, prefix: str, suffix: str, table_name: str) -> Optional[str]:
        """Retrieve and reconstruct the full hash using prefix and suffix.
        
        Args:
            prefix (str): The prefix part of the hash used as the database key.
            suffix (str): The suffix part of the hash to be appended.
            table_name (str): The database table to query (either "messages" or "reads").
        
        Returns:
            Optional[str]: The full reconstructed hash if found, None otherwise.
        """
        try:
            # Validate and map the correct table/column names
            if table_name == "messages":
                prefix_col, hash_col = "prefixed_msg_hash", "partial_msg_hash"
            elif table_name == "reads":
                prefix_col, hash_col = "prefixed_hash", "partial_hash"
            else:
                raise ValueError("Invalid table name. Use 'messages' or 'reads'.")

            async with self._get_connection() as conn:
                query = "SELECT {} FROM {} WHERE {} = ?".format(hash_col, table_name, prefix_col)
                async with conn.execute(query, (prefix,)) as cursor:
                    result = await cursor.fetchone()
                    
                    if not result:
                        return None
                    
                    # Get the stored hash and reconstruct the full encrypted hash
                    stored_hash = result[0]
                    return stored_hash + suffix
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

    async def store_partial_hash(self, prefix_hash: str, stored_hash: str, table_name: str, year_month: Optional[str] = None) -> bool:
        """Store an encrypted hash in the given table."""
        try:
            async with self._get_connection() as conn:
                if table_name == 'messages':
                    await conn.execute('INSERT INTO messages (prefixed_msg_hash, partial_msg_hash, year_month) VALUES (?, ?, ?)', (prefix_hash, stored_hash, year_month,))
                elif table_name == 'reads':
                    await conn.execute('INSERT INTO reads (prefixed_hash, partial_hash) VALUES (?, ?)', (prefix_hash, stored_hash,))
                await conn.commit()
                return True
        except Exception as e:
            logger.exception(f"Error storing message hash: {e}")
            return False

    async def close_all(self):
        """Close all database connections in the pool."""
        for conn in self._pool.values():
            await conn.close()
        self._pool.clear()

    async def get_decrypted_bot_tokens(self) -> List[str]:
        """Get a list of decrypted bot tokens from the database.
        
        Returns:
            List[int]: A list of decrypted bot tokens.
        """
        decrypted_tokens = list()
        try:
            async with self._get_connection() as conn:
                async with conn.execute('SELECT bot_token FROM admins') as cursor:
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
            # Use deterministic encryption for consistent lookups
            encrypted_id = self.encryptor.encrypt(str(user_id), deterministic=True)
            encrypted_bu = self.encryptor.encrypt(bot_username, deterministic=True)
            
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
            # Use deterministic encryption for consistent lookups
            encrypted_id = self.encryptor.encrypt(str(user_id), deterministic=True)
            encrypted_bu = self.encryptor.encrypt(bot_username, deterministic=True)
            
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
            # Use deterministic encryption for consistent lookups
            encrypted_id = self.encryptor.encrypt(str(user_id), deterministic=True)
            encrypted_bu = self.encryptor.encrypt(bot_username, deterministic=True)
            
            async with self._get_connection() as conn:
                async with conn.execute('SELECT 1 FROM blocks WHERE blocked_user_id = ? AND bot_username = ?', (encrypted_id, encrypted_bu)) as cursor:
                    result = await cursor.fetchone()
                    return result is not None
        except Exception as e:
            logger.exception(f"Error checking if user is blocked: {e}")
            return False

    async def remove_partial_hash(self, prefix_hash: str, table_name: str) -> bool:
        """Remove a row from the specified table using the prefix hash.
        
        Args:
            prefix_hash (str): The prefix hash used as the primary key.
            table_name (str): The database table to remove from (either "messages" or "reads").
            
        Returns:
            bool: True if the row was successfully removed, False otherwise.
        """
        try:
            # Validate and map the correct table/column names
            if table_name == "messages":
                prefix_col = "prefixed_msg_hash"
            elif table_name == "reads":
                prefix_col = "prefixed_hash"
            else:
                raise ValueError("Invalid table name. Use 'messages' or 'reads'.")

            async with self._get_connection() as conn:
                cursor = await conn.execute('DELETE FROM {} WHERE {} = ?'.format(table_name, prefix_col), (prefix_hash,))
                await conn.commit()
                return cursor.rowcount > 0
        except ValueError as ve:
            logger.error(f"Validation Error: {ve}")
            return False
        except Exception as e:
            logger.exception(f"Error removing hash from {table_name}\n{e}")
            return False

class Encryptor:
    _instance = None
    
    def __init__(self, password: Optional[str] = None):
        # This attribute is set in __new__, but declared here for type checking
        self.master_password: Optional[str]
        if password is not None:
            self.master_password = password

    def __new__(cls, password: Optional[str] = None):
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
            raise ValueError(f'Decryption failed: {str(e)}')

class AdminManager:
    _instance = None
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None, encryptor: Optional[Encryptor] = None):
        # These attributes are set in __new__, but declared here for type checking
        self.db: DatabaseManager
        self.encryptor: Encryptor
        if db_manager is not None:
            self.db = db_manager
        if encryptor is not None:
            self.encryptor = encryptor

    def __new__(cls, db_manager: Optional[DatabaseManager] = None, encryptor: Optional[Encryptor] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.db = db_manager or DatabaseManager()
            cls._instance.encryptor = encryptor or Encryptor()
        return cls._instance

    async def add_admin(self, bot_token: str, bot_username: str, user_id: int) -> bool:
        
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

    async def is_admin(self, user_id: int, bot_username: Optional[str] = None) -> bool:
        async with self.db._get_connection() as conn:
            if bot_username:
                # Encrypt both user_id and bot_username for database query
                encrypted_id = self.encryptor.encrypt(str(user_id), deterministic=True)
                encrypted_bu = self.encryptor.encrypt(bot_username, deterministic=True)
                # Query both admin_id and bot_username together
                async with conn.execute('SELECT 1 FROM admins WHERE admin_id = ? AND bot_username = ?', (encrypted_id, encrypted_bu)) as cursor:
                    result = await cursor.fetchone()
                    return result is not None
            else:
                # Encrypt user_id for direct comparison
                encrypted_id = self.encryptor.encrypt(str(user_id), deterministic=True)
                async with conn.execute('SELECT 1 FROM admins WHERE admin_id = ?', (encrypted_id,)) as cursor:
                    result = await cursor.fetchone()
                    return result is not None

    @cached(LRUCache(maxsize=1000), lambda args, kwargs: args[1] if args else kwargs.get('bot_username'))
    async def get_admin_id_from_bot(self, bot_username: str) -> Optional[int]:
        try:
            # Use deterministic encryption for bot username to ensure consistent lookup
            encrypted_bu = self.encryptor.encrypt(bot_username, deterministic=True)
            
            async with self.db._get_connection() as conn:
                # Query the admin record directly using the encrypted bot username
                async with conn.execute('SELECT admin_id FROM admins WHERE bot_username = ?', (encrypted_bu,)) as cursor:
                    result = await cursor.fetchone()
                    
                    if not result:
                        return None
                    
                    # Decrypt and return the admin ID
                    decrypted_id = self.encryptor.decrypt(result[0])
                    return int(decrypted_id)
        except Exception:
            return None
