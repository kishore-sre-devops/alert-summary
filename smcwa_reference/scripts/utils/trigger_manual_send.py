#!/usr/bin/env python3
"""
Manually trigger LAMA Exchange send for testing
This bypasses the scheduler and sends metrics immediately
"""

import sys
import os

# Add the backend app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'api', 'backend'))

from app.utils.lama_metrics_scheduler import hardware_scheduler, network_scheduler, db_scheduler
import logging

logging.basicConfig(level=logging.INFO)

print("🚀 Manually triggering LAMA Exchange send...")
print("This will execute the live Hardware, Network, and DB schedulers.")
print("")

try:
    print("📤 Triggering Hardware Scheduler...")
    hardware_scheduler()
    print("✅ Hardware send process triggered")
    
    print("📤 Triggering Network Scheduler...")
    network_scheduler()
    print("✅ Network send process triggered")
    
    print("📤 Triggering DB Scheduler...")
    db_scheduler()
    print("✅ DB send process triggered")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("")
print("✅ Manual trigger sequence complete!")
print("Check Exchange Activity dashboard to see results.")