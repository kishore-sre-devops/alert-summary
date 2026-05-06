"""
Email Service for SMC-LAMA
Reuses existing SMTP configuration from alert_config table
Supports password reset, user notifications, etc.
"""
import smtplib
import logging
import secrets
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from app.db.db import engine
from sqlalchemy import text

logger = logging.getLogger(__name__)

def get_smtp_config():
    """
    Get SMTP configuration from alert_config table
    Returns SMTP settings or None if not configured
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT smtp_host, smtp_port, smtp_username, smtp_password, 
                           smtp_from_email, smtp_use_tls
                    FROM alert_config 
                    WHERE alert_channel = 'email' AND enabled = true
                    LIMIT 1
                """)
            ).fetchone()
            
            if not result:
                logger.warning("SMTP configuration not found or email alerts are disabled")
                return None
            
            # Decrypt password
            from app.utils.aes_encryption import decrypt_password
            
            return {
                'host': result[0],
                'port': result[1],
                'username': result[2],
                'password': decrypt_password(result[3]),
                'from_email': result[4],
                'use_tls': result[5] if result[5] is not None else True
            }
    except Exception as e:
        logger.error(f"Error getting SMTP config: {e}", exc_info=True)
        return None

def send_email(to_email: str, subject: str, body_html: str, body_text: str = None) -> bool:
    """
    Send email using configured SMTP settings
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body_html: HTML email body
        body_text: Plain text email body (optional, will use HTML if not provided)
    
    Returns:
        True if email sent successfully, False otherwise
    """
    smtp_config = get_smtp_config()
    if not smtp_config:
        logger.error("SMTP not configured. Please configure email alerts in Alert Configuration.")
        return False
    
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = smtp_config['from_email']
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Attach plain text version
        if body_text:
            msg.attach(MIMEText(body_text, 'plain'))
        else:
            # Create simple text version from HTML
            import re
            body_text = re.sub('<[^<]+?>', '', body_html)
            msg.attach(MIMEText(body_text, 'plain'))
        
        # Attach HTML version
        msg.attach(MIMEText(body_html, 'html'))
        
        # Send email with 5-second timeout to prevent hanging the API
        smtp_timeout = 5
        
        if smtp_config['use_tls']:
            with smtplib.SMTP(smtp_config['host'], smtp_config['port'], timeout=smtp_timeout) as server:
                server.starttls()
                server.login(smtp_config['username'], smtp_config['password'])
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_config['host'], smtp_config['port'], timeout=smtp_timeout) as server:
                server.login(smtp_config['username'], smtp_config['password'])
                server.send_message(msg)
        
        logger.info(f"Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}", exc_info=True)
        return False

def generate_password_reset_token() -> str:
    """Generate a secure random token for password reset"""
    return secrets.token_urlsafe(32)

