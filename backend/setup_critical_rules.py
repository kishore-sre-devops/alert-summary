from database import SessionLocal
from models import AlertRule, AlertGroupConfig
import os

def setup_critical_rules():
    db = SessionLocal()
    try:
        default_group = db.query(AlertGroupConfig).filter(AlertGroupConfig.name == 'Default').first()
        group_id = default_group.id if default_group else 1

        # 1. Update Instance Down to Critical
        instance_down = db.query(AlertRule).filter(AlertRule.name == 'InstanceDown').first()
        if instance_down:
            print(f"Updating {instance_down.name} to Critical")
            instance_down.severity = 'critical'
        else:
            print("Creating InstanceDown rule")
            db.add(AlertRule(
                name='InstanceDown',
                promql='up == 0',
                severity='critical',
                group_id=group_id,
                duration='1m'
            ))

        # 2. Add CPU Usage (50% to 95%) - Critical
        # Using a generic node_exporter metric as example
        cpu_query = '(100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100) > 50) and (100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100) <= 95)'
        
        existing_cpu = db.query(AlertRule).filter(AlertRule.name == 'CriticalCPU_50_95').first()
        if not existing_cpu:
            print("Adding Critical CPU (50-95%) rule")
            db.add(AlertRule(
                name='CriticalCPU_50_95',
                promql=cpu_query,
                severity='critical',
                group_id=group_id,
                duration='2m'
            ))
        else:
            existing_cpu.promql = cpu_query
            existing_cpu.severity = 'critical'

        # 3. Add Disk Usage (50% to 95%) - Critical
        disk_query = '(100 - (node_filesystem_free_bytes / node_filesystem_size_bytes * 100) > 50) and (100 - (node_filesystem_free_bytes / node_filesystem_size_bytes * 100) <= 95)'
        
        existing_disk = db.query(AlertRule).filter(AlertRule.name == 'CriticalDisk_50_95').first()
        if not existing_disk:
            print("Adding Critical Disk (50-95%) rule")
            db.add(AlertRule(
                name='CriticalDisk_50_95',
                promql=disk_query,
                severity='critical',
                group_id=group_id,
                duration='2m'
            ))
        else:
            existing_disk.promql = disk_query
            existing_disk.severity = 'critical'

        # 4. Add Memory Usage (50% to 95%) - Critical
        # Generic node_exporter memory query
        mem_query = '(100 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100) > 50) and (100 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100) <= 95)'
        
        existing_mem = db.query(AlertRule).filter(AlertRule.name == 'CriticalMemory_50_95').first()
        if not existing_mem:
            print("Adding Critical Memory (50-95%) rule")
            db.add(AlertRule(
                name='CriticalMemory_50_95',
                promql=mem_query,
                severity='critical',
                group_id=group_id,
                duration='2m'
            ))
        else:
            existing_mem.promql = mem_query
            existing_mem.severity = 'critical'

        db.commit()
        print("Successfully updated critical rules.")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    setup_critical_rules()
