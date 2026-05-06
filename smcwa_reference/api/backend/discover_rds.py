
import asyncio
import httpx
import json

async def discover_rds():
    url = "http://10.236.26.167:9009/prometheus/api/v1/query"
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Query for all unique db_instance_identifier labels
        print("--- All db_instance_identifier values ---")
        resp = await client.get(url, params={"query": 'count by (db_instance_identifier) (up)'})
        if resp.status_code == 200:
            for r in resp.json().get("data", {}).get("result", []):
                print(r['metric'])
        
        # Query for anything with "postgres"
        print("\n--- Anything with 'postgres' ---")
        resp = await client.get(url, params={"query": '{instance=~".*postgres.*"} or {job=~".*postgres.*"} or {db_instance_identifier=~".*postgres.*"}'})
        if resp.status_code == 200:
            for r in resp.json().get("data", {}).get("result", []):
                print(r['metric'])

if __name__ == "__main__":
    asyncio.run(discover_rds())
