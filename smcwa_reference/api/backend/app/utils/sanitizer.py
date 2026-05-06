"""
XSS Sanitization utility - Prevents HTML/JS injection in string inputs
"""
import re
import html

def sanitize_string(text: str) -> str:
    """
    Sanitize a string by:
    1. Escaping HTML special characters
    2. Removing potential script tags and event handlers
    """
    if not text or not isinstance(text, str):
        return text
        
    # Escape HTML special characters (&, <, >, ", ')
    sanitized = html.escape(text)
    
    # Remove common XSS patterns that might bypass simple escaping
    # (e.g., javascript: links, data: URIs in certain contexts)
    sanitized = re.sub(r'javascript:', '', sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r'data:', '', sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r'vbscript:', '', sanitized, flags=re.IGNORECASE)
    
    return sanitized

def sanitize_dict(data: dict) -> dict:
    """Recursively sanitize all string values in a dictionary"""
    if not data:
        return data
        
    new_data = {}
    for key, value in data.items():
        if isinstance(value, str):
            new_data[key] = sanitize_string(value)
        elif isinstance(value, dict):
            new_data[key] = sanitize_dict(value)
        elif isinstance(value, list):
            new_data[key] = [sanitize_string(v) if isinstance(v, str) else 
                             (sanitize_dict(v) if isinstance(v, dict) else v) 
                             for v in value]
        else:
            new_data[key] = value
    return new_data
