# SMC-LAMA User Management Architecture

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                       WEB BROWSER (React Frontend)                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌────────────────────┐  ┌────────────────────┐  ┌──────────────┐  │
│  │  Login Page        │  │  Dashboard         │  │  Users Page  │  │
│  │  (Login.jsx)       │  │  (Dashboard.jsx)   │  │  (Users.jsx) │  │
│  └────────────────────┘  └────────────────────┘  └──────────────┘  │
│           │                      │                      │            │
│           │                      │                      │            │
│  ┌────────────────────────────────────────────────────────┐         │
│  │  Stores JWT Token + user_id + user_email             │         │
│  │  in localStorage                                       │         │
│  └────────────────────────────────────────────────────────┘         │
│           │                      │                      │            │
│  ┌────────────────────┐  ┌────────────────────┐  ┌──────────────┐  │
│  │  Profile Page      │  │  Settings Page     │  │  Topbar      │  │
│  │  (Profile.jsx)     │  │  (Settings.jsx)    │  │  (Topbar.jsx)│  │
│  │  - View profile    │  │  - API config      │  │  - Profile   │  │
│  │  - Edit details    │  │  - Settings        │  │  - Logout    │  │
│  │  - Change password │  │  - Preferences     │  │  - User menu │  │
│  └────────────────────┘  └────────────────────┘  └──────────────┘  │
│           │                      │                      │            │
└───────────┼──────────────────────┼──────────────────────┼────────────┘
            │ HTTP Requests        │                      │
            │ (with JWT token)     │                      │
            ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Python)                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │ FastAPI Routes (app/routes/auth.py)                         │  │
│   │                                                              │  │
│   │  POST /auth/login                                           │  │
│   │    ├─ Email + Password → Verify → JWT + user_id            │  │
│   │    └─ Response: { token, user_email, user_id, role }       │  │
│   │                                                              │  │
│   │  GET /auth/users                                            │  │
│   │    ├─ Verify JWT Token                                      │  │
│   │    └─ Return all users (passwords removed)                  │  │
│   │                                                              │  │
│   │  POST /auth/users (Admin only)                              │  │
│   │    ├─ Create new user                                       │  │
│   │    └─ Hash password with bcrypt                             │  │
│   │                                                              │  │
│   │  PUT /auth/users/{id} (Admin only)                          │  │
│   │    └─ Update user name/phone/role                           │  │
│   │                                                              │  │
│   │  DELETE /auth/users/{id} (Admin only)                       │  │
│   │    └─ Delete user (prevent default admin)                   │  │
│   │                                                              │  │
│   │  POST /auth/change-password                                 │  │
│   │    ├─ Verify old password                                   │  │
│   │    └─ Hash and save new password                            │  │
│   │                                                              │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │ Local Storage Module (app/local_storage.py)                 │  │
│   │                                                              │  │
│   │  ├─ init_users()              Create default admin          │  │
│   │  ├─ authenticate_user(e, p)   Verify credentials           │  │
│   │  ├─ create_user(...)          Add new user                  │  │
│   │  ├─ update_user(...)          Update user details           │  │
│   │  ├─ update_password(...)      Secure password change        │  │
│   │  ├─ delete_user(...)          Remove user                   │  │
│   │  ├─ get_all_users()           Retrieve all users            │  │
│   │  └─ get_user_by_id(...)       Retrieve specific user        │  │
│   │                                                              │  │
│   │  Utilities:                                                 │  │
│   │  ├─ load_users()              Read from JSON file           │  │
│   │  ├─ save_users()              Write to JSON file            │  │
│   │  └─ verify_password()         Bcrypt verification           │  │
│   │                                                              │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
└───────────────────────────────────┬────────────────────────────────┘
                                    │ Read/Write
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    User Storage (JSON File)                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  File: app/data/users.json                                          │
│                                                                       │
│  [                                                                  │
│    {                                                                │
│      "id": 1,                                                       │
│      "email": "dineshpathak@smcindiaonline.com",                  │
│      "password_hash": "$2b$12$...",  ← Bcrypt hashed              │
│      "role": "admin",                                              │
│      "full_name": "Dinesh Pathak",                                 │
│      "phone": "",                                                  │
│      "created_at": "2025-11-18T04:17:32.651808",                  │
│      "updated_at": "2025-11-18T04:17:32.652931"                   │
│    },                                                              │
│    {                                                                │
│      "id": 2,                         ← New users created here     │
│      "email": "user@example.com",                                  │
│      "password_hash": "$2b$12$...",                               │
│      ...                                                            │
│    }                                                                │
│  ]                                                                  │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Authentication Flow

