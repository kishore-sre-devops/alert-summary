import asyncio
import json
import sys
import os
import logging
from datetime import datetime
import time

sys.path.append(os.path.join(os.getcwd(), "api/backend"))

from app.schedulers.hardware import collect_all_hardware_metrics, BATCH_SIZE
from app.utils.lama_exchange import get_exchange_credentials, get_enabled_exchanges
from app.utils.lama_token_cache import get_lama_exchange_token
from app.utils.lama_exchange_api import get_next_sequence_id, send_metrics_to_lama_exchange
from app.utils.nse_timestamp import get_nse_timestamp_ms

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ENVIRONMENT = "uat"

async def manual_submit():
    print("Starting MANUAL submission of hardware metrics collection...")
    enabled_envs = [ENVIRONMENT]
    all_metrics = await collect_all_hardware_metrics(enabled_envs)
    
    creds = get_exchange_credentials(ENVIRONMENT)
    if not creds:
        print(f"No credentials found for {ENVIRONMENT}")
        return
        
    member_id = creds["member_id"]
    exchanges = get_enabled_exchanges(ENVIRONMENT)
    
    env_metrics = [m for m in all_metrics if m["environment"] == ENVIRONMENT]

    metrics_by_loc = {}
    for m in env_metrics:
        loc = m["locationId"]
        if loc not in metrics_by_loc: metrics_by_loc[loc] = []
        metrics_by_loc[loc].append(m)
        
    for exch_id in exchanges:
        print(f"\n--- Processing for Exchange ID {exch_id} ---")
        token = get_lama_exchange_token(ENVIRONMENT, exch_id, scheduler_name="Manual-HW-Submit")
        if not token:
            print(f"Failed to get token for Exchange {exch_id}")
            continue

        for loc_id, loc_metrics in metrics_by_loc.items():
            print(f"\n--- Location ID {loc_id} ({len(loc_metrics)} servers) ---")
            
            for i in range(0, len(loc_metrics), BATCH_SIZE):
                batch = loc_metrics[i:i + BATCH_SIZE]
                batch_server_names = ", ".join([b["server_name"] for b in batch])
                
                batched_payload = []
                for b in batch:
                    batched_payload.append({
                        "applicationId": b["applicationId"],
                        "metricData": b["metricData"]
                    })
                
                seq = get_next_sequence_id(ENVIRONMENT, member_id, exch_id, "hardware", scheduler_name="Manual-HW-Submit")
                if seq is None: continue
                
                print(f"\nSubmitting Batch (Seq: {seq}) for servers: {batch_server_names}")
                
                result = send_metrics_to_lama_exchange(
                    environment=ENVIRONMENT,
                    member_id=member_id,
                    instance_id="combined",
                    metrics=[],
                    auth_token=token,
                    metric_type="hardware",
                    scheduler_name="Manual-HW-Submit",
                    server_name=batch_server_names,
                    exchange_id=exch_id,
                    application_id=4,
                    sequence_id=seq,
                    sent_at=datetime.utcnow(),
                    nse_timestamp=get_nse_timestamp_ms(),
                    skip_705_check=True,
                    location_id=loc_id,
                    batched_payload=batched_payload
                )
                
                print(f"Result:")
                print(json.dumps(result, indent=2))
                
                if str(result.get("response_code")) == "704":
                    hint = result.get("exchange_response", {}).get("expectedSequenceId")
                    if hint:
                        print(f"Retrying with suggested sequence ID: {hint}")
                        result = send_metrics_to_lama_exchange(
                            environment=ENVIRONMENT,
                            member_id=member_id,
                            instance_id="combined",
                            metrics=[], 
                            auth_token=token,
                            metric_type="hardware",
                            scheduler_name="Manual-HW-Submit",
                            server_name=batch_server_names,
                            exchange_id=exch_id,
                            application_id=4, 
                            sequence_id=int(hint),
                            sent_at=datetime.utcnow(),
                            nse_timestamp=get_nse_timestamp_ms(),
                            skip_705_check=True,
                            location_id=loc_id,
                            batched_payload=batched_payload
                        )
                        print(f"Retry Result:")
                        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(manual_submit())