def store_reset_token(user_id: int, token: str, expiry_minutes: int = 30):
    """
    Store password reset token in database
    Token expires after specified minutes
    """
    try:
        expiry_time = datetime.utcnow() + timedelta(minutes=expiry_minutes)
        
        with engine.connect() as conn:
            # Create password_reset_tokens table if it doesn't exist
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    token VARCHAR(255) NOT NULL UNIQUE,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """))
            conn.commit()
            
            # Invalidate any existing tokens for this user
            conn.execute(
                text("UPDATE password_reset_tokens SET used = true WHERE user_id = :user_id AND used = false"),
                {"user_id": user_id}
            )
            conn.commit()
            
            # Insert new token
            conn.execute(
                text("""
                    INSERT INTO password_reset_tokens (user_id, token, expires_at)
                    VALUES (:user_id, :token, :expires_at)
                """),
                {"user_id": user_id, "token": token, "expires_at": expiry_time}
            )
            conn.commit()
            
        logger.info(f"Password reset token stored for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error storing reset token: {e}", exc_info=True)
        return False

def verify_reset_token(token: str) -> dict:
    """
    Verify password reset token
    Returns user info if token is valid, None otherwise
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT prt.user_id, prt.expires_at, prt.used, u.email, u.full_name
                    FROM password_reset_tokens prt
                    JOIN users u ON prt.user_id = u.id
                    WHERE prt.token = :token
                """),
                {"token": token}
            ).fetchone()
            
            if not result:
                logger.warning("Password reset token not found")
                return None
            
            user_id, expires_at, used, email, full_name = result
            
            # Check if already used
            if used:
                logger.warning(f"Password reset token already used for user {user_id}")
                return None
            
            # Check if expired
            if datetime.utcnow() > expires_at:
                logger.warning(f"Password reset token expired for user {user_id}")
                return None
            
            return {
                'user_id': user_id,
                'email': email,
                'full_name': full_name
            }
            
    except Exception as e:
        logger.error(f"Error verifying reset token: {e}", exc_info=True)
        return None

def mark_token_as_used(token: str):
    """Mark password reset token as used"""
    try:
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE password_reset_tokens SET used = true WHERE token = :token"),
                {"token": token}
            )
            conn.commit()
        logger.info("Password reset token marked as used")
        return True
    except Exception as e:
        logger.error(f"Error marking token as used: {e}", exc_info=True)
        return False

def send_password_reset_email(user_email: str, user_name: str, reset_token: str, base_url: str) -> bool:
    """
    Send password reset email to user
    
    Args:
        user_email: User's email address
        user_name: User's full name
        reset_token: Password reset token
        base_url: Base URL of the application (e.g., https://smclama.smcindiaonline.com)
    """
    reset_url = f"{base_url}/reset-password?token={reset_token}"
    
    subject = "SMC-LAMA - Password Reset Request"
    
    body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
            border: 1px solid #ddd;
            border-radius: 5px;
        }}
        .header {{
            background-color: #5e35b1;
            color: white;
            padding: 20px;
            text-align: center;
            border-radius: 5px 5px 0 0;
        }}
        .content {{
            background-color: white;
            padding: 30px;
            border-radius: 0 0 5px 5px;
        }}
        .button {{
            display: inline-block;
            padding: 12px 30px;
            background-color: #5e35b1;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            margin: 20px 0;
        }}
        .warning {{
            background-color: #fff3cd;
            border: 1px solid #ffc107;
            padding: 10px;
            border-radius: 5px;
            margin: 20px 0;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔒 Password Reset Request</h1>
        </div>
        <div class="content">
            <p>Hello {user_name},</p>
            
            <p>We received a request to reset your password for your SMC-LAMA account.</p>
            
            <p>Click the button below to reset your password:</p>
            
            <center>
                <a href="{reset_url}" class="button">Reset Password</a>
            </center>
            
            <p>Or copy and paste this link into your browser:</p>
            <p style="word-break: break-all; color: #5e35b1;">{reset_url}</p>
            
            <div class="warning">
                <strong>⚠️ Important:</strong>
                <ul>
                    <li>This link will expire in <strong>30 minutes</strong></li>
                    <li>For security reasons, this link can only be used once</li>
                    <li>If you didn't request this reset, please ignore this email</li>
                </ul>
            </div>
            
            <p>If you need assistance, please contact your system administrator.</p>
            
            <p>Best regards,<br>
            SMC-LAMA Team</p>
        </div>
        <div class="footer">
            <p>This is an automated email from SMC-LAMA. Please do not reply to this email.</p>
            <p>&copy; 2025 SMC India Online. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
    """
    
    body_text = f"""
SMC-LAMA - Password Reset Request

Hello {user_name},

We received a request to reset your password for your SMC-LAMA account.

Click the link below to reset your password:
{reset_url}

IMPORTANT:
- This link will expire in 30 minutes
- For security reasons, this link can only be used once
- If you didn't request this reset, please ignore this email

If you need assistance, please contact your system administrator.

Best regards,
SMC-LAMA Team

---
This is an automated email from SMC-LAMA. Please do not reply to this email.
© 2025 SMC India Online. All rights reserved.
    """
    
    return send_email(user_email, subject, body_html, body_text)

def cleanup_expired_tokens():
    """
    Clean up expired password reset tokens
    Should be called periodically (e.g., daily via scheduler)
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    DELETE FROM password_reset_tokens 
                    WHERE expires_at < CURRENT_TIMESTAMP OR used = true
                """)
            )
            conn.commit()
            deleted_count = result.rowcount
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired/used password reset tokens")
            return True
    except Exception as e:
        logger.error(f"Error cleaning up expired tokens: {e}", exc_info=True)
        return False

