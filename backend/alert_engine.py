import asyncio
import httpx
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Alert, PrometheusServer, AlertRule, AlertState, AlertGroupConfig
from notifications import notify
import hashlib

async def create_alert_log(db, rule, instance, cluster, group_name, team, status, now, ends_at, fingerprint, metric_labels=None):
    """Creates a record in the Alert (history) table"""
    disk_info = None
    if rule.description:
        # Check for volume or mountpoint pattern, replace $labels.XXX with metric labels
        if "$labels.volume" in rule.description and metric_labels:
            disk_info = metric_labels.get("volume")
        elif "$labels.mountpoint" in rule.description and metric_labels:
            disk_info = metric_labels.get("mountpoint")
            
    alert_log = Alert(
        received_at=now,
        alertname=rule.name,
        instance=instance,
        job=team, # Using team as job
        group_name=group_name,
        status=status,
        severity=rule.severity,
        disk_info=disk_info,
        starts_at=now if status == "firing" else None,
        ends_at=ends_at,
        fingerprint=f"{fingerprint}_{now.timestamp()}",
        cluster=cluster
    )
    db.add(alert_log)
    db.commit()

async def query_prometheus(url, query):
    async with httpx.AsyncClient() as client:
        try:
            # Add timeout to avoid hanging
            response = await client.get(f"{url}/api/v1/query", params={"query": query}, timeout=10.0)
            response.raise_for_status()
            return response.json().get("data", {}).get("result", [])
        except Exception as e:
            print(f"Error querying Prometheus {url}: {e}")
            return []

