import React from 'react';
import { Navigate } from 'react-router-dom';

/**
 * RoleProtectedRoute - Protects routes based on user role
 * 
 * If user role is not in allowedRoles, redirects to dashboard
 * 
 * @param {Object} props
 * @param {React.ReactNode} props.children - Child components to render if access allowed
 * @param {string[]} props.allowedRoles - Array of allowed roles (e.g., ['admin'])
 */
export default function RoleProtectedRoute({ children, allowedRoles = ['admin'] }) {
  const userRole = sessionStorage.getItem('lama_user_role') || 'user';
  
  // If user role is not in allowed roles, redirect to dashboard
  if (!allowedRoles.includes(userRole)) {
    return <Navigate to="/servers" replace />;
  }
  
  return children;
}

