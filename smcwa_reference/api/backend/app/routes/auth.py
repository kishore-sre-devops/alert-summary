from fastapi import APIRouter, HTTPException, Depends, Header, Request, Response
from pydantic import BaseModel
from typing import Optional
from app.db.db import engine, users_table, get_db
from sqlalchemy import select
from sqlalchemy.orm import Session
import bcrypt
import os
import logging
from datetime import datetime, timedelta
from jose import JWTError, jwt
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import secrets
import string

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/test")
def test_auth_route():
    """Test endpoint to verify auth router is working"""
    return {"status": "auth router is working"}

JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("JWT_SECRET_PROD", "your-secret-key-change-in-prod"))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

class LoginRequest(BaseModel):
    email: str = None
    mobile: str = None
    password: str

class LoginResponse(BaseModel):
    token: Optional[str] = None
    user_email: str
    user_id: Optional[int] = None
    role: Optional[str] = None
    group_name: Optional[str] = None # Added for mobile profile visibility
    user: Optional[dict] = None
    otp_required: bool = False
    message: Optional[str] = None

def get_user_groups(user_id: int) -> str:
    """Fetch all groups (escalation policies) a user belongs to"""
    try:
        from app.models.mobile import escalation_policies_table
        with engine.connect() as conn:
            policies = conn.execute(select(escalation_policies_table)).fetchall()
            groups = []
            for p in policies:
                policy_data = dict(p._mapping)
                steps = policy_data.get("steps", [])

                # Robust JSON handling: Convert string to list if necessary
                if isinstance(steps, str):
                    try:
                        import json
                        steps = json.loads(steps)
                    except: steps = []

                if isinstance(steps, list):
                    for step in steps:
                        if isinstance(step, dict):
                            notify_list = step.get("notify", [])
                            if user_id in notify_list or str(user_id) in [str(uid) for uid in notify_list]:
                                groups.append(policy_data.get("name", "Unknown"))
                                break # Move to next policy

            return f"Group {', '.join(groups)}" if groups else None
    except Exception as e:
        logger.error(f"Error fetching user groups: {e}")
        return None

class VerifyOtpRequest(BaseModel):
    email: str
    otp: str

class GoogleLoginRequest(BaseModel):
    token: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: str = "user"
    full_name: str = ""

class UpdateUserRequest(BaseModel):
    full_name: str = None
    mobile: str = None
    role: str = None

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

def create_jwt_token(user_id: int, email: str, role: str) -> str:
    """Generate JWT token with 24-hour expiration"""
    expiration = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "exp": expiration
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token

def authenticate_user_db(email_or_mobile: str, password: str):
    """Authenticate user from database - supports both email and mobile login"""
    try:
        logger.info(f"Attempting to authenticate: {email_or_mobile}")
        # FIX: Use context manager for automatic connection cleanup
        with engine.connect() as conn:
            # Try to find user by email or mobile
            query = select(users_table).where(
                (users_table.c.email == email_or_mobile) | 
                (users_table.c.mobile == email_or_mobile)
            )
            result = conn.execute(query).fetchone()

            logger.info(f"Query result: {result is not None}")
            if not result:
                logger.warning(f"User not found: {email_or_mobile}")
                return None

            # Check if user is active
            # Access by index: 6=is_active (if it exists)
            is_active = True
            try:
                # Based on users_table definition in db.py
                # 0=id, 1=email, 2=mobile, 3=password, 4=full_name, 5=role, 6=is_active
                if len(result) > 6:
                    is_active = result[6]
            except:
                pass

            if not is_active:
                logger.warning(f"Login attempt for disabled account: {email_or_mobile}")
                return None

            # result columns: id, email, mobile, password, full_name, role, created_at, updated_at
            # Access by index: 0=id, 1=email, 2=mobile, 3=password, 4=full_name, 5=role
            stored_password = result[3]
            # CRITICAL FIX BUG-014: Remove password hash from logs (security)
            # Only log that password exists, not the actual hash
            logger.info(f"Stored password hash exists: {bool(stored_password)} (hash length: {len(stored_password) if stored_password else 0})")

            # Check password - handle both string and bytes
            password_match = False
            try:
                # Normalize stored password to string if needed
                if isinstance(stored_password, bytes):
                    stored_password_str = stored_password.decode('utf-8')
                else:
                    stored_password_str = str(stored_password)

                # Ensure it's a valid bcrypt hash
                if stored_password_str.startswith('$2'):
                    # Valid bcrypt hash
                    password_match = bcrypt.checkpw(password.encode('utf-8'), stored_password_str.encode('utf-8'))
                else:
                    logger.warning(f"Invalid password hash format for user: {email_or_mobile}")
                    password_match = False
            except Exception as e:
                logger.error(f"Password check error: {e}", exc_info=True)
                password_match = False

            logger.info(f"Password match: {password_match}")

            if password_match:
                user_data = {
                    'id': result[0],
                    'email': result[1] or result[2],  # Use email if available, else mobile
                    'role': result[5]
                }
                logger.info(f"Authentication successful for: {email_or_mobile}")
                return user_data
            logger.warning(f"Password mismatch for: {email_or_mobile}")
            return None
    except Exception as e:
        logger.error(f"Database authentication error: {e}", exc_info=True)
        import traceback
        logger.error(traceback.format_exc())
        return None