async def fetch_prometheus_alerts(url):
    """Fetches currently firing alerts directly from Prometheus API"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{url}/api/v1/alerts", timeout=10.0)
            response.raise_for_status()
            return response.json().get("data", {}).get("alerts", [])
        except Exception as e:
            print(f"Error fetching alerts from Prometheus {url}: {e}")
            return []

def generate_fingerprint(alert_name, instance, cluster):
    key = f"{alert_name}{instance}{cluster}"
    return hashlib.md5(key.encode()).hexdigest()

async def evaluate_rules():
    db = SessionLocal()
    try:
        servers = db.query(PrometheusServer).filter(PrometheusServer.is_active == 1).all()
        rules = db.query(AlertRule).filter(AlertRule.is_active == 1).all()
        
        active_fingerprints = set()

        for server in servers:
            # Check server health
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{server.url}/-/healthy", timeout=5.0)
                    server.status = "online" if resp.status_code == 200 else "offline"
            except Exception:
                server.status = "offline"
            
            server.last_checked = datetime.utcnow()
            db.commit()

            if server.status == "offline":
                print(f"⚠️ Prometheus server {server.name} ({server.url}) is OFFLINE. Skipping rules evaluation.")
                continue

            # Phase 1: Custom local rules evaluation (PromQL queries)
            for rule in rules:
                results = await query_prometheus(server.url, rule.promql)
                
                for res in results:
                    metric = res.get("metric", {})
                    # Prefer labels from metric, fallback to server name for cluster
                    instance = metric.get("instance", "unknown")
                    cluster = metric.get("cluster", server.name)
                    group_name = metric.get("group", "unknown")
                    team = metric.get("team", "unknown")
                    
                    fingerprint = generate_fingerprint(rule.name, instance, cluster)
                    active_fingerprints.add(fingerprint)
                    
                    # Check if alert already exists in active state
                    alert_state = db.query(AlertState).filter(AlertState.fingerprint == fingerprint).first()
                    
                    now = datetime.utcnow()
                    
                    if not alert_state:
                        # New alert
                        alert_state = AlertState(
                            rule_id=rule.id,
                            alert_name=rule.name,
                            instance=instance,
                            cluster=cluster,
                            group_name=group_name,
                            team=team,
                            status="firing",
                            severity=rule.severity,
                            starts_at=now,
                            last_notified_at=now,
                            fingerprint=fingerprint
                        )
                        db.add(alert_state)
                        db.commit()
                        
                        # Add to history
                        await create_alert_log(db, rule, instance, cluster, group_name, team, "firing", now, None, fingerprint, metric_labels=metric)
                        
                        # Notify
                        groups_to_notify = rule.notification_groups if rule.notification_groups else []
                        # Fallback to group_id if notification_groups is empty
                        if not groups_to_notify and rule.group_id:
                            fallback_group = db.query(AlertGroupConfig).filter(AlertGroupConfig.id == rule.group_id).first()
                            if fallback_group:
                                groups_to_notify = [fallback_group]
                                
                        for group_config in groups_to_notify:
                            await notify(group_config, {
                                "alert_name": rule.name,
                                "instance": instance,
                                "cluster": cluster,
                                "group": group_name,
                                "team": team,
                                "severity": rule.severity,
                                "status": "firing",
                                "startsAt": now.isoformat()
                            })
                    else:
                        # Existing alert
                        if alert_state.status == "resolved":
                            # Re-firing
                            alert_state.status = "firing"
                            alert_state.starts_at = now
                            alert_state.ends_at = None
                            alert_state.last_notified_at = now
                            db.commit()
                            
                            # Add repeat log to history
                            await create_alert_log(db, rule, instance, cluster, group_name, team, "firing", now, None, fingerprint, metric_labels=metric)


                            # Notify
                            groups_to_notify = rule.notification_groups if rule.notification_groups else []
                            if not groups_to_notify and rule.group_id:
                                fallback_group = db.query(AlertGroupConfig).filter(AlertGroupConfig.id == rule.group_id).first()
                                if fallback_group:
                                    groups_to_notify = [fallback_group]
                                    
                            for group_config in groups_to_notify:
                                await notify(group_config, {
                                    "alert_name": rule.name,
                                    "instance": instance,
                                    "cluster": cluster,
                                    "group": group_name,
                                    "team": team,
                                    "severity": rule.severity,
                                    "status": "firing",
                                    "startsAt": now.isoformat()
                                })
                        else:
                            # Still firing - apply cooldown check if we were to re-notify
                            # Log repeated alert to history every hour
                            if not alert_state.last_notified_at or (now - alert_state.last_notified_at).total_seconds() >= 3600:
                                alert_state.last_notified_at = now
                                db.commit()
                                # Add repeat log to history
                                await create_alert_log(db, rule, instance, cluster, group_name, team, "firing", now, None, fingerprint, metric_labels=metric)
        # Handle resolved alerts
        firing_alerts = db.query(AlertState).filter(AlertState.status == "firing").all()
        for alert in firing_alerts:
            if alert.fingerprint not in active_fingerprints:
                # Alert resolved
                alert.status = "resolved"
                alert.ends_at = datetime.utcnow()
                db.commit()
                
                # Add to history
                rule = db.query(AlertRule).filter(AlertRule.id == alert.rule_id).first()
                if rule:
                    await create_alert_log(db, rule, alert.instance, alert.cluster, alert.group_name, alert.team, "resolved", alert.ends_at, alert.ends_at, alert.fingerprint)

                # Notify resolved
                if rule:
                    groups_to_notify = rule.notification_groups if rule.notification_groups else []
                    if not groups_to_notify and rule.group_id:
                        fallback_group = db.query(AlertGroupConfig).filter(AlertGroupConfig.id == rule.group_id).first()
                        if fallback_group:
                            groups_to_notify = [fallback_group]
                            
                    for group_config in groups_to_notify:
                        await notify(group_config, {
                            "alert_name": alert.alert_name,
                            "instance": alert.instance,
                            "cluster": alert.cluster,
                            "group": alert.group_name,
                            "team": alert.team,
                            "severity": alert.severity,
                            "status": "resolved",
                            "startsAt": alert.starts_at.isoformat()
                        })

    except Exception as e:
        print(f"Error in alert engine: {e}")
    finally:
        db.close()

async def run_alert_engine():
    print("Starting Alert Engine...")
    while True:
        try:
            await evaluate_rules()
        except Exception as e:
            print(f"Alert Engine Loop Error: {e}")
        await asyncio.sleep(30)
