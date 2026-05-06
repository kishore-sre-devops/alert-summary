
import sys
import os

# Add the backend directory to sys.path
sys.path.append(os.path.join(os.getcwd(), 'api/backend'))

from app.db.db import engine, application_status_table, database_status_table, server_status_table, lama_exchange_server_selection_table
from sqlalchemy import select, delete, text

def cleanup_orphaned_ecs():
    services_to_delete = [
        "smc-trade-midw-ecs-fargate/smc-trade-midw-login-etl-jobs-prod-td-service-rfrb1jqg",
        "smc-trade-midw-ecs-fargate/smc-trade-midw-login-etl-jobs-prod-td-service-j3i3pj4x"
    ]
    
    with engine.begin() as conn:
        for svc_name in services_to_delete:
            # We search for names containing the service name since they might have prefixes like [SMC-TRADING-MIDDLEWARE-PROD]
            print(f"Searching for service: {svc_name}")
            
            # Find the IDs first so we can clean up server_selection too
            query = select(application_status_table.c.id, application_status_table.c.name).where(
                application_status_table.c.name.like(f"%{svc_name}%")
            )
            results = conn.execute(query).fetchall()
            
            for app_id, full_name in results:
                print(f"Found match: {full_name} (ID: {app_id})")
                
                # 1. Delete from lama_exchange_server_selection if metric_source is 'application'
                # Note: This is a bit risky if IDs overlap, but aws_discovery.py uses it this way
                del_sel = delete(lama_exchange_server_selection_table).where(
                    (lama_exchange_server_selection_table.c.server_id == app_id) & 
                    (lama_exchange_server_selection_table.c.metric_source == 'application')
                )
                res_sel = conn.execute(del_sel)
                print(f"  Deleted {res_sel.rowcount} entries from lama_exchange_server_selection")
                
                # 2. Delete from application_status
                del_app = delete(application_status_table).where(application_status_table.c.id == app_id)
                res_app = conn.execute(del_app)
                print(f"  Deleted from application_status: {res_app.rowcount}")

        # Also cleanup any application_status where source_id is NULL and external_id starts with 'arn:aws:ecs'
        # which indicates they were discovered from ECS but their source is now gone.
        print("\nChecking for other orphaned ECS services (source_id is NULL)...")
        query_orphans = select(application_status_table.c.id, application_status_table.c.name).where(
            (application_status_table.c.source_id == None) & 
            (application_status_table.c.external_id.like("arn:aws:ecs:%"))
        )
        orphans = conn.execute(query_orphans).fetchall()
        for app_id, full_name in orphans:
            print(f"Found orphaned ECS service: {full_name} (ID: {app_id})")
            
            # Cleanup server selection
            del_sel = delete(lama_exchange_server_selection_table).where(
                (lama_exchange_server_selection_table.c.server_id == app_id) & 
                (lama_exchange_server_selection_table.c.metric_source == 'application')
            )
            conn.execute(del_sel)
            
            # Delete application status
            del_app = delete(application_status_table).where(application_status_table.c.id == app_id)
            conn.execute(del_app)
            print(f"  Cleaned up orphan {full_name}")

if __name__ == "__main__":
    cleanup_orphaned_ecs()
