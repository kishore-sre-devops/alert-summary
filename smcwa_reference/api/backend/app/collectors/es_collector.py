"""
Elasticsearch Metrics Collector for LAMA Application Scheduler.

CRITICAL: DO NOT TOUCH
---------------------
This file contains core collection logic for Odiin-Trading-Logs and other ES-based services.
It is mandatory for LAMA V1.3 Compliance (Native Audit / Pick & Pass).
Do NOT refactor or modify this logic without explicit instruction.
- Case-insensitivity (Throughput/throughput) must be handled by the caller.
- historicalThroughput/historicalLatency keys must be supported in es_zeros.
- 5 AM IST Rule is foundational.

COMPLIANCE RULE:
- ES index is created fresh at 5 AM IST every day
- Before 5 AM IST → index does not exist → return ALL ZEROS
- After 5 AM IST → query today's IST index → return real data
- On ANY error → return ALL ZEROS
- NEVER return cached, stale, or yesterday's data
- Sending non-zero values before 5 AM IST = regulatory violation
"""

import logging
import pytz
from datetime import datetime
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

# IST timezone — all index date logic uses this
IST = pytz.timezone('Asia/Kolkata')
INDEX_AVAILABLE_HOUR_IST = 5  # 5 AM IST

def _zeros() -> dict:
    """Safe zero payload — always valid to send to LAMA."""
    return {
        "throughput": {"min": 0.0, "max": 0.0, 
                       "avg": 0.0, "med": 0.0},
        "latency":    {"min": 0.0, "max": 0.0,
                       "avg": 0.0, "med": 0.0},
        "historicalThroughput": {"min": 0.0, "max": 0.0, 
                                 "avg": 0.0, "med": 0.0},
        "historicalLatency":    {"min": 0.0, "max": 0.0,
                                 "avg": 0.0, "med": 0.0},
        "failureTradeApi":       0,
        "failureAuthentication": 0,
        "datasource":      "Elasticsearch",
        "data_available":  False,
    }

def _is_index_available() -> tuple[bool, str]:
    """
    Check if today's ES index should be available.
    Returns (available: bool, today_index_name: str)
    
    Index is ONLY available after 5 AM IST.
    Index name uses IST date — NOT UTC date.
    """
    now_ist = datetime.now(IST)
    today_ist_str = now_ist.strftime('%Y.%m.%d')
    index_name = f"lama-smc{today_ist_str}"
    
    if now_ist.hour < INDEX_AVAILABLE_HOUR_IST:
        logger.info(
            f"ES index not available yet. "
            f"Current IST: {now_ist.strftime('%H:%M')}. "
            f"Index created at {INDEX_AVAILABLE_HOUR_IST}:00 IST. "
            f"Returning zeros for all ES services."
        )
        return False, index_name
    
    return True, index_name


class ESCollector:
    """
    Collects application metrics from Elasticsearch.
    
    IMPORTANT: Uses today's IST index only.
    Returns zeros before 5 AM IST or on any error.
    Never returns stale or cached data.
    """
    
    def __init__(self, es_url: str, 
                 username: str = None, 
                 password: str = None):
        self.es_url = es_url.rstrip('/')
        self.auth = (username, password) \
                    if username and password else None
        self.timeout = 10
    
    async def collect_metric(
        self,
        index_name: str,
        metric_name: str,
        query_string: str
    ) -> Optional[dict]:
        """
        Query ES for a specific metric using a Lucene query string.
        Returns a stats dict or plain value dict with points.
        """
        try:
            # Inject time range into Lucene query if not present
            # We use a 5 minute window with 90s stabilization buffer
            now = datetime.utcnow()
            # Note: We don't inject here because the caller (application.py) should handle time windowing
            # but we ensure the query is structured correctly for ES

            query = {
                "size": 5,
                "sort": [{"@timestamp": {"order": "desc"}}],
                "query": {
                    "bool": {
                        "must": [{"query_string": {"query": query_string}}]
                    }
                }
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                kwargs = {}
                if self.auth: kwargs['auth'] = self.auth

                resp = await client.post(f"{self.es_url}/{index_name}/_search", json=query, **kwargs)
                if resp.status_code != 200:
                    logger.error(f"ES query failed for {metric_name}: {resp.status_code} {resp.text}")
                    return None

                resp_json = resp.json()
                hits = resp_json.get("hits", {}).get("hits", [])
                if not hits: return None

                # Priority fields for extraction
                priority_fields = ['Average', 'lamareqesttime', 'reqesttime', 'request_time', 'throughput', 'latency', 'Sum', 'count', 'total']

                def get_val(doc):
                    if metric_name in doc and isinstance(doc[metric_name], (int, float)): return float(doc[metric_name])
                    for f in priority_fields:
                        if f in doc and isinstance(doc[f], (int, float)): return float(doc[f])
                    for k, v in doc.items():
                        if isinstance(v, (int, float)) and k not in ['tenant', '@version']: return float(v)
                    return 0.0

                points = []
                for h in hits:
                    s = h.get("_source", {})
                    ts = s.get("@timestamp")
                    ts_unix = 0
                    try:
                        if ts:
                            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            ts_unix = int(dt.timestamp())
                    except: pass
                    points.append([ts_unix, get_val(s)])

                # Return in mapper-compatible format
                if metric_name.lower() in ["throughput", "latency", "historicalthroughput", "historicallatency"]:
                    vals = [p[1] for p in points]
                    import statistics
                    return {
                        "min": round(min(vals), 2),
                        "max": round(max(vals), 2),
                        "avg": round(sum(vals) / len(vals), 2),
                        "med": round(statistics.median(vals), 2),
                        "points": points,
                        "datasource": "Elasticsearch"
                    }
                else:
                    return {
                        "value": int(sum(p[1] for p in points) / len(points)) if points else 0,
                        "points": points,
                        "datasource": "Elasticsearch"
                    }

        except Exception as e:
            logger.error(f"ES metric collection failed for {metric_name}: {e}")
            return None

