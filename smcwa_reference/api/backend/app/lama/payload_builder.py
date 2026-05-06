"""
LAMA Payload Builder & Utils: SMC LAMA V2.0 Implementation
"""
import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# NSE Epoch: Milliseconds since 1980-01-01
NSE_EPOCH = datetime(1980, 1, 1)

def to_nse_epoch_ms(dt: datetime = None) -> int:
    """Convert datetime to NSE Epoch (ms since 1980)"""
    if dt is None:
        dt = datetime.utcnow()
    # Ensure dt is timezone-naive for direct subtraction with NSE_EPOCH
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    delta = dt - NSE_EPOCH
    return int(delta.total_seconds() * 1000)

class LamaPayloadBuilder:
    @staticmethod
    def build_hardware_payload(aggregated_data: Dict[str, Any], 
                               sequence_id: int, 
                               member_id: str, 
                               login_id: str,
                               server_id: str,
                               location_id: int = 1) -> Dict[str, Any]:
        """Builds /metrics/hardware payload for a single server"""
        
        # Mapping aggregated stats to LAMA keys
        cpu = aggregated_data.get("cpu", {"min": 0, "max": 0, "avg": 0, "med": 0})
        memory = aggregated_data.get("memory", {"min": 0, "max": 0, "avg": 0, "med": 0})
        disk = aggregated_data.get("disk", {"min": 0, "max": 0, "avg": 0, "med": 0})
        uptime = aggregated_data.get("uptime", {"avg": 0}).get("avg", 0)
        
        return {
            "memberId": member_id,
            "loginId": login_id,
            "sequenceId": sequence_id,
            "timestamp": to_nse_epoch_ms(),
            "locationId": location_id,
            "metrics": [
                {
                    "serverId": server_id,
                    "cpu": {
                        "min": cpu["min"],
                        "max": cpu["max"],
                        "avg": cpu["avg"],
                        "med": cpu["med"]
                    },
                    "memory": {
                        "min": memory["min"],
                        "max": memory["max"],
                        "avg": memory["avg"],
                        "med": memory["med"]
                    },
                    "disk": {
                        "min": disk["min"],
                        "max": disk["max"],
                        "avg": disk["avg"],
                        "med": disk["med"]
                    },
                    "uptime": int(uptime)
                }
            ]
        }