@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, request: Request, response: Response, environment: str = None):
    """Authenticate user and initiate OTP flow"""
    # Import rate limiter
    from app.utils.rate_limiter import rate_limiter
    
    # Check rate limit BEFORE processing login
    rate_limiter.check_rate_limit(request)
    
    import sys
    email_or_mobile = data.email or data.mobile
    # Try authenticating via multiple methods (Email, Mobile)
    user = None
    logger.info(f"Login attempt for: {email_or_mobile}")
    
    if not data.password:
        raise HTTPException(status_code=400, detail="Password required")
    
    if not email_or_mobile:
        raise HTTPException(status_code=400, detail="Email or mobile required")
    
    # Try database first
    logger.info("Trying database authentication...")
    user = authenticate_user_db(email_or_mobile, data.password)
    
    if not user:
        # Failed login - record attempt for rate limiting
        ip_address = rate_limiter.get_client_ip(request)
        rate_limiter.record_failed_attempt(ip_address)
        
        logger.warning(f"All authentication methods failed for: {email_or_mobile}")
        raise HTTPException(status_code=401, detail="Invalid email/mobile or password")
    
    # Successful credentials check
    
    # Check if SMTP is configured - If not, bypass OTP (prevent lockout on fresh install)
    from app.utils.email_service import get_smtp_config
    smtp_config = get_smtp_config()
    
    if not smtp_config:
        logger.warning(f"SMTP not configured - skipping OTP for user {email_or_mobile}")
        
        # Clear failed attempts
        ip_address = rate_limiter.get_client_ip(request)
        rate_limiter.clear_failed_attempts(ip_address)
        
        # Generate token directly
        token = create_jwt_token(user['id'], user['email'], user['role'])

        # VAPT FIX: Set HttpOnly cookie for extra security
        response.set_cookie(
            key="lama_session",
            value=token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=JWT_EXPIRATION_HOURS * 3600,
            path="/"
        )

        # Log login activity
        try:
            from app.utils.activity_logger import log_login
            log_login(user['id'], user['email'], success=True, request=request)
        except Exception as e:
            logger.warning(f"Failed to log login activity: {e}")
            
        return LoginResponse(
            token=token,
            user_email=user['email'],
            user_id=user['id'],
            role=user['role'],
            group_name=get_user_groups(user['id']),
            user={
                'email': user['email'],
                'id': user['id'],
                'role': user['role']
            },
            otp_required=False,
            message="Login successful"
        )
    
    # SMTP Configured - Send OTP
    try:
        from app.utils.email_service import generate_otp, store_otp, send_otp_email
        
        otp = generate_otp()
        if store_otp(user['id'], otp):
            # Send Email
            if send_otp_email(user['email'], otp):
                logger.info(f"OTP sent to {user['email']}")
                return LoginResponse(
                    user_email=user['email'],
                    otp_required=True,
                    message="Verification code sent to your email"
                )
            else:
                raise HTTPException(status_code=500, detail="Failed to send verification email. Please contact support.")
        else:
            raise HTTPException(status_code=500, detail="System error: Failed to generate verification code.")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OTP generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error initiating login verification")

