# api/backend/app/routes/alerts.py
"""
Alert history endpoints: List alerts, filter by date/time, export to Excel
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import select, text, and_, or_, func, case
from app.db.db import engine, alerts_table, server_status_table
from app.utils.environment import get_active_environment
from datetime import datetime, timedelta, timezone
from typing import Optional
import pandas as pd
from fastapi.responses import StreamingResponse
import io

router = APIRouter()

def to_ist_str(dt):
    if not dt: return None
    # Strictly add 5:30 for IST and return clear AM/PM format
    from datetime import timedelta
    ist = dt + timedelta(hours=5, minutes=30)
    return ist.strftime("%d/%m/%Y, %I:%M:%S %p")

def _get_alerts_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    metric_type: Optional[str] = None,
    severity: Optional[str] = None,
    is_resolved: Optional[str] = None,
    environment: Optional[str] = None,
    page: int = 0,
    page_size: int = 25,
    limit: Optional[int] = None
):
    """
    Core logic for retrieving alerts from database
    """
    # Determine limit from page_size or legacy limit
    query_limit = limit if limit is not None else page_size
    offset = page * query_limit

    # Handle boolean strings from frontend
    resolved_filter = None
    if is_resolved == 'true' or is_resolved is True:
        resolved_filter = True
    elif is_resolved == 'false' or is_resolved is False:
        resolved_filter = False

    # Base conditions
    conditions = []
    
    # Date filtering - Professional NOC Logic:
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    utc_tz = timezone.utc
    
    date_conditions = []
    if start_date:
        try:
            if start_time:
                start_dt_ist = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=ist_tz)
            else:
                start_dt_ist = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=ist_tz)
            start_dt_utc = start_dt_ist.astimezone(utc_tz).replace(tzinfo=None)
            date_conditions.append(alerts_table.c.created_at >= start_dt_utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")
    
    if end_date:
        try:
            if end_time:
                end_dt_ist = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=ist_tz)
            else:
                end_dt_ist = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=ist_tz)
            end_dt_utc = end_dt_ist.astimezone(utc_tz).replace(tzinfo=None)
            date_conditions.append(alerts_table.c.created_at < end_dt_utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD")

    if date_conditions:
        conditions.append(or_(and_(*date_conditions), alerts_table.c.is_resolved == False))
    
    if metric_type:
        conditions.append(alerts_table.c.alert_type.like(f"{metric_type}.%"))
    
    if severity:
        conditions.append(alerts_table.c.severity == severity)
    
    if resolved_filter is not None:
        conditions.append(alerts_table.c.is_resolved == resolved_filter)
        
    if environment:
        conditions.append(server_status_table.c.environment == environment)

    with engine.connect() as conn:
        # 1. Total Count
        count_query = select(func.count()).select_from(alerts_table.join(server_status_table, alerts_table.c.server_id == server_status_table.c.id, isouter=True))
        if conditions: count_query = count_query.where(and_(*conditions))
        total_count = conn.execute(count_query).scalar()

        # 2. Stats
        stats_query = select(
            func.count(alerts_table.c.id).label("total"),
            func.sum(case((and_(alerts_table.c.is_resolved == False, alerts_table.c.severity == 'error'), 1), else_=0)).label("active_critical"),
            func.sum(case((and_(alerts_table.c.is_resolved == False, alerts_table.c.severity == 'warning'), 1), else_=0)).label("active_warning"),
            func.sum(case((alerts_table.c.is_resolved == False, 1), else_=0)).label("pending"),
            func.sum(case((alerts_table.c.is_resolved == True, 1), else_=0)).label("resolved")
        ).select_from(alerts_table.join(server_status_table, alerts_table.c.server_id == server_status_table.c.id, isouter=True))
        if conditions: stats_query = stats_query.where(and_(*conditions))
        stats_res = conn.execute(stats_query).fetchone()
        summary_stats = {
            "total": int(stats_res[0] or 0),
            "active_critical": int(stats_res[1] or 0),
            "active_warning": int(stats_res[2] or 0),
            "pending": int(stats_res[3] or 0),
            "resolved": int(stats_res[4] or 0)
        }

        # 3. Data Query
        from app.models.mobile import mobile_alerts_table; from app.db.db import users_table
        query = select(
            alerts_table.c.id, alerts_table.c.server_id, alerts_table.c.alert_type,
            alerts_table.c.severity, alerts_table.c.message, alerts_table.c.is_resolved,
            alerts_table.c.created_at, alerts_table.c.resolved_at,
            server_status_table.c.name.label('server_name'), server_status_table.c.ip.label('server_ip'),
            func.max(users_table.c.full_name).label("ack_user_name"), func.max(users_table.c.email).label("ack_user_email"),
            func.max(mobile_alerts_table.c.ert_at).label("ert_at"), func.max(mobile_alerts_table.c.ert_justification).label("ert_justification")
        ).select_from(
            alerts_table.join(server_status_table, alerts_table.c.server_id == server_status_table.c.id, isouter=True)
            .join(mobile_alerts_table, alerts_table.c.id == mobile_alerts_table.c.alert_id, isouter=True)
            .join(users_table, mobile_alerts_table.c.acknowledged_by == users_table.c.id, isouter=True)
        )
        if conditions: query = query.where(and_(*conditions))
        query = query.group_by(alerts_table.c.id, server_status_table.c.name, server_status_table.c.ip)
        query = query.order_by(alerts_table.c.is_resolved.asc(), alerts_table.c.severity.asc(), alerts_table.c.created_at.desc())
        query = query.limit(query_limit).offset(offset)
        
        results = conn.execute(query).fetchall()
        alerts = []
        for r in results:
            parts = r.alert_type.split('.', 1) if r.alert_type else ['', '']
            alerts.append({
                "id": r.id, "server_id": r.server_id, "server_name": r.server_name or "Unknown",
                "server_ip": r.server_ip or "Unknown", "metric_type": parts[0], "metric_key": parts[1] if len(parts)>1 else "",
                "alert_type": r.alert_type, "severity": r.severity, "message": r.message, "is_resolved": r.is_resolved,
                "created_at": to_ist_str(r.created_at), "resolved_at": to_ist_str(r.resolved_at),
                "created_at_raw": r.created_at.isoformat() + 'Z' if r.created_at else None,
                "resolved_at_raw": r.resolved_at.isoformat() + 'Z' if r.resolved_at else None,
                "acknowledged_by_name": r.ack_user_name or r.ack_user_email or "-",
                "ert_at": to_ist_str(r.ert_at), "ert_justification": r.ert_justification
            })
        return {"alerts": alerts, "count": total_count, "stats": summary_stats, "page": page, "page_size": query_limit}

@router.get("/")
def list_alerts(
    start_date: Optional[str] = Query(None), end_date: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None), end_time: Optional[str] = Query(None),
    metric_type: Optional[str] = Query(None), severity: Optional[str] = Query(None),
    is_resolved: Optional[str] = Query(None), 
    environment: str = Depends(get_active_environment),
    page: int = Query(0, ge=0), page_size: int = Query(25, ge=1, le=100), limit: Optional[int] = None
):
    return _get_alerts_data(start_date, end_date, start_time, end_time, metric_type, severity, is_resolved, environment, page, page_size, limit)

@router.get("/export")
def export_alerts_excel(
    start_date: Optional[str] = Query(None), end_date: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None), end_time: Optional[str] = Query(None),
    metric_type: Optional[str] = Query(None), severity: Optional[str] = Query(None),
    is_resolved: Optional[str] = Query(None), 
    environment: str = Depends(get_active_environment)
):
    try:
        res = _get_alerts_data(start_date, end_date, start_time, end_time, metric_type, severity, is_resolved, environment, limit=10000)
        alerts = res["alerts"]
        
        column_mapping = {
            'id': 'Alert ID', 'created_at': 'Triggered At (IST)', 'server_name': 'Server Name', 'server_ip': 'Server IP',
            'alert_type': 'Metric Key', 'severity': 'Severity', 'message': 'Message', 'is_resolved': 'Resolved Status',
            'resolved_at': 'Resolved At (IST)', 'acknowledged_by_name': 'Ack By', 'ert_at': 'ERT Commitment (IST)',
            'ert_justification': 'Justification Reason', 'lifecycle_trail': 'Full Lifecycle / Audit Trail'
        }

        if not alerts:
            df = pd.DataFrame(columns=column_mapping.keys())
        else:
            from app.models.mobile import incident_audit_trail_table; from app.db.db import users_table
            alert_ids = [a['id'] for a in alerts]
            audit_query = select(
                incident_audit_trail_table.c.alert_id, incident_audit_trail_table.c.action,
                incident_audit_trail_table.c.details, incident_audit_trail_table.c.created_at,
                users_table.c.full_name.label("user_name")
            ).select_from(incident_audit_trail_table.outerjoin(users_table)).where(incident_audit_trail_table.c.alert_id.in_(alert_ids)).order_by(incident_audit_trail_table.c.created_at.asc())
            
            with engine.connect() as conn:
                all_audits = conn.execute(audit_query).fetchall()
            
            import json
            audit_map = {}
            for aud in all_audits:
                if aud.alert_id not in audit_map: audit_map[aud.alert_id] = []
                ts = aud.created_at + timedelta(hours=5, minutes=30)
                ts_str = ts.strftime("%H:%M:%S")
                
                # Robustly handle details whether it's a dict or a JSON string
                details = aud.details
                if isinstance(details, str):
                    try: details = json.loads(details)
                    except: details = {}
                elif not details:
                    details = {}
                
                detail_str = ""
                if details.get('ert_minutes'): detail_str = f" (ERT: {details['ert_minutes']}m)"
                if details.get('justification'): detail_str += f" Reason: {details['justification']}"
                audit_map[aud.alert_id].append(f"[{ts_str}] {aud.action} by {aud.user_name or 'System'}{detail_str}")

            for alert in alerts:
                alert['lifecycle_trail'] = " -> ".join(audit_map.get(alert['id'], ["No trail recorded"]))
                for k in column_mapping.keys():
                    if k not in alert: alert[k] = "-"
            df = pd.DataFrame(alerts)
        
        for col in column_mapping.keys():
            if col not in df.columns: df[col] = "-"

        df = df[list(column_mapping.keys())].rename(columns=column_mapping)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Alert History')
            worksheet = writer.sheets['Alert History']
            for idx, col in enumerate(df.columns):
                max_len = max(df[col].apply(lambda x: len(str(x)) if pd.notnull(x) else 0).max(), len(str(col))) + 2
                worksheet.column_dimensions[chr(65 + idx)].width = min(max_len, 50)
        output.seek(0)
        return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=alert_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error exporting alerts: {str(e)}")
