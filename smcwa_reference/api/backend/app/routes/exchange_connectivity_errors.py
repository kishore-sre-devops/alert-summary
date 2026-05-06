# api/backend/app/routes/exchange_connectivity_errors.py
"""
Exchange Connectivity Error Logs endpoints
Returns only login/logout errors (authentication and API connection issues)
Separated from Exchange Activity page for cleaner organization
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_
from app.db.db import get_db, engine, exchange_transactions_table
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import io
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Error statuses for login/logout errors
ERROR_STATUSES = ['failed', 'error', 'timeout', 'connection_error', 'request_error', 'protocol_error']


@router.get("/exchange-connectivity-errors")
def get_exchange_connectivity_errors(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    start_time: Optional[str] = Query(None, description="Start time (HH:MM:SS)"),
    end_time: Optional[str] = Query(None, description="End time (HH:MM:SS)"),
    environment: Optional[str] = Query(None, description="Filter by environment (prod/uat)"),
    error_type: Optional[str] = Query(None, description="Filter by error type (login/logout)"),
    limit: int = Query(1000, description="Maximum number of records to return"),
    db: Session = Depends(get_db)
):
    """
    Get exchange connectivity error logs (login/logout errors only)
    Returns authentication and API connection errors with detailed information
    """
    try:
        query = select(exchange_transactions_table).where(
            and_(
                exchange_transactions_table.c.metric_type.in_(['login', 'logout']),
                exchange_transactions_table.c.status.in_(ERROR_STATUSES)
            )
        )
        
        # Date and time range filtering
        # Frontend sends UTC times. Database stores IST (PostgreSQL timezone=Asia/Kolkata).
        IST_OFFSET = timedelta(hours=5, minutes=30)
        if start_date:
            try:
                if start_time:
                    start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M:%S") + IST_OFFSET
                else:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.where(exchange_transactions_table.c.sent_at >= start_dt)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid start_date/start_time format: {str(e)}. Use YYYY-MM-DD for date and HH:MM:SS for time")
        
        if end_date:
            try:
                if end_time:
                    end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M:%S") + IST_OFFSET
                else:
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                query = query.where(exchange_transactions_table.c.sent_at < end_dt)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid end_date/end_time format: {str(e)}. Use YYYY-MM-DD for date and HH:MM:SS for time")
        
        # Environment filter
        if environment:
            if environment not in ['prod', 'uat']:
                raise HTTPException(status_code=400, detail="Environment must be 'prod' or 'uat'")
            query = query.where(exchange_transactions_table.c.environment == environment)
        
        # Error type filter (login/logout)
        if error_type:
            if error_type not in ['login', 'logout']:
                raise HTTPException(status_code=400, detail="Error type must be 'login' or 'logout'")
            query = query.where(exchange_transactions_table.c.metric_type == error_type)
        
        # Order by most recent first
        query = query.order_by(exchange_transactions_table.c.sent_at.desc()).limit(limit)
        
        with engine.connect() as conn:
            results = conn.execute(query).fetchall()
            
            # Convert rows to dictionaries
            errors = []
            for row in results:
                # ENHANCED: Extract complete request details from metrics_sent
                metrics_sent = row[8] if len(row) > 8 else {}  # metrics_sent column (index 8)
                complete_request = metrics_sent.copy() if isinstance(metrics_sent, dict) else {}
                
                # Extract request headers (fallback to old format for backward compatibility)
                request_headers = complete_request.get('request_headers') or complete_request.get('headers', {})
                
                # Extract complete payload details (for login/logout transactions)
                # The payload should contain memberId, loginId, password (encrypted), and notes
                request_payload = {}
                
                # Check if this is a login/logout transaction by metric_type
                is_login_logout = row[7] in ['login', 'logout']  # metric_type column (index 7)
                
                if is_login_logout:
                    # Login/logout transaction - ALWAYS extract all details explicitly
                    # This ensures we show memberId, loginId, password even if stored in different format
                    request_payload = {
                        "memberId": complete_request.get('memberId', ''),
                        "loginId": complete_request.get('loginId', ''),
                        "password": complete_request.get('password', complete_request.get('password_encrypted', '')),
                        "password_encryption_note": complete_request.get('password_encryption_note', ''),
                        "secretKey_note": complete_request.get('secretKey_note', '')
                    }
                    
                    # If payload is empty, try to get from complete_request directly
                    # This handles cases where data might be stored at root level
                    if not request_payload.get('memberId') and not request_payload.get('loginId'):
                        # Check if complete_request itself has the fields (might be stored differently)
                        if isinstance(complete_request, dict):
                            # Try direct access
                            request_payload['memberId'] = complete_request.get('memberId', '')
                            request_payload['loginId'] = complete_request.get('loginId', '')
                            request_payload['password'] = complete_request.get('password', complete_request.get('password_encrypted', ''))
                            
                            # If still empty, include all fields from complete_request (except metadata)
                            if not request_payload.get('memberId') and not request_payload.get('loginId'):
                                # Include all fields except request metadata
                                for key, value in complete_request.items():
                                    if key not in ['request_headers', 'request_url', 'request_method']:
                                        if key not in request_payload:
                                            request_payload[key] = value
                else:
                    # For other transaction types, use the full payload
                    request_payload = complete_request
                
                # Extract response headers and body from exchange_response
                exchange_response = row[10] if len(row) > 10 else {}  # exchange_response column (index 10)
                complete_response = exchange_response.copy() if isinstance(exchange_response, dict) else {}
                
                response_headers = complete_response.get('response_headers', {})
                response_code = complete_response.get('responseCode') or complete_response.get('response_code')
                response_desc = complete_response.get('responseDesc') or complete_response.get('response_desc') or complete_response.get('message')
                
                # ENHANCED: Extract complete response body
                response_body = complete_response.get('response_body_raw') or complete_response.get('response_body_json') or complete_response
                
                # Format error for response with complete details
                error_dict = {
                    "id": row[0],
                    "environment": row[1],
                    "error_type": row[7],  # metric_type (login/logout)
                    "status": row[11],  # status (failed, error, timeout, etc.)
                    "status_code": row[12],  # HTTP status code
                    "error_message": row[13] or "",  # error_message
                    "sent_at": (row[14].isoformat() + 'Z') if row[14] else None,  # sent_at
                    "response_received_at": (row[15].isoformat() + 'Z') if row[15] else None,  # response_received_at
                    
                    # ENHANCED: Complete request details
                    "request": {
                        "url": complete_request.get('request_url', ''),
                        "method": complete_request.get('request_method', 'POST'),
                        "headers": request_headers,
                        "payload": request_payload
                    },
                    
                    # ENHANCED: Complete response details
                    "response": {
                        "status_code": row[12],
                        "headers": response_headers,
                        "body": response_body,  # Complete response body
                        "responseCode": response_code,  # LAMA response code
                        "responseDesc": response_desc,  # LAMA response description
                    },
                    
                    # Backward compatibility fields
                    "request_headers": request_headers,
                    "response_headers": response_headers,
                    "response_code": response_code,
                    "response_desc": response_desc,
                    "full_response": complete_response,  # Full response object for detailed view
                    "member_id": row[5] or "",  # member_id
                }
                errors.append(error_dict)
            
            return {
                "count": len(errors),
                "errors": errors
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching exchange connectivity errors: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching connectivity errors: {str(e)}")


@router.get("/exchange-connectivity-errors/export")
def export_exchange_connectivity_errors(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    start_time: Optional[str] = Query(None, description="Start time (HH:MM:SS)"),
    end_time: Optional[str] = Query(None, description="End time (HH:MM:SS)"),
    environment: Optional[str] = Query(None, description="Filter by environment (prod/uat)"),
    error_type: Optional[str] = Query(None, description="Filter by error type (login/logout)"),
    db: Session = Depends(get_db)
):
    """
    Export exchange connectivity errors to Excel
    """
    try:
        # Get errors using the same logic as get_exchange_connectivity_errors
        query = select(exchange_transactions_table).where(
            and_(
                exchange_transactions_table.c.metric_type.in_(['login', 'logout']),
                exchange_transactions_table.c.status.in_(ERROR_STATUSES)
            )
        )
        
        # Apply same filters as get_exchange_connectivity_errors
        # Frontend sends UTC times. Database stores IST (PostgreSQL timezone=Asia/Kolkata).
        IST_OFFSET = timedelta(hours=5, minutes=30)
        if start_date:
            if start_time:
                start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M:%S") + IST_OFFSET
            else:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.where(exchange_transactions_table.c.sent_at >= start_dt)
        
        if end_date:
            if end_time:
                end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M:%S") + IST_OFFSET
            else:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            query = query.where(exchange_transactions_table.c.sent_at < end_dt)
        
        if environment:
            query = query.where(exchange_transactions_table.c.environment == environment)
        
        if error_type:
            query = query.where(exchange_transactions_table.c.metric_type == error_type)
        
        query = query.order_by(exchange_transactions_table.c.sent_at.desc())
        
        with engine.connect() as conn:
            results = conn.execute(query).fetchall()
            
            # Prepare data for Excel export
            export_data = []
            for row in results:
                metrics_sent = row[8] if len(row) > 8 else {}
                exchange_response = row[10] if len(row) > 10 else {}
                
                request_headers = {}
                response_headers = {}
                response_code = None
                response_desc = None
                
                if isinstance(metrics_sent, dict):
                    request_headers = metrics_sent.get('request_headers') or metrics_sent.get('headers', {})
                    request_payload = {
                        "memberId": metrics_sent.get('memberId', ''),
                        "loginId": metrics_sent.get('loginId', ''),
                        "password": metrics_sent.get('password', metrics_sent.get('password_encrypted', '')),
                        "password_note": metrics_sent.get('password_encryption_note', ''),
                        "secretKey_note": metrics_sent.get('secretKey_note', '')
                    }
                
                if isinstance(exchange_response, dict):
                    response_headers = exchange_response.get('response_headers', {})
                    response_code = exchange_response.get('responseCode') or exchange_response.get('response_code')
                    response_desc = exchange_response.get('responseDesc') or exchange_response.get('response_desc') or exchange_response.get('message')
                    response_body = exchange_response.get('response_body_raw') or exchange_response.get('response_body_json') or exchange_response
                
                export_data.append({
                    "Time (UTC)": row[14].isoformat() if row[14] else "",
                    "Environment": row[1].upper(),
                    "Error Type": row[7].upper(),  # login/logout
                    "Status": row[11],
                    "HTTP Status Code": row[12] or "",
                    "LAMA Response Code": response_code or "",
                    "LAMA Response Description": response_desc or "",
                    "Error Message": row[13] or "",
                    "Request URL": metrics_sent.get('request_url', '') if isinstance(metrics_sent, dict) else "",
                    "Request Method": metrics_sent.get('request_method', 'POST') if isinstance(metrics_sent, dict) else "",
                    "Request Payload": str(request_payload) if isinstance(metrics_sent, dict) else "",
                    "Request Headers": str(request_headers) if request_headers else "",
                    "Response Body": str(response_body) if isinstance(exchange_response, dict) else "",
                    "Response Headers": str(response_headers) if response_headers else "",
                    "Member ID": row[5] or "",
                })
            
            # Create DataFrame and export to Excel
            df = pd.DataFrame(export_data)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Connectivity Errors', index=False)
                
                # Auto-adjust column widths
                worksheet = writer.sheets['Connectivity Errors']
                for idx, col in enumerate(df.columns):
                    max_length = max(
                        df[col].astype(str).apply(len).max(),
                        len(col)
                    )
                    worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)
            
            output.seek(0)
            
            # Generate filename with timestamp
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"exchange_connectivity_errors_{timestamp}.xlsx"
            
            return StreamingResponse(
                io.BytesIO(output.read()),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
            
    except Exception as e:
        logger.error(f"Error exporting exchange connectivity errors: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error exporting connectivity errors: {str(e)}")

