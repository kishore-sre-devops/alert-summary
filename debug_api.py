import requests
import json

BASE_URL = "http://localhost:8010"

def test_api():
    print("Testing /api/metrics...")
    try:
        r = requests.get(f"{BASE_URL}/api/metrics")
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Firing: {data.get('firing')}")
        print(f"Resolved: {data.get('resolved')}")
        print(f"Recent Alerts Count: {len(data.get('recent_alerts', []))}")
        
        if data.get('recent_alerts'):
            first = data['recent_alerts'][0]
            print("Fields in sample alert:")
            for k, v in first.items():
                print(f"  {k}: {v}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_api()