```
User navigates to http://localhost:3000
        │
        ▼
┌──────────────────┐
│  Login Page      │
│  (Login.jsx)     │
└──────────────────┘
        │
        │ User enters email & password
        ▼
┌────────────────────────────────┐
│ Frontend sends POST /auth/login│
│ Body: {email, password}        │
└────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────┐
│ Backend authenticates              │
│ 1. Look up user by email           │
│ 2. Verify password with bcrypt     │
└────────────────────────────────────┘
        │
        ├─ If VALID:
        │       │
        │       ▼
        │  ┌──────────────────────┐
        │  │ Generate JWT token   │
        │  │ Claims:              │
        │  │  - user_id           │
        │  │  - email             │
        │  │  - role              │
        │  │  - exp (24 hours)    │
        │  └──────────────────────┘
        │       │
        │       ▼
        │  ┌────────────────────────────┐
        │  │ Send response:             │
        │  │ {                          │
        │  │   token: "eyJ0eXAi...",   │
        │  │   user_email: "...",       │
        │  │   user_id: 1,              │
        │  │   role: "admin"            │
        │  │ }                          │
        │  └────────────────────────────┘
        │       │
        │       ▼
        │  ┌────────────────────────────┐
        │  │ Frontend stores in         │
        │  │ localStorage:              │
        │  │ - lama_jwt: token          │
        │  │ - user_email               │
        │  │ - user_id                  │
        │  │ - user_role                │
        │  └────────────────────────────┘
        │       │
        │       ▼
        │  ┌────────────────────────┐
        │  │ Redirect to Dashboard  │
        │  │ User logged in ✓       │
        │  └────────────────────────┘
        │
        └─ If INVALID:
                │
                ▼
           ┌────────────────────┐
           │ Return error:      │
           │ "Invalid          │
           │ credentials"       │
           └────────────────────┘
                │
                ▼
           ┌────────────────────┐
           │ Stay on login page │
           │ Show error message │
           └────────────────────┘
```

---

## User Management Flow (Admin)

```
Admin logged in, clicks "Users" menu
        │
        ▼
┌────────────────────────────┐
│ Users Page loads           │
│ GET /auth/users request    │
│ (with JWT token)           │
└────────────────────────────┘
        │
        ▼
┌────────────────────────────────┐
│ Backend verifies JWT token     │
│ Returns list of all users      │
│ (passwords removed from API)   │
└────────────────────────────────┘
        │
        ▼
┌────────────────────────────┐
│ Display users in table     │
│ - Email                    │
│ - Full Name                │
│ - Role (color-coded)       │
│ - Created Date             │
│ - Edit & Delete buttons    │
└────────────────────────────┘
        │
        ├─────────────────────┬─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
    "Add User"           "Edit User"           "Delete User"
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────────┐
│ Dialog Opens │      │ Dialog Opens │      │ Confirmation Box │
│              │      │              │      │                  │
│ Forms:       │      │ Forms:       │      │ Delete this user?│
│ - Email      │      │ - Name       │      └──────────────────┘
│ - Password   │      │ - Phone      │           │
│ - Name       │      │ - Role       │      Yes: DELETE request
│ - Role       │      │              │      No:  Cancel
│ - Submit     │      │ - Save       │           │
└──────────────┘      └──────────────┘      ▼
        │                     │      ┌────────────────┐
        ▼                     ▼      │ User Deleted ✓ │
  POST /auth/users   PUT /auth/users │ Refresh list   │
        │                     │      └────────────────┘
        ▼                     ▼
┌──────────────────────────────────┐
│ Backend:                         │
│ 1. Verify JWT token (admin)      │
│ 2. Validate input                │
│ 3. Hash password (for new users) │
│ 4. Save to users.json            │
│ 5. Return success                │
└──────────────────────────────────┘
        │
        ▼
    ┌─────────────────┐
    │ Close dialog    │
    │ Refresh list    │
    │ Show success    │
    └─────────────────┘
```

---

## Password Change Flow

```
User clicks "Change Password"
        │
        ▼
┌─────────────────────────┐
│ Password Dialog Opens   │
│ Fields:                 │
│ - Old Password          │
│ - New Password          │
│ - Confirm Password      │
│ - Save button           │
└─────────────────────────┘
        │
        │ User enters passwords
        ▼
┌──────────────────────────────────┐
│ Frontend validates               │
│ 1. Old ≠ New (no change)         │
│ 2. New = Confirm                 │
│ 3. Password strength             │
└──────────────────────────────────┘
        │
        ├─ Validation FAILS
        │       │
        │       ▼
        │  Show error message
        │       │
        │       ▼
        │  User corrects
        │       │
        │       └─────────┐
        │                 │
        └─────────┬───────┘
                  │
                  ▼
    Validation PASSES
                  │
                  ▼
    POST /auth/change-password
    Body: {
      old_password: "...",
      new_password: "..."
    }
    Header: Authorization: Bearer {JWT}
                  │
                  ▼
    Backend:
    1. Verify JWT token
    2. Get user_id from token
    3. Load user from users.json
    4. Verify old password with bcrypt
                  │
        ┌─────────┴─────────┐
        │                   │
        │ (FAIL)            │ (SUCCESS)
        ▼                   ▼
    Error:              1. Hash new password
    "Wrong old           2. Update users.json
    password"            3. Return success
        │                   │
        └─────────┬─────────┘
                  │
                  ▼
        Close dialog
        Show success/error
        Clear password fields
```

