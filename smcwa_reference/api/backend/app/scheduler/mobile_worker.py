from apscheduler.schedulers.background import BackgroundScheduler
from app.services.escalation import process_escalations
import asyncio
import logging

logger = logging.getLogger(__name__)

# This worker handles background tasks for mobile alerting
# It can be run as a separate process or attached to the main scheduler

async def run_escalation_check():
    logger.info("Running escalation check...")
    await process_escalations()

def start_mobile_scheduler():
    scheduler = BackgroundScheduler()
    
    # Wrap async function for blocking scheduler
    def job_wrapper():
        asyncio.run(run_escalation_check())

    scheduler.add_job(job_wrapper, 'interval', seconds=60, id='mobile_escalation')
    scheduler.start()
    logger.info("Mobile scheduler started")
    return scheduler
