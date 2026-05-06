#!/usr/bin/env python3
"""
Setup Test Servers Script
Creates 2 test servers and starts 2 mock agents for local testing
"""

import requests
import time
import random
import json
import os
import sys
from datetime import datetime
from threading import Thread

# Try to detect API URL - check if accessible on localhost:8000, otherwise use Docker network IP
import socket
import subprocess

def get_api_url():
    # First try localhost:8000
    try:
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.settimeout(1)
        result = test_sock.connect_ex(('localhost', 8000))
        test_sock.close()
        if result == 0:
            return "http://localhost:8000"
    except:
        pass
    
    # If not accessible, try to get Docker network IP
    try:
        result = subprocess.run(
            ['docker', 'inspect', '-f', '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}', 'lama_api'],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0 and result.stdout.strip():
            api_ip = result.stdout.strip()
            return f"http://{api_ip}:8000"
    except:
        pass
    
    # Fallback
    return "http://localhost:8000"

API_URL = os.environ.get("API_URL", get_api_url())
if API_URL != "http://localhost:8000":
    print(f"   ℹ️  Using API at: {API_URL}")
ADMIN_EMAIL = "dineshpathak@smcindiaonline.com"
ADMIN_PASSWORD = "@Smcltd123"
ENVIRONMENT = "uat"  # Test in UAT environment

def login():
    """Login and get JWT token"""
    print("📋 Step 1: Authenticating as admin...")
    try:
        response = requests.post(
            f"{API_URL}/auth/login?environment={ENVIRONMENT}",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            token = data.get("token")
            if token:
                print("   ✅ Authenticated successfully")
                return token
            else:
                print("   ❌ No token in response")
                return None
        else:
            print(f"   ❌ Login failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"   ❌ Login error: {e}")
        return None

def create_server(token, name, ip):
    """Create a test server"""
    try:
        response = requests.post(
            f"{API_URL}/v1/servers",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": name,
                "ip": ip,
                "status": "offline",
                "environment": ENVIRONMENT
            },
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            server_id = data.get("id")
            print(f"   ✅ {name} created with ID: {server_id}")
            return server_id
        elif response.status_code == 400 and "already exists" in response.text:
            # Server already exists, try to find it
            print(f"   ⚠️  {name} already exists, finding it...")
            servers = get_servers(token)
            for server in servers:
                if server.get("ip") == ip or server.get("name") == name:
                    server_id = server.get("id")
                    print(f"   ✅ Found {name} with ID: {server_id}")
                    return server_id
            print(f"   ❌ Could not find existing {name}")
            return None
        else:
            print(f"   ❌ Failed to create {name}: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"   ❌ Error creating {name}: {e}")
        return None

def get_servers(token):
    """Get list of servers"""
    try:
        response = requests.get(
            f"{API_URL}/v1/servers?environment={ENVIRONMENT}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

def run_mock_agent(agent_num, server_id, server_name, server_ip):
    """Run a mock agent that sends metrics"""
    agent_id = f"test-agent-{agent_num}-{int(time.time())}"
    
    print(f"\n🤖 Starting Mock Agent {agent_num} for {server_name}")
    print(f"   Agent ID: {agent_id}")
    print(f"   Server ID: {server_id}")
    print(f"   Environment: {ENVIRONMENT}")
    
    # Register agent
    print("   📝 Registering agent...")
    try:
        register_response = requests.post(
            f"{API_URL}/v1/agents/{agent_id}/register",
            json={
                "hostname": server_name,
                "ip": server_ip,
                "environment": ENVIRONMENT,
                "os_type": "Linux",
                "agent_version": "1.0.0"
            },
            timeout=10
        )
        if register_response.status_code == 200:
            print(f"   ✅ Agent registered successfully")
        else:
            print(f"   ⚠️  Registration response: {register_response.status_code}")
    except Exception as e:
        print(f"   ⚠️  Registration error: {e}")
    
    # Send heartbeats
    print(f"   📊 Sending metrics every 30 seconds...")
    print(f"   Press Ctrl+C to stop all agents\n")
    
    while True:
        try:
            # Generate realistic test metrics
            cpu_avg = round(random.uniform(2.0, 8.0), 2)
            memory_avg = round(random.uniform(8.0, 15.0), 2)
            disk_avg = round(random.uniform(20.0, 40.0), 2)
            
            heartbeat_data = {
                "cpu": cpu_avg,
                "memory": memory_avg,
                "disk": disk_avg,
                "uptime": random.uniform(1000, 5000),
                "network_bandwidth": round(random.uniform(10.0, 50.0), 2),
                "network_latency": round(random.uniform(100, 500), 2),
                "packet_count": random.randint(0, 10),
                "lookup_count": random.randint(0, 5)
            }
            
            response = requests.post(
                f"{API_URL}/v1/servers/{server_id}/heartbeat",
                json=heartbeat_data,
                timeout=10
            )
            
            if response.status_code == 200:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] Agent {agent_num} ✅ - CPU: {cpu_avg:.2f}%, Memory: {memory_avg:.2f}%, Disk: {disk_avg:.2f}%")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Agent {agent_num} ❌ - {response.status_code}")
        except KeyboardInterrupt:
            print(f"\n   🛑 Agent {agent_num} stopped")
            break
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Agent {agent_num} ❌ Error: {e}")
        
        time.sleep(30)

def main():
    print("🚀 Setting up local test environment...")
    print("")
    
    # Check API health
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        if response.status_code != 200:
            print("   ⚠️  API health check failed, but continuing...")
    except:
        print("   ⚠️  Could not reach API, but continuing...")
    
    # Login
    token = login()
    if not token:
        print("\n❌ Failed to authenticate. Exiting.")
        sys.exit(1)
    
    print("")
    print("📋 Step 2: Creating test servers...")
    
    # Create Server 1
    server1_id = create_server(token, "test-server-1", "192.168.1.101")
    if not server1_id:
        print("\n❌ Failed to create Server 1. Exiting.")
        sys.exit(1)
    
    # Create Server 2
    server2_id = create_server(token, "test-server-2", "192.168.1.102")
    if not server2_id:
        print("\n❌ Failed to create Server 2. Exiting.")
        sys.exit(1)
    
    print("")
    print("✅ Test servers created successfully!")
    print("")
    print("📋 Step 3: Starting mock agents...")
    print("   (Agents will run in foreground - press Ctrl+C to stop)")
    print("")
    
    # Start agents in separate threads
    agent1_thread = Thread(target=run_mock_agent, args=(1, server1_id, "test-server-1", "192.168.1.101"), daemon=True)
    agent2_thread = Thread(target=run_mock_agent, args=(2, server2_id, "test-server-2", "192.168.1.102"), daemon=True)
    
    agent1_thread.start()
    time.sleep(2)  # Stagger the starts
    agent2_thread.start()
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping all agents...")
        print("✅ Test complete!")

if __name__ == "__main__":
    main()