def generate_otp() -> str:
    """Generate a 6-digit OTP"""
    import string
    # Generate 6 digit numeric OTP
    return ''.join(secrets.choice(string.digits) for _ in range(6))

def store_otp(user_id: int, otp: str, expiry_minutes: int = 10):
    """
    Store OTP in database
    """
    try:
        expiry_time = datetime.utcnow() + timedelta(minutes=expiry_minutes)
        
        with engine.connect() as conn:
            # Create user_otps table if it doesn't exist
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_otps (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    otp VARCHAR(10) NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """))
            conn.commit()
            
            # Invalidate any existing OTPs for this user
            conn.execute(
                text("UPDATE user_otps SET used = true WHERE user_id = :user_id AND used = false"),
                {"user_id": user_id}
            )
            conn.commit()
            
            # Insert new OTP
            conn.execute(
                text("""
                    INSERT INTO user_otps (user_id, otp, expires_at)
                    VALUES (:user_id, :otp, :expires_at)
                """),
                {"user_id": user_id, "otp": otp, "expires_at": expiry_time}
            )
            conn.commit()
            
        logger.info(f"OTP stored for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error storing OTP: {e}", exc_info=True)
        return False

def verify_otp(user_id: int, otp: str) -> bool:
    """
    Verify OTP
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, expires_at, used
                    FROM user_otps
                    WHERE user_id = :user_id AND otp = :otp
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"user_id": user_id, "otp": otp}
            ).fetchone()
            
            if not result:
                logger.warning(f"OTP not found or incorrect for user {user_id}")
                return False
            
            otp_id, expires_at, used = result
            
            # Check if already used
            if used:
                logger.warning(f"OTP already used for user {user_id}")
                return False
            
            # Check if expired
            if datetime.utcnow() > expires_at:
                logger.warning(f"OTP expired for user {user_id}")
                return False
            
            # Mark as used
            conn.execute(
                text("UPDATE user_otps SET used = true WHERE id = :id"),
                {"id": otp_id}
            )
            conn.commit()
            
            return True
            
    except Exception as e:
        logger.error(f"Error verifying OTP: {e}", exc_info=True)
        return False

def send_otp_email(user_email: str, otp: str) -> bool:
    """Send OTP email to user"""
    subject = "SMC-LAMA - Login Verification Code"
    
    body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border: 1px solid #ddd; border-radius: 5px; }}
        .header {{ background-color: #5e35b1; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
        .content {{ background-color: white; padding: 30px; border-radius: 0 0 5px 5px; text-align: center; }}
        .otp-code {{ font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #5e35b1; margin: 20px 0; padding: 10px; background: #f0f0f0; border-radius: 5px; display: inline-block; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔐 Login Verification</h1>
        </div>
        <div class="content">
            <p>Hello,</p>
            <p>Please use the verification code below to complete your login:</p>
            
            <div class="otp-code">{otp}</div>
            
            <p>This code will expire in 10 minutes.</p>
            <p>If you did not attempt to login, please contact your administrator immediately.</p>
        </div>
        <div class="footer">
            <p>This is an automated email from SMC-LAMA. Please do not reply.</p>
        </div>
    </div>
</body>
</html>
    """
    
    body_text = f"Your SMC-LAMA Verification Code is: {otp}\\n\\nThis code expires in 10 minutes."
    
    return send_email(user_email, subject, body_html, body_text)
