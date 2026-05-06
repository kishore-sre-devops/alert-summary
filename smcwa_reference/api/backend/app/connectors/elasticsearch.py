import logging
import json
from datetime import datetime
from typing import Any, Dict
from elasticsearch import Elasticsearch
from app.connectors.base import BaseConnector
from app.utils.aes_encryption import decrypt_password

logger = logging.getLogger(__name__)

class ElasticsearchConnector(BaseConnector):
    def __init__(self, config):
        super().__init__(config)
        self.client = None
        self.connected = False
        
    def connect(self) -> bool:
        try:
            host = self.config.get("host")
            port = self.config.get("port", 9200)
            username = self.config.get("username")
            encrypted_password = self.config.get("password")
            
            password = decrypt_password(encrypted_password) if encrypted_password else None
            
            if not host:
                logger.error("Elasticsearch host not provided in config")
                return False
                
            # Handle http/https prefix
            if not host.startswith("http"):
                host = f"http://{host}"
                
            # Build connection args
            conn_args = {
                "hosts": [f"{host}:{port}"],
                "verify_certs": False,
                "ssl_show_warn": False
            }
            
            if username and password:
                conn_args["basic_auth"] = (username, password)
                
            self.client = Elasticsearch(**conn_args)
            
            # Test connection
            info = self.client.info()
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Elasticsearch: {e}")
            self.connected = False
            return False

    def execute_query(self, query: str, index: str = None) -> Any:
        if not self.connected or not self.client:
            if not self.connect():
                raise ConnectionError("Could not connect to Elasticsearch")
                
        try:
            # Parse query string into dictionary
            if isinstance(query, str):
                try:
                    query_body = json.loads(query)
                except json.JSONDecodeError:
                    # If not JSON, treat as a 'query_string' query
                    query_body = {
                        "query": {
                            "query_string": {
                                "query": query
                            }
                        }
                    }
            else:
                query_body = query

            if not index:
                index = "lama-*" # Default fallback

            # Execute search with size=1 and descending sort on @timestamp to get most recent
            response = self.client.search(
                index=index, 
                body=query_body, 
                size=1, 
                sort=[{"@timestamp": {"order": "desc"}}],
                ignore_unavailable=True
            )
            return response

        except Exception as e:
            logger.error(f"Error executing Elasticsearch query: {e}")
            raise

    def close(self):
        if self.client:
            try:
                self.client.close()
            except:
                pass
