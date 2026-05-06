"""
MetricAggregator: SMC LAMA V2.0 Implementation
Calculates Min/Max/Avg/Med per 5-min window
"""
import statistics
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class MetricAggregator:
    @staticmethod
    def aggregate(raw_data: Dict[str, List[float]]) -> Dict[str, Any]:
        """
        Processes raw metric lists into LAMA-required statistics.
        Example Input: {"cpu": [10.5, 12.0, 11.5]}
        Example Output: {"cpu": {"min": 10.5, "max": 12.0, "avg": 11.3, "med": 11.5}}
        """
        aggregated = {}
        
        for metric_key, values in raw_data.items():
            if not values:
                aggregated[metric_key] = {"min": 0, "max": 0, "avg": 0, "med": 0}
                continue
                
            try:
                aggregated[metric_key] = {
                    "min": round(min(values), 2),
                    "max": round(max(values), 2),
                    "avg": round(statistics.mean(values), 2),
                    "med": round(statistics.median(values), 2)
                }
            except Exception as e:
                logger.error(f"Aggregation failed for {metric_key}: {e}")
                aggregated[metric_key] = {"min": 0, "max": 0, "avg": 0, "med": 0}
                
        return aggregated

    @staticmethod
    def format_for_lama(aggregated_data: Dict[str, Any], metric_type: str) -> Dict[str, Any]:
        """
        Final formatting for LAMA payload (e.g. converting bytes to %, etc. if needed)
        """
        # For now, most metrics are already in the target format (percentage or raw values)
        return aggregated_data
