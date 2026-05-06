#!/usr/bin/env python3
"""
AES Password Encryption Script for LAMA API Testing
Encrypts password using AES with the provided secret key
"""

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
import base64
import sys

def encrypt_password(password: str, secret_key_b64: str) -> str:
    """
    Encrypt password using AES-ECB mode with PKCS7 padding (as per LAMA Exchange API requirements).
    
    Args:
        password: Plain text password to encrypt
        secret_key_b64: Base64 encoded secret key
        
    Returns:
        Base64 encoded encrypted password
    """
    # Decode secret key
    try:
        secret_key = base64.b64decode(secret_key_b64)
    except Exception as e:
        raise ValueError(f"Invalid base64 secret key: {e}")
    
    # Validate key length (AES requires 16, 24, or 32 bytes)
    key_length = len(secret_key)
    if key_length not in [16, 24, 32]:
        raise ValueError(f"Invalid key length: {key_length} bytes. AES requires 16, 24, or 32 bytes.")
    
    # Select AES algorithm based on key length
    if key_length == 32:
        algorithm = algorithms.AES(secret_key)
        aes_type = "AES-256-ECB"
    elif key_length == 24:
        algorithm = algorithms.AES(secret_key)
        aes_type = "AES-192-ECB"
    else:  # 16 bytes
        algorithm = algorithms.AES(secret_key)
        aes_type = "AES-128-ECB"
    
    # Convert password to bytes
    password_bytes = password.encode('utf-8')
    
    # Create cipher with AES-ECB mode (no IV needed for ECB)
    backend = default_backend()
    cipher = Cipher(algorithm, modes.ECB(), backend)
    encryptor = cipher.encryptor()
    
    # Apply PKCS7 padding
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(password_bytes) + padder.finalize()
    
    # Encrypt
    encrypted_bytes = encryptor.update(padded_data) + encryptor.finalize()
    
    # Return Base64-encoded encrypted password
    encrypted_password = base64.b64encode(encrypted_bytes).decode('utf-8')
    
    return encrypted_password, aes_type

def decrypt_password(encrypted_b64: str, secret_key_b64: str) -> str:
    """
    Decrypt password using AES-ECB mode with PKCS7 padding.
    
    Args:
        encrypted_b64: Base64 encoded encrypted password
        secret_key_b64: Base64 encoded secret key
        
    Returns:
        Decrypted plain text password
    """
    # Decode secret key
    try:
        secret_key = base64.b64decode(secret_key_b64)
    except Exception as e:
        raise ValueError(f"Invalid base64 secret key: {e}")
    
    # Decode encrypted data
    try:
        encrypted_bytes = base64.b64decode(encrypted_b64)
    except Exception as e:
        raise ValueError(f"Invalid base64 encrypted data: {e}")
    
    # Create cipher with AES-ECB mode
    backend = default_backend()
    cipher = Cipher(algorithms.AES(secret_key), modes.ECB(), backend)
    decryptor = cipher.decryptor()
    
    # Decrypt
    padded_data = decryptor.update(encrypted_bytes) + decryptor.finalize()
    
    # Remove PKCS7 padding
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    password_bytes = unpadder.update(padded_data) + unpadder.finalize()
    
    return password_bytes.decode('utf-8')

if __name__ == "__main__":
    # LAMA API credentials
    MEMBER_ID = "07714"
    LOGIN_ID = "apim_07714_9"
    PASSWORD = "@Smcltd12345"
    SECRET_KEY_B64 = "1bw71c9+AXTsu2VVHJNzJkmq9EFXGAI3XouySpjss2Y="
    
    print("=" * 60)
    print("LAMA API Password Encryption")
    print("=" * 60)
    print(f"\nMember ID: {MEMBER_ID}")
    print(f"Login ID: {LOGIN_ID}")
    print(f"Password: {PASSWORD}")
    print(f"Secret Key (base64): {SECRET_KEY_B64}")
    print("\n" + "-" * 60)
    
    try:
        # Encrypt password
        encrypted_password, aes_type = encrypt_password(PASSWORD, SECRET_KEY_B64)
        
        print(f"\n✅ Encryption Successful ({aes_type})")
        print(f"\nEncrypted Password (base64):")
        print(f"{encrypted_password}")
        print("\n" + "-" * 60)
        
        # Verify by decrypting
        decrypted = decrypt_password(encrypted_password, SECRET_KEY_B64)
        print(f"\n✅ Verification: Decrypted password matches original: {decrypted == PASSWORD}")
        
        print("\n" + "=" * 60)
        print("📋 For Postman Testing:")
        print("=" * 60)
        print(f"\nUse this encrypted password in your API request:")
        print(f"  \"password\": \"{encrypted_password}\"")
        print(f"\nFull request body example:")
        print(f"{{")
        print(f"  \"member_id\": \"{MEMBER_ID}\",")
        print(f"  \"login_id\": \"{LOGIN_ID}\",")
        print(f"  \"password\": \"{encrypted_password}\"")
        print(f"}}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

