"""
Rate Limiting Middleware for Authentication Endpoints
Simple in-memory rate limiting to prevent brute force attacks
"""
from fastapi import Request, HTTPException
from datetime import datetime, timedelta
import logging
from collections import defaultdict
import asyncio

logger = logging.getLogger(__name__)

class RateLimiter:
    """
    Simple in-memory rate limiter
    Tracks failed login attempts per IP address
    """
    def __init__(self):
        # Track failed attempts: {ip_address: [(timestamp, count)]}
        self.failed_attempts = defaultdict(list)
        # Track when IPs were blocked: {ip_address: unblock_timestamp}
        self.blocked_ips = {}
        
        # Configuration
        self.MAX_ATTEMPTS = 50  # Max failed attempts (Increased for testing)
        self.WINDOW_MINUTES = 15  # Time window for counting attempts
        self.BLOCK_DURATION_MINUTES = 30  # How long to block after max attempts
        
        # Start cleanup task
        self.cleanup_task = None
    
    def get_client_ip(self, request: Request) -> str:
        """Extract client IP from request"""
        # Check X-Forwarded-For header (nginx proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Fall back to direct client IP
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def is_blocked(self, ip_address: str) -> tuple[bool, int]:
        """
        Check if IP is currently blocked
        Returns: (is_blocked, seconds_until_unblock)
        """
        if ip_address in self.blocked_ips:
            unblock_time = self.blocked_ips[ip_address]
            now = datetime.now()
            
            if now < unblock_time:
                # Still blocked
                seconds_left = int((unblock_time - now).total_seconds())
                return True, seconds_left
            else:
                # Block expired, remove it
                del self.blocked_ips[ip_address]
                # Clear old attempts
                if ip_address in self.failed_attempts:
                    del self.failed_attempts[ip_address]
        
        return False, 0
    
    def record_failed_attempt(self, ip_address: str):
        """Record a failed login attempt"""
        now = datetime.now()
        cutoff = now - timedelta(minutes=self.WINDOW_MINUTES)
        
        # Get existing attempts for this IP
        attempts = self.failed_attempts[ip_address]
        
        # Remove old attempts outside the time window
        attempts = [a for a in attempts if a > cutoff]
        
        # Add new attempt
        attempts.append(now)
        self.failed_attempts[ip_address] = attempts
        
        # Check if should block
        if len(attempts) >= self.MAX_ATTEMPTS:
            # Block this IP
            unblock_time = now + timedelta(minutes=self.BLOCK_DURATION_MINUTES)
            self.blocked_ips[ip_address] = unblock_time
            
            logger.warning(
                f"[SECURITY] IP {ip_address} blocked for {self.BLOCK_DURATION_MINUTES} minutes "
                f"after {len(attempts)} failed login attempts"
            )
            
            return True  # Now blocked
        else:
            remaining = self.MAX_ATTEMPTS - len(attempts)
            logger.warning(
                f"[SECURITY] Failed login from {ip_address}. "
                f"{remaining} attempts remaining before block"
            )
            return False  # Not yet blocked
    
    def clear_failed_attempts(self, ip_address: str):
        """Clear failed attempts after successful login"""
        if ip_address in self.failed_attempts:
            del self.failed_attempts[ip_address]
    
    def check_rate_limit(self, request: Request):
        """
        Check if request should be rate limited
        Raises HTTPException if blocked
        """
        ip_address = self.get_client_ip(request)
        
        is_blocked, seconds_left = self.is_blocked(ip_address)
        if is_blocked:
            minutes_left = int(seconds_left / 60) + 1
            logger.warning(f"[SECURITY] Blocked login attempt from {ip_address}")
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed login attempts. Account temporarily locked. "
                       f"Please try again in {minutes_left} minutes."
            )
    
    async def cleanup_old_entries(self):
        """Periodically clean up old entries to prevent memory leak"""
        while True:
            try:
                await asyncio.sleep(600)  # Run every 10 minutes
                
                now = datetime.now()
                cutoff = now - timedelta(minutes=self.WINDOW_MINUTES * 2)
                
                # Clean failed attempts
                for ip in list(self.failed_attempts.keys()):
                    attempts = self.failed_attempts[ip]
                    attempts = [a for a in attempts if a > cutoff]
                    if attempts:
                        self.failed_attempts[ip] = attempts
                    else:
                        del self.failed_attempts[ip]
                
                # Clean expired blocks
                for ip in list(self.blocked_ips.keys()):
                    if now >= self.blocked_ips[ip]:
                        del self.blocked_ips[ip]
                        logger.info(f"[SECURITY] IP {ip} unblocked after timeout")
                
                logger.debug(
                    f"[SECURITY] Rate limiter cleanup: "
                    f"{len(self.failed_attempts)} tracked IPs, "
                    f"{len(self.blocked_ips)} blocked IPs"
                )
            except Exception as e:
                logger.error(f"[SECURITY] Rate limiter cleanup error: {e}")
                await asyncio.sleep(60)  # Retry after 1 minute on error

# Global rate limiter instance
rate_limiter = RateLimiter()