@router.post("/verify-otp-login", response_model=LoginResponse)
def verify_otp_login(data: VerifyOtpRequest, request: Request, response: Response):
    """Verify OTP and return JWT token"""
    from app.utils.rate_limiter import rate_limiter
    from app.utils.email_service import verify_otp

    try:
        # Find user by email
        with engine.connect() as conn:
            query = select(users_table).where(users_table.c.email == data.email)
            result = conn.execute(query).fetchone()

            if not result:
                raise HTTPException(status_code=400, detail="User not found")

            user_id = result[0]
            user_role = result[5]

            # Verify OTP
            if verify_otp(user_id, data.otp):
                # Success - Generate Token
                token = create_jwt_token(user_id, data.email, user_role)

                # VAPT FIX: Set HttpOnly cookie for extra security
                response.set_cookie(
                    key="lama_session",
                    value=token,
                    httponly=True,
                    secure=True,
                    samesite="strict",
                    max_age=JWT_EXPIRATION_HOURS * 3600,
                    path="/"
                )

                # Log login activity
                try:
                    from app.utils.activity_logger import log_login
                    log_login(user_id, data.email, success=True, request=request)
                except Exception as e:
                    logger.warning(f"Failed to log login activity: {e}")
                
                # Clear any failed attempts for this IP
                ip_address = rate_limiter.get_client_ip(request)
                rate_limiter.clear_failed_attempts(ip_address)
                
                return LoginResponse(
                    token=token,
                    user_email=data.email,
                    user_id=user_id,
                    role=user_role,
                    group_name=get_user_groups(user_id),
                    user={
                        'email': data.email,
                        'id': user_id,
                        'role': user_role
                    },
                    otp_required=False,
                    message="Login successful"
                )
            else:
                # Failed OTP
                ip_address = rate_limiter.get_client_ip(request)
                rate_limiter.record_failed_attempt(ip_address)
                raise HTTPException(status_code=400, detail="Invalid or expired verification code")
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OTP verification error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error verifying code")

