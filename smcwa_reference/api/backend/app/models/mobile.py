from sqlalchemy import Table, Column, Integer, String, DateTime, Boolean, ForeignKey, JSON, Text, BigInteger, UniqueConstraint
from app.db.db import metadata
from datetime import datetime

# Mobile Devices Table
mobile_devices_table = Table(
    "mobile_devices",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("push_token", String(255), nullable=True, unique=True),
    Column("device_os", String(20), nullable=False),  # 'android' or 'ios'
    Column("device_name", String(100), nullable=True),
    Column("app_version", String(20), nullable=True),
    Column("is_logged_in", Boolean, default=True),
    Column("last_active_at", DateTime, default=datetime.utcnow),
    Column("created_at", DateTime, default=datetime.utcnow)
)

# Escalation Policies Table
escalation_policies_table = Table(
    "escalation_policies",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("steps", JSON, nullable=False),  # Array of steps: [{delay: 0, notify: [user_id_1]}, {delay: 5, notify: [user_id_2]}]
    Column("enabled", Boolean, default=True),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
)

# Active Escalations Table
active_escalations_table = Table(
    "active_escalations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("alert_id", Integer, ForeignKey("alerts.id", ondelete="CASCADE"), unique=True, nullable=False),
    Column("policy_id", Integer, ForeignKey("escalation_policies.id", ondelete="SET NULL"), nullable=True),
    Column("current_step", Integer, default=0),
    Column("next_escalation_at", DateTime),
    Column("last_processed_at", DateTime, nullable=True),
    Column("status", String(20), default="active"),  # 'active', 'completed', 'resolved'
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    Column("ert_at", DateTime, nullable=True),
    Column("ert_justification", Text, nullable=True)
)

# Mobile Alerts Table (History/Tracking)
mobile_alerts_table = Table(
    "mobile_alerts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("alert_id", Integer, ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    Column("title", String(255), nullable=False),
    Column("body", Text, nullable=False),
    Column("data", JSON, nullable=True),
    Column("severity", String(20), default="info"),
    Column("status", String(20), default="sent"),  # 'sent', 'acknowledged', 'failed'
    Column("acknowledged_by", Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    Column("acknowledged_at", DateTime, nullable=True),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("ert_at", DateTime, nullable=True),
    Column("ert_justification", Text, nullable=True),
    UniqueConstraint("alert_id", "user_id", name="unique_alert_user")
)

# Incident Audit Trail Table
incident_audit_trail_table = Table(
    "incident_audit_trail",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("alert_id", Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
    Column("action", String(100), nullable=False), # 'Triggered', 'Acknowledge', 'Escalated', 'Resolved', 'ERT Expired'
    Column("user_id", Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    Column("details", JSON, nullable=True), # Structured details: {ert_minutes, justification, etc.}
    Column("created_at", DateTime, default=datetime.utcnow)
)
