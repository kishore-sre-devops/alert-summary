import asyncio
import json
import sys
import os
import logging
from datetime import datetime

sys.path.append(os.path.join(os.getcwd(), "api/backend"))

from app.collectors.aws_collector import AWSCollector
from app.aggregators.metric_mapper import MetricMapper
from app.config.exchange_config import ECS_SERVICES

from app.utils.lama_exchange import get_exchange_credentials, get_enabled_exchanges
from app.utils.lama_token_cache import get_lama_exchange_token
from app.utils.lama_exchange_api import get_next_sequence_id, send_metrics_to_lama_exchange
from app.utils.nse_timestamp import get_nse_timestamp_ms
from app.utils.lama_exchange_constants import APPLICATION_ID_EXCHANGE_CONNECTIVITY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROLE_ARN = "arn:aws:iam::396913716058:role/SMC-LAMA-CrossAccount-ReadOnly"
aws_collector = AWSCollector(role_arn=ROLE_ARN)

def _to_lama_metric_data(mapped: dict) -> list[dict]:
    return [{"key": k, "value": v} for k, v in mapped.items()]

async def collect_application_metrics() -> list[dict]:
    results = []
    mapper = MetricMapper()

    for service in ECS_SERVICES:
        try:
            if service["type"] == "ALB":
                raw = await aws_collector.collect_alb_application_metrics(
                    alb_arn=service["alb_arn"],
                    target_group_arn=service["target_group_arn"],
                )
            elif service["type"] == "NLB":
                raw = await aws_collector.collect_nlb_application_metrics(
                    nlb_arn=service["nlb_arn"],
                    target_group_arn=service["target_group_arn"],
                )
            else:  # BACKGROUND
                raw = await aws_collector.collect_background_service_metrics()

            mapped = mapper.map_application(raw)
            results.append({
                "applicationId": service["application_id"],
                "metricData": _to_lama_metric_data(mapped)
            })

        except Exception as e:
            logger.error(f"Failed collecting app metrics for {service['name']}: {e}")
            results.append({
                "applicationId": service["application_id"],
                "metricData": _to_lama_metric_data(mapper.map_application({}))
            })

    return results

BATCH_SIZE = 5
ENVIRONMENT = "uat"

async def manual_submit():
    print("Starting MANUAL submission of application metrics collection...")
    payload_list = await collect_application_metrics()
    
    creds = get_exchange_credentials(ENVIRONMENT)
    if not creds:
        print(f"No credentials found for {ENVIRONMENT}")
        return
        
    member_id = creds["member_id"]
    exchanges = get_enabled_exchanges(ENVIRONMENT)
    
    for exch_id in exchanges:
        print(f"\n--- Processing for Exchange ID {exch_id} ---")
        token = get_lama_exchange_token(ENVIRONMENT, exch_id, scheduler_name="Manual-App-Submit")
        if not token:
            print(f"Failed to get token for Exchange {exch_id}")
            continue
            
        for i in range(0, len(payload_list), BATCH_SIZE):
            batch = payload_list[i:i + BATCH_SIZE]
            seq = get_next_sequence_id(ENVIRONMENT, member_id, exch_id, "application", scheduler_name="Manual-App-Submit")
            
            if seq is None:
                print(f"Failed to get sequence ID for batch {i // BATCH_SIZE + 1}")
                continue
                
            print(f"\nSubmitting Batch {i // BATCH_SIZE + 1} (Size: {len(batch)} records, Seq: {seq}):")
            
            result = send_metrics_to_lama_exchange(
                environment=ENVIRONMENT,
                member_id=member_id,
                instance_id="App-Metrics-Batch",
                metrics=[],  # Ignored when batched_payload is used
                auth_token=token,
                metric_type="application",
                scheduler_name="Manual-App-Submit",
                server_name="Combined-Apps",
                exchange_id=exch_id,
                application_id=APPLICATION_ID_EXCHANGE_CONNECTIVITY, # Ignored when batched_payload is used
                sequence_id=seq,
                sent_at=datetime.utcnow(),
                nse_timestamp=get_nse_timestamp_ms(),
                skip_705_check=True,
                batched_payload=batch
            )
            
            print(f"Result for Batch {i // BATCH_SIZE + 1}:")
            print(json.dumps(result, indent=2))
            
            # Simple retry on 704
            if str(result.get("response_code")) == "704":
                hint = result.get("exchange_response", {}).get("expectedSequenceId")
                if hint:
                    print(f"Retrying Batch {i // BATCH_SIZE + 1} with suggested sequence ID: {hint}")
                    result = send_metrics_to_lama_exchange(
                        environment=ENVIRONMENT,
                        member_id=member_id,
                        instance_id="App-Metrics-Batch",
                        metrics=[], 
                        auth_token=token,
                        metric_type="application",
                        scheduler_name="Manual-App-Submit",
                        server_name="Combined-Apps",
                        exchange_id=exch_id,
                        application_id=APPLICATION_ID_EXCHANGE_CONNECTIVITY, 
                        sequence_id=int(hint),
                        sent_at=datetime.utcnow(),
                        nse_timestamp=get_nse_timestamp_ms(),
                        skip_705_check=True,
                        batched_payload=batch
                    )
                    print(f"Retry Result:")
                    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(manual_submit())