@router.post("/google-login", response_model=LoginResponse)
def google_login(data: GoogleLoginRequest, request: Request, response: Response):
    """Authenticate user via Google Identity Services"""
    from app.utils.rate_limiter import rate_limiter
    
    # Check rate limit
    rate_limiter.check_rate_limit(request)
    
    try:
        # Verify Google Token
        # We don't strictly enforce the client ID check here if we want to allow multiple clients,
        # but for security it's best to match the one we expect.
        # Since the frontend sends the token, and we want to verify it was issued for us:
        CLIENT_ID = "655248995621-mf0gp9tb3omc7dfjr71kft8qr30ucjr2.apps.googleusercontent.com"
        
        id_info = id_token.verify_oauth2_token(
            data.token, 
            google_requests.Request(), 
            CLIENT_ID
        )

        email = id_info.get('email')
        if not email:
            raise HTTPException(status_code=400, detail="Google token does not contain email")
        
        # RESTRICTION: Only allow @smcindiaonline.com domain for Google Login
        if not email.endswith('@smcindiaonline.com'):
            logger.warning(f"Unauthorized domain login attempt via Google: {email}")
            raise HTTPException(
                status_code=403, 
                detail="Login allowed only for @smcindiaonline.com accounts"
            )
        
        # Check if email is verified by Google
        if not id_info.get('email_verified'):
            raise HTTPException(status_code=400, detail="Google email not verified")

        # Check if user exists in our DB
        with engine.connect() as conn:
            query = select(users_table).where(users_table.c.email == email)
            result = conn.execute(query).fetchone()
            
            user_id = None
            role = "user"
            
            if result:
                # User exists
                user_id = result[0]
                role = result[5]
                
                # Log login
                try:
                    from app.utils.activity_logger import log_login
                    log_login(user_id, email, success=True, request=request)
                except Exception as e:
                    logger.warning(f"Failed to log login activity: {e}")
                    
            else:
                # User does not exist - Create new user
                logger.info(f"Creating new user from Google Login: {email}")
                
                # Generate a random strong password (user won't know it, they login via Google)
                alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
                password = ''.join(secrets.choice(alphabet) for i in range(20))
                hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                
                full_name = id_info.get('name') or email.split('@')[0]
                
                # Insert new user
                try:
                    insert_query = users_table.insert().values(
                        email=email,
                        password=hashed_password,
                        full_name=full_name,
                        role="user", # Default role
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    conn.execute(insert_query)
                    conn.commit()
                    
                    # Fetch the newly created user
                    query_new = select(users_table).where(users_table.c.email == email)
                    new_user = conn.execute(query_new).fetchone()
                    
                    if not new_user:
                        raise Exception("Failed to retrieve newly created user")
                        
                    user_id = new_user[0]
                    role = new_user[5]
                    
                    logger.info(f"Successfully created new user: {email} (ID: {user_id})")
                    
                    try:
                        from app.utils.activity_logger import log_login
                        log_login(user_id, email, success=True, request=request)
                    except Exception as e:
                        logger.warning(f"Failed to log login activity: {e}")
                        
                except Exception as e:
                    logger.error(f"Database error during user creation for {email}: {str(e)}")
                    # Try to see if it failed because of race condition (user created by another request)
                    # If so, try to select again
                    query_retry = select(users_table).where(users_table.c.email == email)
                    result_retry = conn.execute(query_retry).fetchone()
                    if result_retry:
                        user_id = result_retry[0]
                        role = result_retry[5]
                        logger.info(f"User {email} was created by another process, proceeding.")
                    else:
                        raise HTTPException(status_code=500, detail="Failed to create user account")

            # Generate JWT Token
            token = create_jwt_token(user_id, email, role)
            
            # VAPT FIX: Set HttpOnly cookie for extra security
            response.set_cookie(
                key="lama_session",
                value=token,
                httponly=True,
                secure=True, # Should be True in production with HTTPS
                samesite="strict",
                max_age=JWT_EXPIRATION_HOURS * 3600,
                path="/"
            )
            
            # Clear rate limits on success
            ip_address = rate_limiter.get_client_ip(request)
            rate_limiter.clear_failed_attempts(ip_address)
            
            return LoginResponse(
                token=token,
                user_email=email,
                user_id=user_id,
                role=role,
                group_name=get_user_groups(user_id),
                user={
                    'email': email,
                    'id': user_id,
                    'role': role
                },
                otp_required=False,
                message="Login successful"
            )

    except HTTPException:
        raise
    except ValueError as e:
        # Invalid token
        logger.warning(f"Google token validation failed: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {str(e)}")
    except Exception as e:
        logger.error(f"Google login error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing Google login: {str(e)}")

@router.post("/verify")
def verify_token(request: Request, token: str = None):
    """Verify JWT token validity from parameter, header, or cookie"""
    if not token:
        # Check cookie
        token = request.cookies.get("lama_session")
    
    if not token:
        # Check header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(status_code=401, detail="No token provided")
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {"valid": True, "user_id": payload.get("user_id"), "email": payload.get("email"), "role": payload.get("role")}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.get("/me")
async def get_current_user_info(request: Request):
    """Get current authenticated user info from cookie or header"""
    token = request.cookies.get("lama_session")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        
        with engine.connect() as conn:
            query = select(users_table).where(users_table.c.id == user_id)
            user = conn.execute(query).fetchone()
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
                
            return {
                "id": user[0],
                "email": user[1],
                "role": user[5],
                "full_name": user[4]
            }
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid session")

@router.post("/logout")
async def logout(response: Response):
    """Clear the session cookie"""
    response.delete_cookie("lama_session", path="/")
    return {"message": "Successfully logged out"}

def validate_password_policy(password: str, email: str = None, mobile: str = None) -> tuple[bool, str]:
    """
    Validate password against ITIL best practices:
    - Minimum 8 characters (recommended 12+)
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    - At least one special character
    - Cannot contain username/email/mobile
    """
    errors = []
    
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")
    elif len(password) < 12:
        # Warning but not blocking
        pass
    
    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")
    
    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")
    
    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one number")
    
    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not any(c in special_chars for c in password):
        errors.append("Password must contain at least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?)")
    
    # Check if password contains username/email/mobile
    if email:
        email_parts = email.split('@')[0].lower()
        if email_parts and len(email_parts) >= 3 and email_parts.lower() in password.lower():
            errors.append("Password cannot contain your email username")
    
    if mobile:
        if mobile in password:
            errors.append("Password cannot contain your mobile number")
    
    if errors:
        return False, "; ".join(errors)
    
    return True, "Password meets security requirements"

def get_current_user_token(request: Request):
    """Extract JWT token from Cookie or Authorization header"""
    token = request.cookies.get("lama_session")
    
    if not token:
        authorization = request.headers.get("Authorization") or request.headers.get("authorization")
        if authorization:
            parts = authorization.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
    
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated. Please provide a valid token.")
    
    # Verify token is valid
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return token, payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    request: Request
):
    """Change user password with ITIL password policy validation"""
    # Extract token from Authorization header
    logger.info("Change password endpoint called")
    
    try:
        token, payload = get_current_user_token(request)
        user_id = payload.get("user_id")
        user_email = payload.get("email", "")
        logger.info(f"Token decoded successfully for user_id: {user_id}, email: {user_email}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting token: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Not authenticated. Please provide a valid token.")
    
    # Validate new password against ITIL policy
    is_valid, policy_message = validate_password_policy(data.new_password, user_email)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Password policy violation: {policy_message}")
    
    # Try database first
    try:
        # Use engine.begin() for proper transaction management
        with engine.begin() as conn:
            query = select(users_table).where(users_table.c.id == user_id)
            result = conn.execute(query).fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Row access: id, email, mobile, password, full_name, role, created_at, updated_at
            # Index: 0=id, 1=email, 2=mobile, 3=password, 4=full_name, 5=role
            stored_password = result[3]
            
            # Verify old password
            password_match = False
            try:
                if isinstance(stored_password, bytes):
                    stored_password_str = stored_password.decode('utf-8')
                else:
                    stored_password_str = str(stored_password)
                
                if stored_password_str.startswith('$2'):
                    password_match = bcrypt.checkpw(data.old_password.encode('utf-8'), stored_password_str.encode('utf-8'))
            except Exception as e:
                logger.error(f"Password verification error: {e}")
                password_match = False
            
            if not password_match:
                raise HTTPException(status_code=400, detail="Current password is incorrect")
            
            # Check if new password is same as old password
            if password_match and bcrypt.checkpw(data.new_password.encode('utf-8'), stored_password_str.encode('utf-8')):
                raise HTTPException(status_code=400, detail="New password must be different from current password")
            
            # Update password
            hashed = bcrypt.hashpw(data.new_password.encode(), bcrypt.gensalt()).decode()
            from sqlalchemy import update
            update_query = update(users_table).where(users_table.c.id == user_id).values(password=hashed)
            conn.execute(update_query)
            # engine.begin() automatically commits on successful exit
            logger.info(f"Password changed successfully for user_id: {user_id}")
            return {"status": "success", "message": "Password changed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database password change error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error changing password: {str(e)}")

