# api/backend/app/routes/certificate_status.py
"""
SSL Certificate Status API
Monitors certificate expiry and provides alerts
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional, List
import os
import logging

# Try to import cryptography for certificate parsing
try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

from app.db.db import get_db

router = APIRouter(tags=["Certificate"])
logger = logging.getLogger(__name__)

# Certificate paths to check (in order of preference)
CERTIFICATE_PATHS = [
    "/etc/ssl/certs/fullchain.crt",
    "/etc/ssl/certs/wildcard_smcindiaonline_com.crt",
    "/etc/ssl/certs/smcindiaonline.crt",
    "/app/certificates/fullchain.crt",
    "/app/certificates/wildcard_smcindiaonline_com.crt",
]

# Alert thresholds (days)
ALERT_THRESHOLDS = {
    "critical": 7,
    "warning": 15,
    "notice": 30,
}


def parse_certificate(cert_path: str) -> dict:
    """Parse certificate file and extract details"""
    if not CRYPTO_AVAILABLE:
        raise HTTPException(
            status_code=500, 
            detail="cryptography library not installed. Run: pip install cryptography"
        )
    
    try:
        with open(cert_path, "rb") as f:
            cert_data = f.read()
        
        # Parse PEM certificate
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())
        
        # Extract details - handle both timezone-aware and naive datetimes
        if hasattr(cert, 'not_valid_before_utc'):
            not_before = cert.not_valid_before_utc
            not_after = cert.not_valid_after_utc
            # Use timezone-aware now for comparison
            from datetime import timezone as dt_timezone
            now = datetime.now(dt_timezone.utc)
        else:
            not_before = cert.not_valid_before
            not_after = cert.not_valid_after
            # Use naive datetime for comparison
            now = datetime.utcnow()
        
        # Calculate days remaining
        days_remaining = (not_after - now).days
        
        # Determine status
        if days_remaining < 0:
            status = "expired"
            status_color = "error"
        elif days_remaining <= ALERT_THRESHOLDS["critical"]:
            status = "critical"
            status_color = "error"
        elif days_remaining <= ALERT_THRESHOLDS["warning"]:
            status = "warning"
            status_color = "warning"
        elif days_remaining <= ALERT_THRESHOLDS["notice"]:
            status = "notice"
            status_color = "info"
        else:
            status = "ok"
            status_color = "success"
        
        # Extract subject and issuer
        subject = cert.subject
        issuer = cert.issuer
        
        # Get common name from subject
        common_name = None
        for attr in subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                common_name = attr.value
                break
        
        # Get issuer organization
        issuer_org = None
        for attr in issuer:
            if attr.oid == x509.oid.NameOID.ORGANIZATION_NAME:
                issuer_org = attr.value
                break
        
        # Get Subject Alternative Names (SANs) if available
        sans = []
        try:
            san_extension = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            for name in san_extension.value:
                if isinstance(name, x509.DNSName):
                    sans.append(name.value)
        except x509.ExtensionNotFound:
            pass
        
        return {
            "found": True,
            "path": cert_path,
            "common_name": common_name,
            "subject_alternative_names": sans,
            "issuer": issuer_org,
            "not_before": not_before.isoformat(),
            "not_after": not_after.isoformat(),
            "days_remaining": days_remaining,
            "status": status,
            "status_color": status_color,
            "serial_number": format(cert.serial_number, 'X'),
            "signature_algorithm": cert.signature_algorithm_oid._name if hasattr(cert.signature_algorithm_oid, '_name') else str(cert.signature_algorithm_oid),
            "checked_at": datetime.utcnow().isoformat(),
        }
        
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Certificate file not found: {cert_path}")
    except Exception as e:
        logger.error(f"Error parsing certificate {cert_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Error parsing certificate: {str(e)}")


def find_certificate() -> Optional[str]:
    """Find the first available certificate file"""
    for path in CERTIFICATE_PATHS:
        if os.path.exists(path):
            return path
    return None


@router.get("/certificate/status")
def get_certificate_status():
    """
    Get SSL certificate status including expiry information
    
    Returns:
        Certificate details including:
        - Domain/Common Name
        - Issuer
        - Expiry date
        - Days remaining
        - Status (ok/notice/warning/critical/expired)
    """
    # Find certificate
    cert_path = find_certificate()
    
    if not cert_path:
        return {
            "found": False,
            "message": "No SSL certificate found",
            "searched_paths": CERTIFICATE_PATHS,
            "status": "unknown",
            "status_color": "default",
            "checked_at": datetime.utcnow().isoformat(),
        }
    
    # Parse and return certificate info
    return parse_certificate(cert_path)


@router.get("/check-expiry")
def check_certificate_expiry():
    """
    Check if certificate is expiring soon (for scheduler/alerts)
    
    Returns:
        Alert information if certificate needs attention
    """
    cert_path = find_certificate()
    
    if not cert_path:
        return {
            "needs_alert": False,
            "reason": "no_certificate_found",
            "message": "No SSL certificate configured",
        }
    
    try:
        cert_info = parse_certificate(cert_path)
        
        days_remaining = cert_info["days_remaining"]
        
        # Determine if alert is needed
        if days_remaining < 0:
            return {
                "needs_alert": True,
                "alert_level": "critical",
                "reason": "expired",
                "message": f"SSL Certificate EXPIRED {abs(days_remaining)} days ago!",
                "certificate": cert_info,
            }
        elif days_remaining <= ALERT_THRESHOLDS["critical"]:
            return {
                "needs_alert": True,
                "alert_level": "critical",
                "reason": "expiring_soon",
                "message": f"SSL Certificate expires in {days_remaining} days! Immediate action required.",
                "certificate": cert_info,
            }
        elif days_remaining <= ALERT_THRESHOLDS["warning"]:
            return {
                "needs_alert": True,
                "alert_level": "warning",
                "reason": "expiring_soon",
                "message": f"SSL Certificate expires in {days_remaining} days. Please renew soon.",
                "certificate": cert_info,
            }
        elif days_remaining <= ALERT_THRESHOLDS["notice"]:
            return {
                "needs_alert": True,
                "alert_level": "info",
                "reason": "expiring_notice",
                "message": f"SSL Certificate expires in {days_remaining} days. Plan renewal.",
                "certificate": cert_info,
            }
        else:
            return {
                "needs_alert": False,
                "reason": "certificate_valid",
                "message": f"SSL Certificate is valid for {days_remaining} more days.",
                "certificate": cert_info,
            }
            
    except HTTPException as e:
        return {
            "needs_alert": True,
            "alert_level": "error",
            "reason": "parse_error",
            "message": f"Error checking certificate: {e.detail}",
        }


@router.get("/thresholds")
def get_alert_thresholds():
    """Get current alert threshold settings"""
    return {
        "thresholds": ALERT_THRESHOLDS,
        "description": {
            "critical": f"Alert when {ALERT_THRESHOLDS['critical']} days or less remaining",
            "warning": f"Alert when {ALERT_THRESHOLDS['warning']} days or less remaining",
            "notice": f"Alert when {ALERT_THRESHOLDS['notice']} days or less remaining",
        }
    }

