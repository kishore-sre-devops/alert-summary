import asyncio
import os
import sys
import asyncpg
import socket
import aiohttp

async def run_db_audit():
    try:
        # Connect to Postgres
        conn = await asyncpg.connect(user='lama', password='v3Yw9hi2jUdMQufY', database='lama_prod', host='lama_postgres')
        
        print("\n[SECTION F] MySQL On-Prem")
        rows = await conn.fetch("SELECT * FROM database_config WHERE db_type='mysql'")
        print(f"MySQL configs found: {len(rows)}")
        for row in rows:
            host = row['host']
            port = int(row['port'])
            print(f"  {row['name']} ({host}:{port})")
            
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            try:
                s.connect((host, port))
                print("    ✅ PORT 3306 ACCESSIBLE")
            except Exception as e:
                print(f"    ❌ FAILED: {e}")
            finally:
                s.close()
        
        print("\n[SECTION G] Elasticsearch")
        es_rows = await conn.fetch("SELECT * FROM database_config WHERE db_type='elasticsearch'")
        print(f"ES configs found: {len(es_rows)}")
        for row in es_rows:
            host = row['host']
            port = int(row['port'])
            print(f"  {row['name']} ({host}:{port})")
            
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(f"http://{host}:{port}/_cluster/health", timeout=3) as resp:
                        if resp.status == 200:
                            health = await resp.json()
                            print(f"    ✅ STATUS: {health.get('status')}")
                        else:
                            print(f"    ❌ HTTP {resp.status}")
                except Exception as e:
                    print(f"    ❌ FAILED: {e}")
        
        await conn.close()
    except Exception as e:
        print(f"Audit Script Error: {e}")

if __name__ == '__main__':
    asyncio.run(run_db_audit())
