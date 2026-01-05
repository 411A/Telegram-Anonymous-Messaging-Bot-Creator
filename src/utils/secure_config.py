import os
import sys
import getpass
import secrets
import base64
import time
from pathlib import Path

# Infisical SDK (Correct import for 'infisical-sdk')
from infisical_sdk import InfisicalSDKClient

# Cryptography (REQUIRED for your manual fallback logic)
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from configs.settings import SECURE_CONFIG_FILE, INFISICAL_RETRY_DELAY, INFISICAL_MAX_RETRIES


# ==========================================
# 1. Crypto Helpers (For Manual Fallback)
# ==========================================

def generate_salt() -> bytes:
    return secrets.token_bytes(32)

def derive_key(password: str, salt: bytes) -> bytes:
    """
    Derives a secure cryptographic key from a password using PBKDF2.
    Requires the 'cryptography' library.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return kdf.derive(password.encode())

def save_config(salt: bytes, key_verification: bytes):
    """Saves the salt and verification hash to disk."""
    with open(SECURE_CONFIG_FILE, 'wb') as f:
        f.write(salt + key_verification)

def verify_key(password: str, salt: bytes, key_verification: bytes) -> bool:
    """Verifies a password against the stored salt and verification hash."""
    derived_key = derive_key(password, salt)
    # Double derive for verification storage (prevents attacks on the key itself)
    return secrets.compare_digest(
        derive_key(base64.b64encode(derived_key).decode(), salt),
        key_verification
    )

# ==========================================
# 2. Infisical Integration (Primary Method)
# ==========================================

def get_infisical_secret() -> str | None:
    """
    Attempts to retrieve 'ANAMA_ENCRYPTOR' from Infisical.
    Returns None if configuration is missing or connection fails.
    """
    # These variables should be loaded from your .env file via Docker
    secret_name = os.getenv("INFISICAL_SECRET_NAME", "ANONYMOUS_MASTER_PASSWORD")
    client_id = os.getenv("INFISICAL_CLIENT_ID")
    client_secret = os.getenv("INFISICAL_CLIENT_SECRET")
    project_id = os.getenv("INFISICAL_PROJECT_ID")
    env_slug = os.getenv("INFISICAL_ENVIRONMENT", "prod")

    # If variables aren't set, skip straight to manual fallback
    if not (client_id and client_secret and project_id):
        return None

    try:
        # Initialize Client
        client = InfisicalSDKClient(host="https://app.infisical.com")

        # Authenticate (Universal Auth)
        client.auth.universal_auth.login(
            client_id=client_id,
            client_secret=client_secret
        )

        # Fetch Secret
        secret_object = client.secrets.get_secret_by_name(
            secret_name=secret_name,
            project_id=project_id,
            environment_slug=env_slug,
            secret_path="/"
        )
        
        # FIX: Use .secretValue (camelCase) instead of .secret_value
        return secret_object.secretValue

    except Exception as e:
        print(f"⚠️ Warning: Failed to fetch secret from Infisical: {e}")
        print("Falling back to manual entry...")
        return None

def sync_local_config(password: str):
    """
    Ensures the local secure config file exists and matches the Infisical password.
    This ensures that if Infisical goes down, the manual fallback will accept
    the correct password.
    """
    config_path = Path(SECURE_CONFIG_FILE)

    if not config_path.exists():
        print("Creating local recovery configuration from Infisical secret...")
        salt = generate_salt()
        key = derive_key(password, salt)
        key_verification = derive_key(base64.b64encode(key).decode(), salt)
        save_config(salt, key_verification)
    else:
        # Check integrity: Does the local file match the remote secret?
        with open(SECURE_CONFIG_FILE, 'rb') as f:
            data = f.read()
            salt, key_verification = data[:32], data[32:]
        
        if not verify_key(password, salt, key_verification):
            print("⚠️ WARNING: The password in Infisical does NOT match your local config file.")
            print("To fix this, you may need to delete the local config file and restart.")

# ==========================================
# 3. Main Logic
# ==========================================

def is_interactive() -> bool:
    """Check if we have an interactive TTY available."""
    return sys.stdin.isatty()

def get_encryption_key() -> str | None:
    """
    Retrieves encryption key.
    1. Try Infisical (Automated) - with retries if no TTY available
    2. Fallback to Manual Entry (only if TTY available)
    """
    
    is_headless = not is_interactive()
    retry_count = 0
    
    while True:
        # --- Attempt 1: Infisical ---
        infisical_pass = get_infisical_secret()

        if infisical_pass:
            print("✅ Successfully retrieved encryption key from Infisical.")
            # Sync local config so manual fallback works in future if Infisical dies
            sync_local_config(infisical_pass)
            return infisical_pass

        # --- Infisical failed ---
        
        # If running headless (no TTY), retry Infisical instead of falling back to manual
        if is_headless:
            retry_count += 1
            if retry_count >= INFISICAL_MAX_RETRIES:
                print(f"❌ FATAL: Infisical unavailable after {INFISICAL_MAX_RETRIES} retries and no TTY for manual input.")
                print("Please check your Infisical credentials and network connectivity.")
                # Return None to let the app handle graceful shutdown
                # The container will restart and try again
                return None
            
            print(f"⚠️ Infisical unavailable and no TTY for manual input. Retrying in {INFISICAL_RETRY_DELAY}s... ({retry_count}/{INFISICAL_MAX_RETRIES})")
            time.sleep(INFISICAL_RETRY_DELAY)
            continue
        
        # --- Attempt 2: Manual Fallback (only with TTY) ---
        break
    
    config_path = Path(SECURE_CONFIG_FILE)
    
    # Case A: Initial Setup (No Infisical, No Local Config)
    if not config_path.exists():
        print("Initial setup - please set your encryption password.")
        while True:
            password = getpass.getpass("Enter new encryption password: ")
            
            if password.lower() in ('0', 'exit', 'q'):
                return None

            if len(password) < 12:
                print("Password must be at least 12 characters long.")
                continue
                
            confirm = getpass.getpass("Confirm encryption password: ")
            if password != confirm:
                print("Passwords do not match.")
                continue
            
            salt = generate_salt()
            key = derive_key(password, salt)
            key_verification = derive_key(base64.b64encode(key).decode(), salt)
            save_config(salt, key_verification)
            
            del confirm # Clean up memory
            return password
    
    # Case B: Verify against Local Config
    with open(SECURE_CONFIG_FILE, 'rb') as f:
        data = f.read()
        salt, key_verification = data[:32], data[32:]
    
    max_attempts = 3
    for attempt in range(max_attempts):
        password = getpass.getpass("Enter encryption password: ")
        
        if password.lower() in ('0', 'exit', 'q'):
            return None

        if verify_key(password, salt, key_verification):
            return password

        remaining = max_attempts - attempt - 1
        if remaining > 0:
            print(f"Invalid password. {remaining} attempts remaining.")
    
    print("Maximum password attempts exceeded.")
    return None