---

## Data Flow Summary

### Input Data → Processing → Storage → Output

```
USER INPUT
    │
    ├─ Email + Password ──────► Authenticate ──► JWT Token
    │
    ├─ New User Form ─────────► Validate ──────► Hash Password ──► Save to JSON
    │
    ├─ Edit User Form ────────► Validate ──────► Update JSON
    │
    ├─ Old + New Password ────► Verify Old ────► Hash New ──────► Save to JSON
    │
    └─ Delete User ───────────► Check Admin ──► Check Not Default ──► Remove from JSON

FRONTEND STORAGE
    │
    ├─ localStorage.lama_jwt        (JWT Token)
    ├─ localStorage.user_email      (User Email)
    ├─ localStorage.user_id         (User ID)
    ├─ localStorage.user_role       (User Role)
    ├─ localStorage.user_name       (User Full Name)
    ├─ localStorage.user_phone      (User Phone)
    ├─ localStorage.api_endpoint    (API URL)
    └─ localStorage.theme           (UI Theme)

BACKEND STORAGE
    │
    └─ app/data/users.json
        ├─ id (auto-increment)
        ├─ email
        ├─ password_hash (bcrypt)
        ├─ role
        ├─ full_name
        ├─ phone
        ├─ created_at
        └─ updated_at
```

---

## Request/Response Examples

### Login Request
```
POST /auth/login
Content-Type: application/json

{
  "email": "dineshpathak@smcindiaonline.com",
  "password": "@smcltd12"
}

RESPONSE:
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user_email": "dineshpathak@smcindiaonline.com",
  "user_id": 1,
  "role": "admin"
}
```

### Create User Request
```
POST /auth/users
Content-Type: application/json
Authorization: Bearer {JWT_TOKEN}

{
  "email": "newuser@example.com",
  "password": "SecurePass123",
  "full_name": "John Doe",
  "role": "user"
}

RESPONSE:
{
  "id": 2,
  "email": "newuser@example.com",
  "role": "user",
  "full_name": "John Doe",
  "phone": "",
  "created_at": "2025-11-18T05:30:00.000000",
  "updated_at": "2025-11-18T05:30:00.000000"
}
```

### List Users Request
```
GET /auth/users
Authorization: Bearer {JWT_TOKEN}

RESPONSE:
[
  {
    "id": 1,
    "email": "dineshpathak@smcindiaonline.com",
    "role": "admin",
    "full_name": "Dinesh Pathak",
    "phone": "",
    "created_at": "2025-11-18T04:17:32.651808",
    "updated_at": "2025-11-18T04:17:32.652931"
  },
  {
    "id": 2,
    "email": "newuser@example.com",
    "role": "user",
    "full_name": "John Doe",
    "phone": "1234567890",
    "created_at": "2025-11-18T05:30:00.000000",
    "updated_at": "2025-11-18T05:30:00.000000"
  }
]
```

---

## Component Hierarchy

```
App.jsx (Router + Axios Setup)
│
├─ Public Routes
│  └─ Login.jsx
│     ├─ Config Modal (DNS Setup)
│     └─ Login Form
│
└─ Protected Routes (Require JWT Token)
   ├─ Layout
   │  ├─ Sidebar.jsx (Navigation)
   │  ├─ Topbar.jsx (User Menu + Logout)
   │  └─ Main Content
   │     ├─ Dashboard.jsx
   │     ├─ Users.jsx (Admin User Management)
   │     ├─ Profile.jsx (User Profile)
   │     ├─ Settings.jsx (Configuration)
   │     ├─ Servers.jsx
   │     ├─ AgentOnboard.jsx
   │     ├─ Logs.jsx
   │     └─ ConfigWizard.jsx
   │
   └─ ProtectedRoute.jsx (Route Guard)
      └─ Redirects to /login if no token
```

---

**Diagram Version:** 1.0  
**Last Updated:** November 18, 2025  
**Status:** Complete ✅
