import asyncio
import logging
from datetime import datetime, timedelta
import boto3

logger = logging.getLogger(__name__)

async def run_aws_rds_worker():
    """
    Dedicated worker to pull RDS database metrics from CloudWatch and push to Hot Store.
    """
    while True:
        try:
            logger.info("Starting AWS RDS Polling Cycle...")
            # 1. Fetch AWS accounts & RDS IDs from database_status table
            # 2. Assume Roles via STS
            # 3. Pull FreeableMemory, FreeStorageSpace, Connections via Boto3
            # 4. Save to Redis (Hot Store) -> 'db_status:arn:aws:rds...'
            
            logger.info("Completed AWS RDS Polling Cycle.")
        except Exception as e:
            logger.error(f"Error in AWS RDS Worker: {e}")
            
        await asyncio.sleep(60) # Poll CloudWatch Databases once per minute


async def run_aws_ecs_worker():
    """
    Dedicated worker to pull ECS/Fargate application metrics from CloudWatch.
    """
    while True:
        try:
            logger.info("Starting AWS ECS Polling Cycle...")
            # 1. Fetch ECS ARNs from application_status table
            # 2. Assume Roles via STS
            # 3. Pull CPU, Memory, RequestCount via Boto3
            # 4. Save to Redis (Hot Store) -> 'app_status:arn:aws:ecs...'
            
            logger.info("Completed AWS ECS Polling Cycle.")
        except Exception as e:
            logger.error(f"Error in AWS ECS Worker: {e}")
            
        await asyncio.sleep(60) # Poll CloudWatch Applications once per minute
