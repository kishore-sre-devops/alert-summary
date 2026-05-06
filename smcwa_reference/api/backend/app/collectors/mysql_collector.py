# api/backend/app/collectors/mysql_collector.py
"""
MySQL replication metrics collector for LAMA Database Scheduler.
Connects directly to MySQL instances and queries replication status.
"""
import logging
import statistics
import asyncio
from typing import Optional
import aiomysql

logger = logging.getLogger(__name__)


class MySQLCollector:
    
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,        # already decrypted before passing in
        database: str,
        is_replication: bool, # from database_config.is_replication
        master_host: str = None,
        connect_timeout: int = 30,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self.is_replication = is_replication
        self.master_host = master_host
        self.connect_timeout = connect_timeout

    async def collect(self) -> dict:
        """
        Main entry point with retry.
        Returns LAMA-compatible database metrics dict.
        """
        last_err = None
        for attempt in range(3):
            try:
                conn = await aiomysql.connect(
                    host=self.host,
                    port=self.port,
                    user=self.username,
                    password=self.password,
                    db=self.database,
                    connect_timeout=self.connect_timeout,
                )
                try:
                    if self.is_replication:
                        return await self._collect_replica_metrics(conn)
                    else:
                        return await self._collect_primary_metrics(conn)
                finally:
                    conn.close()
            except Exception as e:
                last_err = e
                if attempt < 2:
                    logger.warning(f"MySQL connect retry {attempt+1}/3 for {self.host}:{self.port} → {e}")
                    await asyncio.sleep(2)
        logger.error(f"MySQL collection failed {self.host}:{self.port} after 3 attempts → {last_err}")
        return self._zeros(status=0)

    async def _collect_replica_metrics(self, conn) -> dict:
        """
        Run on REPLICA — queries SHOW REPLICA STATUS (MySQL 8+)
        with fallback to SHOW SLAVE STATUS (MySQL 5.x)
        """
        cursor = await conn.cursor(aiomysql.DictCursor)
        
        # Try MySQL 8+ syntax first, fallback to 5.x
        try:
            await cursor.execute("SHOW REPLICA STATUS")
        except Exception:
            try:
                await cursor.execute("SHOW SLAVE STATUS")
            except Exception as e:
                logger.error(f"Cannot query replication status: {e}")
                return self._zeros(status=1)

        row = await cursor.fetchone()
        
        if not row:
            # No replication configured despite is_replication=True
            logger.warning(
                f"is_replication=True but SHOW REPLICA STATUS "
                f"returned empty on {self.host}"
            )
            return self._zeros(status=1)

        # Determine replication health
        io_running  = str(row.get("Slave_IO_Running")  or 
                         row.get("Replica_IO_Running", "No")).strip()
        sql_running = str(row.get("Slave_SQL_Running") or 
                         row.get("Replica_SQL_Running", "No")).strip()
        
        both_running = (io_running == "Yes" and sql_running == "Yes")
        status = 1 if both_running else 0

        if not both_running:
            logger.warning(
                f"Replication not healthy on {self.host}: "
                f"IO={io_running}, SQL={sql_running}"
            )

        # qSize → Seconds_Behind_Master as queue depth proxy
        seconds_behind = float(
            row.get("Seconds_Behind_Master") or
            row.get("Seconds_Behind_Source") or 0
        )

        # latency → Seconds_Behind_Master in milliseconds
        latency_ms = seconds_behind * 1000

        # bandwidth → log position diff as proxy
        # Read_Master_Log_Pos - Exec_Master_Log_Pos = bytes not yet applied
        read_pos = float(row.get("Read_Master_Log_Pos") or 
                        row.get("Read_Source_Log_Pos") or 0)
        exec_pos = float(row.get("Exec_Master_Log_Pos") or 
                        row.get("Exec_Source_Log_Pos") or 0)
        
        # Bytes behind as % of a 1GB log file (safe normalization)
        log_diff = max(0.0, read_pos - exec_pos)
        bandwidth_pct = min(100.0, round((log_diff / 1_073_741_824) * 100, 2))

        await cursor.close()

        return {
            "status": status,
            "qSize": self._single_val(round(seconds_behind, 2)),
            "bandwidth": self._single_val(bandwidth_pct),
            "latency": self._single_val(round(latency_ms, 2)),
        }

    async def _collect_primary_metrics(self, conn) -> dict:
        """
        Run on PRIMARY — just verify connectivity.
        No replication metrics available on primary.
        """
        try:
            cursor = await conn.cursor()
            await cursor.execute("SELECT 1")
            await cursor.close()
            logger.info(
                f"Primary DB {self.host} is UP — "
                f"submitting zeros for replication metrics"
            )
            return self._zeros(status=1)
        except Exception as e:
            logger.error(f"Primary DB {self.host} ping failed: {e}")
            return self._zeros(status=0)

    def _single_val(self, v: float) -> dict:
        """Single value → stats dict (all same value) with points and datasource."""
        return {
            "min": v, "max": v, "avg": v, "med": v, 
            "points": [v], 
            "datasource": "MySQL-Direct-Audit"
        }

    def _zeros(self, status: int = 1) -> dict:
        """Return all-zero metrics with given status."""
        return {
            "status": status,
            "qSize":     self._single_val(0.0),
            "bandwidth": self._single_val(0.0),
            "latency":   self._single_val(0.0),
            "datasource": "MySQL-Direct-Audit"
        }
