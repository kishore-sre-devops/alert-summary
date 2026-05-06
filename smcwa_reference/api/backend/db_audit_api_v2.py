import psycopg2
import socket
import requests
import json

def run_db_audit():
    try:
        # Connect to Postgres using psycopg2
        conn = psycopg2.connect(user='lama', password='v3Yw9hi2jUdMQufY', database='lama_prod', host='lama_postgres')
        cur = conn.cursor()
        
        print("\n[SECTION F] MySQL On-Prem")
        cur.execute("SELECT \"database\", host, port FROM database_config WHERE db_type='mysql'")
        rows = cur.fetchall()
        print(f"MySQL configs found: {len(rows)}")
        for db, host, port in rows:
            print(f"  {db} ({host}:{port})")
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            try:
                s.connect((host, int(port)))
                print("    ✅ PORT 3306 ACCESSIBLE")
            except Exception as e:
                print(f"    ❌ FAILED: {e}")
            finally:
                s.close()
        
        print("\n[SECTION G] Elasticsearch")
        cur.execute("SELECT \"database\", host, port FROM database_config WHERE db_type='elasticsearch'")
        rows = cur.fetchall()
        print(f"ES configs found: {len(rows)}")
        for db, host, port in rows:
            print(f"  {db} ({host}:{port})")
            try:
                resp = requests.get(f"http://{host}:{port}/_cluster/health", timeout=3)
                if resp.status_code == 200:
                    health = resp.json()
                    print(f"    ✅ STATUS: {health.get('status')}")
                else:
                    print(f"    ❌ HTTP {resp.status_code}")
            except Exception as e:
                print(f"    ❌ FAILED: {e}")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Audit Script Error: {e}")

if __name__ == '__main__':
    run_db_audit()
