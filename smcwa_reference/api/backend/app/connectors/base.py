from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class BaseConnector(ABC):
    """
    Abstract Base Class for Data Connectors.
    Each connector (Elasticsearch, MySQL, etc.) must implement these methods.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize connector with configuration.
        config: Dict containing host, port, username, password, etc.
        """
        self.config = config

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the data source. Return True if successful."""
        pass

    @abstractmethod
    def execute_query(self, query: str, index: Optional[str] = None) -> Any:
        """
        Execute a query against the data source.
        query: The query string (SQL or JSON)
        index: Optional index/table context (mostly for Elasticsearch)
        Returns: Raw result from the source
        """
        pass

    @abstractmethod
    def close(self):
        """Close any open connections."""
        pass
