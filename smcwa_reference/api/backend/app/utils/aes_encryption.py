# api/backend/app/utils/aes_encryption.py
"""
AES Encryption utility for LAMA Exchange password encryption
Uses AES-ECB mode with Base64-encoded key as per Exchange requirements

CRITICAL: 
- User must enter PLAIN TEXT password (e.g., "@Smcltd12345")
- This module encrypts it before sending to LAMA API
- NEVER enter already-encrypted password - it will be double-encrypted!
"""

import base64
import re
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import logging

logger = logging.getLogger(__name__)

# LAMA Exchange AES Key (Base64 encoded)
LAMA_AES_KEY = "DOqWxmnwif2nHdxrW+gPO394LT6hcOu/0MlVOJOEuhw="


def is_likely_encrypted(password: str) -> bool:
    """
    Check if a password looks like it's already Base64-encoded (AES encrypted).
    
    CRITICAL: This helps detect the DOUBLE ENCRYPTION BUG where users accidentally
    enter already-encrypted passwords (from Postman) instead of plain text.
    
    Signs of an already-encrypted password:
    - Ends with '=' or '==' (Base64 padding)
    - Contains only Base64 characters (A-Za-z0-9+/=_-)
    - Length is a multiple of 4 (Base64 encoding)
    - Length >= 16 (AES output is at least 16 bytes, Base64 is 24+ chars)
    
    Args:
        password: The password string to check
        
    Returns:
        True if password looks like it's already encrypted, False otherwise
    """
    if not password:
        return False
    
    # Check for Base64 padding (common in encrypted passwords)
    has_padding = password.endswith('=') or password.endswith('==')
    
    # Check if contains only Base64 characters (including URL-safe variants)
    base64_pattern = r'^[A-Za-z0-9+/=_-]+$'
    is_base64_chars = bool(re.match(base64_pattern, password))
    
    # Check length (AES encrypted Base64 is typically 24+ chars for short passwords)
    is_long_enough = len(password) >= 20
    
    # Check if length is multiple of 4 (Base64 property)
    is_base64_length = len(password) % 4 == 0
    
    # If it has Base64 characteristics, it's likely already encrypted
    is_encrypted = has_padding and is_base64_chars and is_long_enough and is_base64_length
    
    if is_encrypted:
        logger.warning(f"[AES] ⚠️ Password appears to be already Base64-encoded/encrypted!")
        logger.warning(f"[AES] ⚠️ Length={len(password)}, ends_with_padding={has_padding}")
        logger.warning(f"[AES] ⚠️ User should enter PLAIN TEXT password, not the encrypted version!")
    
    return is_encrypted


def encrypt_password(raw_password: str, secret_key: str = None) -> str:
    """
    Encrypt password using AES-ECB mode with PKCS7 padding
    
    PROFESSIONAL DESIGN:
    - User enters PLAIN TEXT password in UI
    - This function encrypts it for storage in DB
    - DB stores encrypted password (ready for LAMA API)
    - When displaying, we decrypt back to plain text
    
    Args:
        raw_password: Plain text password to encrypt
        secret_key: Secret key (Base64 encoded). If not provided, uses default LAMA_AES_KEY
        
    Returns:
        Base64-encoded encrypted password string
    """
    try:
        # Use provided secret_key or default
        key_b64 = secret_key if secret_key else LAMA_AES_KEY
        # Decode the Base64 key
        key = base64.b64decode(key_b64)
        
        # Convert password to bytes
        password_bytes = raw_password.encode('utf-8')
        
        # Create cipher with AES-ECB mode
        backend = default_backend()
        cipher = Cipher(algorithms.AES(key), modes.ECB(), backend)
        encryptor = cipher.encryptor()
        
        # Apply PKCS7 padding
        padder = padding.PKCS7(algorithms.AES.block_size).padder()
        padded_data = padder.update(password_bytes) + padder.finalize()
        
        # Encrypt
        encrypted_bytes = encryptor.update(padded_data) + encryptor.finalize()
        
        # CRITICAL: Use URL-safe Base64 encoding (replaces + with - and / with _)
        # LAMA Exchange API requires URL-safe Base64 format
        encrypted_password = base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8')
        
        logger.info(f"[AES] Password encrypted (plain: {len(raw_password)} chars → encrypted: {len(encrypted_password)} chars, URL-safe)")
        return encrypted_password
        
    except Exception as e:
        logger.error(f"Error encrypting password: {e}", exc_info=True)
        raise ValueError(f"Failed to encrypt password: {str(e)}")


def decrypt_password(encrypted_password: str, secret_key: str = None) -> str:
    """
    Decrypt password using AES-ECB mode with PKCS7 padding
    
    Args:
        encrypted_password: Base64-encoded encrypted password string
        secret_key: Optional secret key (Base64 encoded). If not provided, uses default LAMA_AES_KEY
        
    Returns:
        Plain text password
    """
    try:
        # Use provided secret_key or default
        key_b64 = secret_key if secret_key else LAMA_AES_KEY
        # Decode the Base64 key
        key = base64.b64decode(key_b64)
        
        # CRITICAL: Decode URL-safe Base64 (handles both + and - , / and _)
        # LAMA Exchange stores passwords in URL-safe Base64 format
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_password)
        
        # Create cipher with AES-ECB mode
        backend = default_backend()
        cipher = Cipher(algorithms.AES(key), modes.ECB(), backend)
        decryptor = cipher.decryptor()
        
        # Decrypt
        padded_data = decryptor.update(encrypted_bytes) + decryptor.finalize()
        
        # Remove PKCS7 padding
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        password_bytes = unpadder.update(padded_data) + unpadder.finalize()
        
        # Return plain text password
        password = password_bytes.decode('utf-8')
        
        logger.debug(f"Password decrypted successfully")
        return password
        
    except Exception as e:
        logger.error(f"Error decrypting password: {e}", exc_info=True)
        raise ValueError(f"Failed to decrypt password: {str(e)}")

