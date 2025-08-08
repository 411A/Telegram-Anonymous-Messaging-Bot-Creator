import getpass
import secrets
import base64
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from configs.settings import SECURE_CONFIG_FILE

def generate_salt() -> bytes:
    return secrets.token_bytes(32)

def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return kdf.derive(password.encode())

def save_config(salt: bytes, key_verification: bytes):
    with open(SECURE_CONFIG_FILE, 'wb') as f:
        f.write(salt + key_verification)

def verify_key(password: str, salt: bytes, key_verification: bytes) -> bool:
    derived_key = derive_key(password, salt)
    return secrets.compare_digest(
        derive_key(base64.b64encode(derived_key).decode(), salt),
        key_verification
    )

def get_encryption_key() -> str | None:
    config_path = Path(SECURE_CONFIG_FILE)
    
    if not config_path.exists():
        print("Initial setup - please set your encryption password (or enter '0' or 'exit' or 'q' to quit).")
        while True:
            password = getpass.getpass("Enter new encryption password: ")
            
            # Check for exit condition
            if password.lower() in ('0', 'exit', 'q'):
                print("Setup cancelled. Exiting.")
                return None

            if len(password) < 12:
                print("Password must be at least 12 characters long.")
                continue
                
            confirm = getpass.getpass("Confirm encryption password: ")
            if password != confirm:
                print("Passwords do not match. Please try again.")
                continue
            
            salt = generate_salt()
            key = derive_key(password, salt)
            # Store key verification data
            key_verification = derive_key(base64.b64encode(key).decode(), salt)
            save_config(salt, key_verification)
            return password
    
    with open(SECURE_CONFIG_FILE, 'rb') as f:
        data = f.read()
        salt, key_verification = data[:32], data[32:]
    
    max_attempts = 3
    for attempt in range(max_attempts):
        password = getpass.getpass("Enter encryption password (or '0' or 'exit' or 'q' to quit): ")

        # Check for exit condition
        if password.lower() in ('0', 'exit', 'q'):
            print("Exiting.")
            return None

        if verify_key(password, salt, key_verification):
            return password
        remaining = max_attempts - attempt - 1
        if remaining > 0:
            print(f"Invalid password. {remaining} attempts remaining.")

    # If all attempts fail, return None to signal failure
    print("Maximum password attempts exceeded.")
    return None
