# User Authentication Flow

## Overview

LAMA uses AES-256 encrypted password transmission and JWT-based session management. Passwords are encrypted on the client side before transmission, validated on the server, and sessions are stored in Redis for fast validation.

---

## Flow Diagram

```
┌──────────┐                                              ┌──────────────┐
│   USER   │                                              │  PostgreSQL  │
└────┬─────┘                                              └──────┬───────┘
     │                                                           │
     │  1. Enter Member ID, Login ID, Password                  │
     ▼                                                           │
┌────────────────────────────────────────────────────────┐      │
│                     REACT UI                            │      │
│  • Password encrypted with AES-256 before transmission │      │
└──────────────────────────┬─────────────────────────────┘      │
                           │                                     │
                           │  2. POST /api/v1/auth/login         │
                           ▼                                     │
┌────────────────────────────────────────────────────────┐      │
│                   FASTAPI BACKEND                       │      │
│                                                         │      │
│  • Decrypt password (AES-256)                          │      │
│  • Validate credentials against PostgreSQL ◄───────────┼──────┘
│  • Generate JWT token (24h expiry)                     │
│  • Store session in Redis                              │
└──────────────────────────┬─────────────────────────────┘
                           │
                           │  3. Return JWT Token + User Info
                           ▼
┌────────────────────────────────────────────────────────┐
│                     REACT UI                            │
│                                                         │
│  • Store token in sessionStorage                       │
│  • Include token in all subsequent API requests        │
│  • Redirect to /servers (Dashboard)                    │
└────────────────────────────────────────────────────────┘
```

---

## Step-by-Step

| Step | Component | Action |
|---|---|---|
| 1 | **React UI** (Login.jsx) | User enters Member ID, Login ID, Password. Password is AES-256 encrypted client-side before sending |
| 2 | **FastAPI** (auth.py) | `POST /api/v1/auth/login` — Decrypts password, validates against PostgreSQL `users` table |
| 3 | **FastAPI** | On success: generates JWT token (24h expiry), stores session in Redis |
| 4 | **React UI** | Receives `{ token, user_email, user_id, role }`, stores in sessionStorage |
| 5 | **React UI** | All subsequent API calls include `Authorization: Bearer <token>` header |
| 6 | **FastAPI** | Every protected endpoint validates JWT + checks Redis session exists |
| 7 | **React UI** | On logout: `POST /api/v1/auth/logout` → invalidates Redis session + clears sessionStorage |

---

## Security Features

| Feature | Implementation |
|---|---|
| **Password Encryption** | AES-256 on client side before transmission over HTTPS |
| **Password Storage** | bcrypt hashed in PostgreSQL (never stored in plain text) |
| **Session Tokens** | JWT with 24-hour expiry, stored in Redis for fast validation |
| **Session Invalidation** | Logout deletes Redis key, token becomes invalid immediately |
| **Role-Based Access** | `admin` and `viewer` roles — admin-only routes protected by `RoleProtectedRoute` |
| **HTTPS** | Nginx terminates SSL with wildcard certificate |

---

## Auth API Endpoints

| Method | Endpoint | Access | Description |
|---|---|---|---|
| POST | `/api/v1/auth/login` | Public | Login with encrypted password, returns JWT |
| POST | `/api/v1/auth/logout` | Authenticated | Invalidate session |
| POST | `/api/v1/auth/reset-password` | Public | Password reset flow |
| POST | `/api/v1/auth/change-password` | Authenticated | Change own password (verify old first) |
| GET | `/api/v1/auth/users` | Admin | List all users |
| POST | `/api/v1/auth/users` | Admin | Create new user |
| PUT | `/api/v1/auth/users/{id}` | Admin | Update user details |
| DELETE | `/api/v1/auth/users/{id}` | Admin | Delete user (cannot delete default admin) |
