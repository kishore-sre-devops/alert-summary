"""
BaseCollector: Abstract class for all data sources in SMC LAMA V2.0
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime

class BaseCollector(ABC):
    """Base class for Prometheus, AWS, ES, and DB collectors"""
    
    @abstractmethod
    def collect(self, resource_id: str, window_minutes: int = 5) -> Dict[str, Any]:
        """
        Collect raw metrics for a specific resource (Server ID, ARN, etc.)
        Must return raw data for Aggregator to process.
        """
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """Verify the data source (e.g., Prometheus URL, AWS Creds) is active"""
        pass

class MetricResponse:
    """Standardized response from collectors before aggregation"""
    def __init__(self, 
                 source: str, 
                 resource_id: str, 
                 timestamp: datetime, 
                 data: Dict[str, Any],
                 status: str = "success",
                 error: Optional[str] = None):
        self.source = source
        self.resource_id = resource_id
        self.timestamp = timestamp
        self.data = data
        self.status = status
        self.error = error
