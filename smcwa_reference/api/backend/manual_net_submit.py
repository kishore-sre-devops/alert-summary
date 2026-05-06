import asyncio
import json
import sys
import os
import logging
from datetime import datetime
import statistics

sys.path.append(os.path.join(os.getcwd(), "api/backend"))

from app.collectors.aws_collector import AWSCollector
from app.aggregators.metric_mapper import MetricMapper
from app.config.exchange_config import ECS_SERVICES

from app.utils.lama_exchange import get_exchange_credentials, get_enabled_exchanges
from app.utils.lama_token_cache import get_lama_exchange_token
from app.utils.lama_exchange_api import get_next_sequence_id, send_metrics_to_lama_exchange
from app.utils.nse_timestamp import get_nse_timestamp_ms
from app.utils.lama_exchange_constants import APPLICATION_ID_NOT_APPLICABLE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROLE_ARN = "arn:aws:iam::396913716058:role/SMC-LAMA-CrossAccount-ReadOnly"
aws_collector = AWSCollector(role_arn=ROLE_ARN)

def agg_stat(stat_list, key, agg_func):
    vals = [s[key] for s in stat_list]
    if not vals: return 0.0
    return round(agg_func(vals), 3)

async def collect_network_metrics() -> dict:
    alb_bw_list = []
    nlb_bw_list = []
    alb_lat_list = []
    total_packet_count = 0

    for svc in ECS_SERVICES:
        if svc["type"] == "ALB":
            res = await aws_collector.collect_alb_network_metrics(svc["alb_arn"])
            alb_bw_list.append(res["bandwidth"])
            alb_lat_list.append(res["latency"])
        elif svc["type"] == "NLB":
            res = await aws_collector.collect_nlb_network_metrics(svc["nlb_arn"])
            nlb_bw_list.append(res["bandwidth"])
            total_packet_count += res["packetCount"]

    all_bw = alb_bw_list + nlb_bw_list

    agg_bw = {
        "min": agg_stat(all_bw, "min", min),
        "max": agg_stat(all_bw, "max", max),
        "avg": agg_stat(all_bw, "avg", statistics.mean),
        "med": agg_stat(all_bw, "med", statistics.mean)
    } if all_bw else {"min": 0, "max": 0, "avg": 0, "med": 0}

    agg_lat = {
        "min": agg_stat(alb_lat_list, "min", min),
        "max": agg_stat(alb_lat_list, "max", max),
        "avg": agg_stat(alb_lat_list, "avg", statistics.mean),
        "med": agg_stat(alb_lat_list, "med", statistics.mean)
    } if alb_lat_list else {"min": 0, "max": 0, "avg": 0, "med": 0}

    return {
        "bandwidth": agg_bw,
        "latency": agg_lat,
        "packetCount": total_packet_count,
        "lookupCount": 0
    }


ENVIRONMENT = "uat"

async def manual_submit():
    print("Starting MANUAL submission of network metrics collection...")
    raw_payload = await collect_network_metrics()
    
    mapper = MetricMapper()
    mapped_payload = mapper.map_network(raw_payload)
    
    final_metrics = [{"name": k, **v} if isinstance(v, dict) else {"name": k, "value": v} for k, v in mapped_payload.items()]
    
    creds = get_exchange_credentials(ENVIRONMENT)
    if not creds:
        print(f"No credentials found for {ENVIRONMENT}")
        return
        
    member_id = creds["member_id"]
    exchanges = get_enabled_exchanges(ENVIRONMENT)
    
    for exch_id in exchanges:
        print(f"\n--- Processing for Exchange ID {exch_id} ---")
        token = get_lama_exchange_token(ENVIRONMENT, exch_id, scheduler_name="Manual-Net-Submit")
        if not token:
            print(f"Failed to get token for Exchange {exch_id}")
            continue
            
        seq = get_next_sequence_id(ENVIRONMENT, member_id, exch_id, "network", scheduler_name="Manual-Net-Submit")
        
        if seq is None:
            print(f"Failed to get sequence ID")
            continue
            
        print(f"\nSubmitting Payload (Seq: {seq}):")
        
        result = send_metrics_to_lama_exchange(
            environment=ENVIRONMENT,
            member_id=member_id,
            instance_id="combined",
            metrics=final_metrics,
            auth_token=token,
            metric_type="network",
            scheduler_name="Manual-Net-Submit",
            server_name="AWS_NETWORK",
            exchange_id=exch_id,
            application_id=APPLICATION_ID_NOT_APPLICABLE,
            sequence_id=seq,
            sent_at=datetime.utcnow(),
            nse_timestamp=get_nse_timestamp_ms(),
            skip_705_check=True,
            stored_metrics=final_metrics
        )
        
        print(f"Result:")
        print(json.dumps(result, indent=2))
        
        # Simple retry on 704
        if str(result.get("response_code")) == "704":
            hint = result.get("exchange_response", {}).get("expectedSequenceId")
            if hint:
                print(f"Retrying with suggested sequence ID: {hint}")
                result = send_metrics_to_lama_exchange(
                    environment=ENVIRONMENT,
                    member_id=member_id,
                    instance_id="combined",
                    metrics=final_metrics, 
                    auth_token=token,
                    metric_type="network",
                    scheduler_name="Manual-Net-Submit",
                    server_name="AWS_NETWORK",
                    exchange_id=exch_id,
                    application_id=APPLICATION_ID_NOT_APPLICABLE, 
                    sequence_id=int(hint),
                    sent_at=datetime.utcnow(),
                    nse_timestamp=get_nse_timestamp_ms(),
                    skip_705_check=True,
                    stored_metrics=final_metrics
                )
                print(f"Retry Result:")
                print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(manual_submit())
