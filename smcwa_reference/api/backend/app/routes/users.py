# api/backend/app/routes/users.py
"""
User management endpoints: CRUD operations for users
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, delete, update
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session
from app.db.db import get_db, users_table, engine, get_connection
from app.utils.permissions import require_admin, get_current_user
import bcrypt
from typing import Optional, List

router = APIRouter()

class UserCreate(BaseModel):
    email: Optional[str] = None
    mobile: Optional[str] = None
    password: str
    full_name: Optional[str] = None
    role: str = "user"
    is_active: bool = True

class UserUpdate(BaseModel):
    email: Optional[str] = None
    mobile: Optional[str] = None
    password: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class UserResponse(BaseModel):
    id: int
    email: Optional[str] = None
    mobile: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    is_active: bool = True
    created_at: Optional[str] = None

def _user_db_to_response(user_row: Row) -> UserResponse:
    """Converts a user database row to a UserResponse model."""
    created_at_str = (user_row.created_at.isoformat() + 'Z') if user_row.created_at else None
    
    # Check if is_active exists in row (it might not if DB hasn't been updated yet)
    is_active = True
    if hasattr(user_row, 'is_active'):
        is_active = user_row.is_active
    elif len(user_row) > 6: # Try by index if it's a row proxy
        # Index based on db.py: 0=id, 1=email, 2=mobile, 3=password, 4=full_name, 5=role, 6=is_active
        try:
            is_active = user_row[6]
        except:
            pass

    return UserResponse(
        id=user_row.id,
        email=user_row.email,
        mobile=user_row.mobile,
        full_name=user_row.full_name,
        role=user_row.role,
        is_active=is_active,
        created_at=created_at_str
    )

@router.get("/", response_model=List[UserResponse])
def list_users(request: Request):
    """List all users - requires admin role"""
    require_admin(request)
    try:
        with get_connection() as conn:
            query = select(users_table)
            results = conn.execute(query).fetchall()
            return [_user_db_to_response(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching users: {str(e)}")

@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, request: Request):
    """Get user by ID - requires authentication and RBAC check"""
    current_user = get_current_user(request)
    
    # RBAC: Only admin can see other users, regular user can only see themselves
    if current_user["role"] != "admin" and current_user["user_id"] != user_id:
        raise HTTPException(
            status_code=403, 
            detail="Access denied. You can only view your own profile."
        )
        
    try:
        with get_connection() as conn:
            query = select(users_table).where(users_table.c.id == user_id)
            result = conn.execute(query).fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="User not found")
            return _user_db_to_response(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching user: {str(e)}")

from app.utils.sanitizer import sanitize_string

@router.post("/", response_model=UserResponse)
def create_user(user_data: UserCreate, request: Request):
    """Create a new user - Admin only"""
    require_admin(request)
    if not user_data.email and not user_data.mobile:
        raise HTTPException(status_code=400, detail="Either email or mobile is required")
    
    # Sanitize inputs (VAPT Fix)
    if user_data.email: user_data.email = sanitize_string(user_data.email)
    if user_data.mobile: user_data.mobile = sanitize_string(user_data.mobile)
    if user_data.full_name: user_data.full_name = sanitize_string(user_data.full_name)
    
    try:
        with get_connection() as conn:
            if user_data.email:
                query = select(users_table).where(users_table.c.email == user_data.email)
                if conn.execute(query).fetchone():
                    raise HTTPException(status_code=400, detail="User with this email already exists")
            
            if user_data.mobile:
                query = select(users_table).where(users_table.c.mobile == user_data.mobile)
                if conn.execute(query).fetchone():
                    raise HTTPException(status_code=400, detail="User with this mobile number already exists")
            
            hashed_password = bcrypt.hashpw(user_data.password.encode(), bcrypt.gensalt()).decode()
            
            insert_query = users_table.insert().values(
                email=user_data.email,
                mobile=user_data.mobile,
                password=hashed_password,
                full_name=user_data.full_name,
                role=user_data.role,
                is_active=user_data.is_active
            ).returning(users_table)
            
            created_user = conn.execute(insert_query).fetchone()
            conn.commit()
            
            return _user_db_to_response(created_user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating user: {str(e)}")

@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, user_data: UserUpdate, request: Request):
    """Update user - Admin only, or user can update their own profile (limited fields)"""
    current_user = get_current_user(request)
    
    if current_user["role"] != "admin":
        if current_user["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Access denied. You can only update your own profile.")
        if any([user_data.role, user_data.email]):
            raise HTTPException(status_code=403, detail="Access denied. You can only update your full name, password, or mobile.")

    # Sanitize inputs (VAPT Fix)
    if user_data.email: user_data.email = sanitize_string(user_data.email)
    if user_data.mobile: user_data.mobile = sanitize_string(user_data.mobile)
    if user_data.full_name: user_data.full_name = sanitize_string(user_data.full_name)

    try:
        with get_connection() as conn:
            if not conn.execute(select(users_table).where(users_table.c.id == user_id)).fetchone():
                raise HTTPException(status_code=404, detail="User not found")
            
            if user_data.email:
                query = select(users_table).where(users_table.c.email == user_data.email, users_table.c.id != user_id)
                if conn.execute(query).fetchone():
                    raise HTTPException(status_code=400, detail="Email already in use by another user")
            
            if user_data.mobile:
                query = select(users_table).where(users_table.c.mobile == user_data.mobile, users_table.c.id != user_id)
                if conn.execute(query).fetchone():
                    raise HTTPException(status_code=400, detail="Mobile number already in use by another user")
            
            update_values = user_data.dict(exclude_unset=True)
            if 'password' in update_values and update_values['password']:
                update_values['password'] = bcrypt.hashpw(update_values['password'].encode(), bcrypt.gensalt()).decode()
            
            if update_values:
                update_query = update(users_table).where(users_table.c.id == user_id).values(**update_values)
                conn.execute(update_query)
                conn.commit()
            
            updated = conn.execute(select(users_table).where(users_table.c.id == user_id)).fetchone()
            return _user_db_to_response(updated)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating user: {str(e)}")

@router.delete("/{user_id}")
def delete_user(user_id: int, request: Request):
    """Delete user - Admin only"""
    require_admin(request)
    try:
        with get_connection() as conn:
            if not conn.execute(select(users_table).where(users_table.c.id == user_id)).fetchone():
                raise HTTPException(status_code=404, detail="User not found")
            
            delete_query = delete(users_table).where(users_table.c.id == user_id)
            conn.execute(delete_query)
            conn.commit()
            
            return {"message": "User deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting user: {str(e)}")