@router.post("/users", response_model=dict)
def create_new_user(data: CreateUserRequest, db: Session = Depends(get_db)):
    """Create new user (admin only)"""
    try:
        # Check if user already exists
        existing_user = db.execute(
            select(users_table).where(users_table.c.email == data.email)
        ).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="User with this email already exists")

        # Hash the password
        hashed_password = bcrypt.hashpw(data.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Create new user
        new_user = {
            "email": data.email,
            "password": hashed_password,
            "role": data.role,
            "full_name": data.full_name,
        }
        db.execute(users_table.insert().values(new_user))
        db.commit()
        return {"status": "success", "user": new_user}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error creating user")

@router.get("/users", response_model=list)
def list_all_users(db: Session = Depends(get_db)):
    """Get all users"""
    try:
        users = db.execute(select(users_table)).fetchall()
        # Remove password hashes from response
        return [{k: v for k, v in u._mapping.items() if k != 'password'} for u in users]
    except Exception as e:
        logger.error(f"Error listing users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error listing users")

@router.delete("/users/{user_id}")
def delete_user_endpoint(user_id: int, db: Session = Depends(get_db)):
    """Delete user"""
    try:
        # Check if user exists
        user = db.execute(
            select(users_table).where(users_table.c.id == user_id)
        ).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        db.execute(users_table.delete().where(users_table.c.id == user_id))
        db.commit()
        return {"status": "success", "message": "User deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error deleting user")

@router.put("/users/{user_id}")
def update_user_endpoint(user_id: int, data: UpdateUserRequest, db: Session = Depends(get_db)):
    """Update user details"""
    try:
        # Check if user exists
        user = db.execute(
            select(users_table).where(users_table.c.id == user_id)
        ).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        updates = {k: v for k, v in data.dict().items() if v is not None}
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        db.execute(
            users_table.update().where(users_table.c.id == user_id).values(updates)
        )
        db.commit()
        return {"status": "success", "message": "User updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error updating user")

@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, request: Request):
    """
    Request password reset - sends email with reset link
    Uses existing SMTP configuration from alert_config
    """
    from app.utils.email_service import (
        generate_password_reset_token,
        store_reset_token,
        send_password_reset_email
    )
    
    try:
        # Check if user exists
        with engine.connect() as conn:
            result = conn.execute(
                select(users_table).where(users_table.c.email == data.email)
            ).fetchone()
            
            if not result:
                # For security, don't reveal if email exists or not
                # Return success but don't send email
                logger.warning(f"Password reset requested for non-existent email: {data.email}")
                return {
                    "status": "success",
                    "message": "If the email exists, a password reset link has been sent."
                }
            
            user_id = result[0]
            user_email = result[1]
            user_name = result[4] if result[4] else "User"
            
            # Generate reset token
            reset_token = generate_password_reset_token()
            
            # Store token in database
            if not store_reset_token(user_id, reset_token, expiry_minutes=30):
                raise HTTPException(
                    status_code=500,
                    detail="Error generating password reset token. Please try again."
                )
            
            # Get base URL from request
            base_url = str(request.base_url).rstrip('/')
            # If behind proxy, use forwarded proto and host
            if 'x-forwarded-proto' in request.headers and 'x-forwarded-host' in request.headers:
                proto = request.headers['x-forwarded-proto']
                host = request.headers['x-forwarded-host']
                base_url = f"{proto}://{host}"
            
            # Send reset email
            email_sent = send_password_reset_email(
                user_email=user_email,
                user_name=user_name,
                reset_token=reset_token,
                base_url=base_url
            )
            
            if not email_sent:
                logger.error(f"Failed to send password reset email to {user_email}")
                raise HTTPException(
                    status_code=500,
                    detail="SMTP not configured. Please contact your administrator to configure email alerts first."
                )
            
            logger.info(f"Password reset email sent successfully to {user_email}")
            return {
                "status": "success",
                "message": "If the email exists, a password reset link has been sent."
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in forgot password: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error processing password reset request")

@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest):
    """
    Reset password using token from email
    """
    from app.utils.email_service import verify_reset_token, mark_token_as_used
    
    try:
        # Verify token
        user_info = verify_reset_token(data.token)
        if not user_info:
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired password reset link. Please request a new one."
            )
        
        user_id = user_info['user_id']
        user_email = user_info['email']
        
        # Validate new password
        is_valid, error_message = validate_password_policy(data.new_password, email=user_email)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_message)
        
        # Hash new password
        hashed_password = bcrypt.hashpw(data.new_password.encode(), bcrypt.gensalt()).decode()
        
        # Update password in database
        with engine.connect() as conn:
            conn.execute(
                users_table.update()
                .where(users_table.c.id == user_id)
                .values(password=hashed_password, updated_at=datetime.utcnow())
            )
            conn.commit()
        
        # Mark token as used
        mark_token_as_used(data.token)
        
        logger.info(f"Password reset successful for user {user_email}")
        
        return {
            "status": "success",
            "message": "Password has been reset successfully. You can now login with your new password."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in reset password: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error resetting password")

@router.get("/verify-reset-token/{token}")
def verify_reset_token_endpoint(token: str):
    """
    Verify if password reset token is valid
    Used by frontend to check token before showing reset form
    """
    from app.utils.email_service import verify_reset_token
    
    try:
        user_info = verify_reset_token(token)
        if not user_info:
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired password reset link"
            )
        
        return {
            "status": "success",
            "valid": True,
            "email": user_info['email']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying reset token: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error verifying token")
        return {"status": "success", "message": "User updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error updating user")
