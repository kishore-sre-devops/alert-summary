import logging
import urllib.parse
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from typing import Any, List, Dict
from app.connectors.base import BaseConnector
from app.utils.aes_encryption import decrypt_password

logger = logging.getLogger(__name__)

class SQLConnector(BaseConnector):
    def __init__(self, source_type: str, config: Dict[str, Any]):
        super().__init__(config)
        self.source_type = source_type
        self.engine: Engine = None
        self.connected = False
        
    def _build_connection_url(self) -> str:
        host = self.config.get("host")
        port = self.config.get("port")
        username = self.config.get("username")
        encrypted_password = self.config.get("password")
        database = self.config.get("database_name")
        
        password = decrypt_password(encrypted_password) if encrypted_password else ""
        encoded_password = urllib.parse.quote_plus(password)
        
        if self.source_type == "postgresql":
            # Default port 5432
            if not port: port = 5432
            return f"postgresql://{username}:{encoded_password}@{host}:{port}/{database}"
            
        elif self.source_type == "mysql":
            # Default port 3306
            if not port: port = 3306
            # Use pymysql driver
            return f"mysql+pymysql://{username}:{encoded_password}@{host}:{port}/{database}"
            
        elif self.source_type == "mssql":
            # Default port 1433
            if not port: port = 1433
            # Use pyodbc driver with SQL Server driver
            # Note: This requires the ODBC driver to be installed in the container
            return f"mssql+pyodbc://{username}:{encoded_password}@{host}:{port}/{database}?driver=ODBC+Driver+17+for+SQL+Server"
            
        else:
            raise ValueError(f"Unsupported SQL source type: {self.source_type}")

    def connect(self) -> bool:
        try:
            url = self._build_connection_url()
            self.engine = create_engine(url)
            
            # Test connection
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to {self.source_type}: {e}")
            self.connected = False
            return False

    def execute_query(self, query: str, index: str = None) -> List[Dict[str, Any]]:
        """
        Execute raw SQL query.
        Returns a list of dictionaries (rows).
        """
        if not self.connected or not self.engine:
            if not self.connect():
                raise ConnectionError(f"Could not connect to {self.source_type}")
                
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                # Convert Result object to list of dicts
                rows = [dict(row._mapping) for row in result]
                return rows

        except Exception as e:
            logger.error(f"Error executing SQL query: {e}")
            raise

    def close(self):
        if self.engine:
            self.engine.dispose()
