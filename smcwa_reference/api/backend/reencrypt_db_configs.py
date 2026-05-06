
import os
import sys
import base64
import logging
from cryptography.fernet import Fernet
from sqlalchemy import text

# Add parent dir to path to import app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.db import engine

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reencrypt")

def get_key_from_string(key_str: str):
    key_bytes = key_str.encode()[:32].ljust(32, b'0')
    return base64.urlsafe_b64encode(key_bytes)

# Possible keys to try for decryption
OLD_KEYS = [
    "default-key-change-in-production",
    "smc-lama-integration-v1-key",
    # Add any other known old keys here
]

CURRENT_KEY_STR = os.getenv("ENCRYPTION_KEY", "default-key-change-in-production")
CURRENT_KEY = get_key_from_string(CURRENT_KEY_STR)
f_current = Fernet(CURRENT_KEY)

def reencrypt():
    with engine.connect() as conn:
        # Fetch all database configurations
        results = conn.execute(text("SELECT id, host, password FROM database_config")).fetchall()
        
        fixed_count = 0
        already_correct = 0
        failed_count = 0
        
        for row in results:
            db_id, host, encrypted_password = row
            if not encrypted_password or encrypted_password == 'N/A':
                continue
                
            decrypted = None
            
            # 1. Try current key
            try:
                decrypted = f_current.decrypt(encrypted_password.encode()).decode()
                already_correct += 1
                logger.info(f"DB {db_id} ({host}): Already correct")
                continue
            except Exception:
                pass
                
            # 2. Try old keys
            for old_key_str in OLD_KEYS:
                try:
                    f_old = Fernet(get_key_from_string(old_key_str))
                    decrypted = f_old.decrypt(encrypted_password.encode()).decode()
                    logger.info(f"DB {db_id} ({host}): Decrypted with old key '{old_key_str[:8]}...'")
                    break
                except Exception:
                    continue
            
            if decrypted:
                # Re-encrypt with current key
                new_encrypted = f_current.encrypt(decrypted.encode()).decode()
                conn.execute(
                    text("UPDATE database_config SET password = :pwd WHERE id = :id"),
                    {"pwd": new_encrypted, "id": db_id}
                )
                conn.commit()
                fixed_count += 1
                logger.info(f"DB {db_id} ({host}): RE-ENCRYPTED SUCCESS")
            else:
                failed_count += 1
                logger.error(f"DB {db_id} ({host}): FAILED to decrypt with any known key")
                
        logger.info(f"SUMMARY: Total={len(results)}, Fixed={fixed_count}, Already Correct={already_correct}, Failed={failed_count}")

if __name__ == "__main__":
    reencrypt()
