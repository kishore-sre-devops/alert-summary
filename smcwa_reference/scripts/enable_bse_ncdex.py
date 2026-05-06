#!/usr/bin/env python3
"""
Script to enable BSE (Exchange ID: 2) and NCDEX (Exchange ID: 5) for LAMA Exchange
This script adds/updates records in the lama_exchange_config table
"""

import sys
import os
from datetime import datetime

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api', 'backend'))

from app.db.db import engine, lama_exchange_config_table
from sqlalchemy import select, insert, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

def enable_exchanges():
    """Enable all exchanges (NSE, BSE, MCX, NCDEX) for both UAT and PROD environments"""
    
    exchanges_to_enable = [
        # UAT exchanges
        {'environment': 'uat', 'exchange_id': 1, 'name': 'NSE'},
        {'environment': 'uat', 'exchange_id': 2, 'name': 'BSE'},
        {'environment': 'uat', 'exchange_id': 4, 'name': 'MCX'},
        {'environment': 'uat', 'exchange_id': 5, 'name': 'NCDEX'},
        # PROD exchanges (will only work if PROD environment is enabled)
        {'environment': 'prod', 'exchange_id': 1, 'name': 'NSE'},
        {'environment': 'prod', 'exchange_id': 2, 'name': 'BSE'},
        {'environment': 'prod', 'exchange_id': 4, 'name': 'MCX'},
        {'environment': 'prod', 'exchange_id': 5, 'name': 'NCDEX'},
    ]
    
    print("=" * 60)
    print("Enabling All Exchanges (NSE, BSE, MCX, NCDEX)")
    print("=" * 60)
    
    try:
        with engine.connect() as conn:
            for exchange in exchanges_to_enable:
                env = exchange['environment']
                exchange_id = exchange['exchange_id']
                name = exchange['name']
                
                # Check if record exists
                check_query = select(lama_exchange_config_table).where(
                    lama_exchange_config_table.c.environment == env,
                    lama_exchange_config_table.c.exchange_id == exchange_id
                )
                existing = conn.execute(check_query).fetchone()
                
                if existing:
                    # Update existing record
                    update_query = update(lama_exchange_config_table).where(
                        lama_exchange_config_table.c.environment == env,
                        lama_exchange_config_table.c.exchange_id == exchange_id
                    ).values(
                        enabled=True,
                        updated_at=datetime.utcnow()
                    )
                    conn.execute(update_query)
                    print(f"✅ Updated: {env.upper()} {name} (Exchange ID: {exchange_id}) - ENABLED")
                else:
                    # Insert new record
                    insert_query = lama_exchange_config_table.insert().values(
                        environment=env,
                        exchange_id=exchange_id,
                        enabled=True,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    conn.execute(insert_query)
                    print(f"✅ Created: {env.upper()} {name} (Exchange ID: {exchange_id}) - ENABLED")
            
            conn.commit()
            print("\n" + "=" * 60)
            print("✅ All exchanges enabled successfully!")
            print("=" * 60)
            
            # Verify enabled exchanges
            print("\nVerifying enabled exchanges...")
            for env in ['uat', 'prod']:
                query = select(lama_exchange_config_table).where(
                    lama_exchange_config_table.c.environment == env,
                    lama_exchange_config_table.c.enabled == True
                ).order_by(lama_exchange_config_table.c.exchange_id)
                results = conn.execute(query).fetchall()
                
                exchange_names = {1: 'NSE', 2: 'BSE', 4: 'MCX', 5: 'NCDEX'}
                enabled_list = [exchange_names.get(row[2], f"Exchange {row[2]}") for row in results]
                
                print(f"\n{env.upper()} Environment - Enabled Exchanges:")
                for name in enabled_list:
                    print(f"  - {name}")
                print(f"  Total: {len(enabled_list)} exchange(s)")
            
            return True
            
    except Exception as e:
        print(f"\n❌ Error enabling exchanges: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = enable_exchanges()
    sys.exit(0 if success else 1)

