from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    received_at = Column("time", DateTime, default=datetime.utcnow)
    alertname = Column("AlertName", String(255), index=True)
    instance = Column("Instance", String(255), index=True)
    job = Column("job_name", String(255))
    company = Column("Company", String(255))
    group_name = Column("Group", String(255))
    group1 = Column(String(255), nullable=True, default="")
    asset = Column("Asset", String(255), nullable=True)
    disk_info = Column("Volume / MountPoint", String(100), nullable=True)
    status = Column(String(50), index=True)  # firing or resolved
    severity = Column("Severity", String(100), nullable=True)
    cluster = Column(String(255), nullable=True)
    starts_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)
    fingerprint = Column(String(255), unique=True, index=True)

    # Improvements
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Acknowledgment fields
    acknowledged_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    is_silenced = Column(Integer, default=0) # 0 = not silenced, 1 = silenced

    comments = relationship("Comment", back_populates="alert", cascade="all, delete-orphan")
    acknowledged_by_user = relationship("User")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    device_name = Column(String(255), nullable=True)
    os_version = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    groups = relationship("UserGroup", back_populates="user", cascade="all, delete-orphan")

class UserGroup(Base):
    __tablename__ = "user_groups"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    group_name = Column(String(255), nullable=False)

    user = relationship("User", back_populates="groups")

class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    alert = relationship("Alert", back_populates="comments")

class SilenceRule(Base):
    __tablename__ = "silence_rules"

    id = Column(Integer, primary_key=True, index=True)
    instance = Column(String(255), nullable=True) # Pattern or exact
    alertname = Column(String(255), nullable=True)
    company = Column(String(255), nullable=True)
    group1 = Column(String(255), nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Integer, default=1)

class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    token = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")

class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PrometheusServer(Base):
    __tablename__ = "prometheus_servers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True)
    url = Column(String(255), nullable=False)
    is_active = Column(Integer, default=1)
    status = Column(String(50), default="unknown") # online, offline, unknown
    last_checked = Column(DateTime, nullable=True)

class AlertGroupConfig(Base):
    __tablename__ = "alert_group_configs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True)
    emails = Column(Text, nullable=True) # Comma separated
    slack_webhook = Column(String(255), nullable=True)
    voice_enabled = Column(Integer, default=0)

class PrometheusTarget(Base):
    __tablename__ = "prometheus_targets"
    id = Column(Integer, primary_key=True, index=True)
    instance = Column(String(255), index=True)
    job = Column(String(255), nullable=True)
    group_name = Column(String(255), nullable=True)
    group1 = Column(String(255), nullable=True)
    company = Column(String(255), nullable=True)
    asset = Column(String(255), nullable=True)
    server_id = Column(Integer, ForeignKey("prometheus_servers.id"))
    last_seen = Column(DateTime, default=datetime.utcnow)

    server = relationship("PrometheusServer")

class AlertRule(Base):
    __tablename__ = "alert_rules"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    promql = Column(Text, nullable=False)
    severity = Column(String(50), default="warning")
    summary = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    group_id = Column(Integer, ForeignKey("alert_group_configs.id"), nullable=True)
    duration = Column(String(50), default="60s")
    is_active = Column(Integer, default=1)
    
    group = relationship("AlertGroupConfig")
    # Added for multiple groups support
    notification_groups = relationship("AlertGroupConfig", secondary="alert_rule_group_association", backref="alert_rules_multi")

class AlertRuleGroupAssociation(Base):
    __tablename__ = "alert_rule_group_association"
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), primary_key=True)
    group_id = Column(Integer, ForeignKey("alert_group_configs.id"), primary_key=True)

class AlertState(Base):
    __tablename__ = "alert_state"
    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"))
    alert_name = Column(String(255), index=True)
    instance = Column(String(255), index=True)
    cluster = Column(String(255), index=True)
    group_name = Column(String(255))
    team = Column(String(255))
    status = Column(String(50)) # firing, resolved
    severity = Column(String(50))
    starts_at = Column(DateTime, default=datetime.utcnow)
    ends_at = Column(DateTime, nullable=True)
    last_notified_at = Column(DateTime, nullable=True)
    fingerprint = Column(String(255), unique=True, index=True)

    rule = relationship("AlertRule")

