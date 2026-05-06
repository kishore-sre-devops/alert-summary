from typing import Dict, Any
from app.connectors.base import BaseConnector
from app.connectors.elasticsearch import ElasticsearchConnector
from app.connectors.sql import SQLConnector
from app.connectors.cloudwatch import CloudWatchConnector
from app.connectors.prometheus import PrometheusConnector

class ConnectorFactory:
    @staticmethod
    def get_connector(source_type: str, config: Dict[str, Any]) -> BaseConnector:
        source_type = source_type.lower()
        if source_type == 'elasticsearch':
            return ElasticsearchConnector(config)
        elif source_type in ['mysql', 'postgresql', 'mssql']:
            return SQLConnector(source_type, config)
        elif source_type in ['cloudwatch', 'aws', 'ecs']:
            return CloudWatchConnector(config)
        elif source_type == 'prometheus':
            return PrometheusConnector(config)
        else:
            raise ValueError(f"Unsupported source type: {source_type}")
