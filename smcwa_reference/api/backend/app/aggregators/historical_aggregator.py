"""
HistoricalAggregator: SMC LAMA V2.0 Implementation
Calculates 21-day historical throughput and latency for SOD submission
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
from sqlalchemy import text
from app.db.db import engine

logger = logging.getLogger(__name__)

class HistoricalAggregator:
    @staticmethod
    def get_21_day_metrics(server_id: int, is_generic: bool = False) -> Dict[str, Any]:
        """
        Query the last 21 days of metrics from ClickHouse (preferred) or Postgres.
        Returns aggregated historicalThroughput and historicalLatency objects with min, max, avg, med.
        """
        try:
            # Determine correct column name based on source type
            # Standard apps use 'app_throughput'/'app_latency' in server_metrics
            # Generic sources use 'throughput'/'latency'
            t_metric = "app_throughput" if not is_generic else "throughput"
            l_metric = "app_latency" if not is_generic else "latency"

            with engine.connect() as conn:
                # Query historical stats for the last 21 days
                # We use ClickHouse if possible for speed, but falling back to server_metrics for now
                query = text(f"""
                    SELECT 
                        MIN(CASE WHEN metric_name = :t_metric THEN value END) as t_min,
                        MAX(CASE WHEN metric_name = :t_metric THEN value END) as t_max,
                        AVG(CASE WHEN metric_name = :t_metric THEN value END) as t_avg,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CASE WHEN metric_name = :t_metric THEN value END) as t_med,
                        MIN(CASE WHEN metric_name = :l_metric THEN value END) as l_min,
                        MAX(CASE WHEN metric_name = :l_metric THEN value END) as l_max,
                        AVG(CASE WHEN metric_name = :l_metric THEN value END) as l_avg,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CASE WHEN metric_name = :l_metric THEN value END) as l_med
                    FROM server_metrics
                    WHERE server_id = :server_id 
                    AND ts > NOW() - INTERVAL '21 days'
                """)
                result = conn.execute(query, {
                    "server_id": server_id,
                    "t_metric": t_metric,
                    "l_metric": l_metric
                }).fetchone()
                
                if not result or result[2] is None: # check t_avg
                    return None

                return {
                    "historicalThroughput": {
                        "min": round(result[0] or 0, 2),
                        "max": round(result[1] or 0, 2),
                        "avg": round(result[2] or 0, 2),
                        "med": round(result[3] or 0, 2)
                    },
                    "historicalLatency": {
                        "min": round(result[4] or 0, 2),
                        "max": round(result[5] or 0, 2),
                        "avg": round(result[6] or 0, 2),
                        "med": round(result[7] or 0, 2)
                    }
                }
        except Exception as e:
            logger.error(f"Failed to aggregate 21-day history for server {server_id}: {e}")
            return None

    @staticmethod
    def build_historical_payload(server_id: str, historical_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Formats the application metrics payload with historical data"""
        return {
            "serverId": server_id,
            "historicalThroughput": historical_metrics.get("historicalThroughput", 0),
            "historicalLatency": historical_metrics.get("historicalLatency", 0)
        }
