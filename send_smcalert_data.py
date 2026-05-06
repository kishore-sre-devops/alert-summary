import requests
import json
import os
import time
from datetime import datetime

# ------------------ CONFIGURATION ------------------
# Production API URL
API_URL = "https://smcalert.smcindiaonline.com/api/alerts"
CACHE_FILE = "alert_cache.json"

# ------------------ CACHE ------------------
def load_cache():
    """Loads the local cache to prevent sending duplicates from the client side"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Cache load error: {e}")
            return {}
    return {}

def save_cache(cache):
    """Saves the sent alerts cache to a file"""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        print(f"⚠️ Cache save error: {e}")

# ------------------ API ------------------
def send_smc_alert(payload):
    """
    Sends an alert payload to the SMC Alert dashboard.
    Includes client-side deduplication using a local cache file.
    """
    cache = load_cache()
    
    # Identify unique fields for deduplication
    alertname = payload.get("alertname")
    instance = payload.get("instance")
    received_at = payload.get("received_at") or payload.get("timestamp")
    
    if not (alertname and instance and received_at):
        print("❌ Error: Missing required fields (alertname, instance, or timestamp)")
        return False

    # Create a unique fingerprint for this specific alert instance
    fingerprint = f"{alertname}_{instance}_{received_at}"
    
    if fingerprint in cache:
        # print(f"⏭️ Skipping duplicate: {alertname} for {instance}")
        return False

    try:
        # Clean up timestamp for parsing if needed
        if isinstance(received_at, str):
            # User's suggested parsing logic to handle Prometheus 'Z' suffix
            clean_time = received_at.replace("Z", "")
            try:
                # Validate it's a valid ISO format
                datetime.fromisoformat(clean_time)
                # Ensure the payload has a standard ISO format
                payload["received_at"] = clean_time
            except:
                pass

        response = requests.post(API_URL, json=payload, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ Sent: {alertname} | {instance}")
            
            # Update and save cache
            cache[fingerprint] = time.time()
            
            # Optional: Cleanup old cache entries (older than 24 hours)
            now = time.time()
            cache = {k: v for k, v in cache.items() if now - v < 86400}
            
            save_cache(cache)
            return True
        else:
            print(f"❌ Failed to send: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"⚠️ Network Error: {e}")
        return False

# ------------------ MAIN ------------------
if __name__ == "__main__":
    print(f"🚀 Starting SMC Alert Sender (Target: {API_URL})")
    
    # Example alert payload
    example_payload = {
        "alertname": "WindowsServerDiskSpaceUsage",
        "instance": "192.168.21.45",
        "status": "firing",
        "severity": "Critical 50%",
        "timestamp": "2026-05-04T00:39:17.483891Z",
        "job": "IPO_Application_Server",
        "company": "SMC",
        "group": "Infra-Team",
        "asset": "CA",
        "description": "Disk usage is more than 50%"
    }
    
    send_smc_alert(example_payload)
