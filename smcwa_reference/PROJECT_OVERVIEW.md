# SMC LAMA: Project Overview & Video Script (Hinglish)

This document provides a comprehensive overview of the **SMC LAMA (Log Analytics and Monitoring Application)**. It is designed to help you create a Hinglish video explaining the project's purpose, architecture, and technical details.

---

## 📺 Video Script Structure (Hinglish)

### 1. Introduction (The Problem & Solution)
*   **Audio (Hinglish):** "Dosto, trading systems mein 'Downtime' matlab 'Bada Loss'. Har ek second ki value hoti hai. Isi problem ko solve karne ke liye humne banaya hai **SMC LAMA**. Yeh ek centralized monitoring platform hai jo NSE, BSE, MCX, aur NCDEX ke servers ko real-time track karta hai."
*   **Key Point:** Centralized observability for multi-exchange trading systems.

### 2. Architecture Overview (How it works)
*   **Audio (Hinglish):** "Iska architecture kaafi robust hai. Hum use kar rahe hain ek **3-Tier Architecture**:
    1.  **Agents (Go-lang):** Jo har server pe install hote hain aur metrics collect karte hain.
    2.  **Backend (FastAPI):** Jo high-performance data processing handle karta hai.
    3.  **Frontend (React):** Jahan humein saara data beautiful dashboards mein dikhta hai."
*   **Key Point:** Go Agents -> Python Backend -> React Frontend.

### 3. Tech Stack (The Engine)
*   **Audio (Hinglish):** "Tech stack ki baat karein toh humne industry-standard tools use kiye hain:
    *   **Backend:** FastAPI (Python) - kyunki yeh async hai aur bohot fast hai.
    *   **Frontend:** React 18 with MUI for a modern UI experience.
    *   **Databases:** Hum do DBs use kar rahe hain. Transactional data ke liye **PostgreSQL** aur high-speed logs/metrics ke liye **ClickHouse** (jo ki ek analytical column-store DB hai).
    *   **Caching:** Redis use hota hai fast lookups ke liye."

### 4. Data Sources (Hybrid Monitoring)
*   **Audio (Hinglish):** "LAMA ki sabse badi khasiyat hai iski **Hybrid Monitoring** capability. Data collect karne ke liye hum sirf Agent pe depend nahi karte. Hum teen tarah se data ingest kar sakte hain:
    1.  **Direct Agents:** Jo humare custom Go-based agents hain.
    2.  **Prometheus Integration:** Agar aapke paas already Prometheus/LGTM setup hai, toh LAMA wahan se directly metrics pull kar sakta hai without new agents.
    3.  **AWS CloudWatch:** AWS ke native resources jaise EC2, RDS, aur ELB ke liye hum seedha CloudWatch API se connect karte hain."

### 5. Agents & Metrics (What we track)
*   **Audio (Hinglish):** "Chahe source koi bhi ho, hum comprehensive metrics track karte hain:
    *   **Hardware:** CPU, Memory, Disk usage (via Agent/Prometheus).
    *   **Network:** Bandwidth, Latency (via SNMP/Agent).
    *   **Application:** Throughput, Error rates (via Logs/API).
    *   **Database:** Replication lag, Query performance."

### 6. LAMA API & Security (Version 1.2)
*   **Audio (Hinglish):** "Security hamari priority hai. LAMA API Specification v1.2 ke mutabiq, hum **AES256 Encryption** use karte hain passwords ke liye. Login ke baad ek JWT token generate hota hai jo har request ko authorize karta hai. Metrics push karne ke liye humne dedicated endpoints banaye hain jaise `/metrics/hardware` aur `/metrics/application`."

### 7. Application Flow (Step-by-Step)
*   **Audio (Hinglish):** "Flow bohot simple hai: 
    *   Sabse pehle, Agent data collect karke JSON format mein Backend ko bhejta hai. 
    *   Backend usse validate karta hai aur ClickHouse mein store karta hai. 
    *   Phir UI (React) ClickHouse se data fetch karke charts (Chart.js/Recharts) mein display karta hai. 
    *   Agar koi threshold cross hota hai, toh alerts trigger hote hain."

---

## 🛠 Technical Summary

| Component | Technology |
| :--- | :--- |
| **Frontend** | React 18, MUI v5, Chart.js, Recharts, Axios |
| **Backend** | Python 3.x, FastAPI, APScheduler, Pandas, Boto3 (AWS) |
| **Data Sources** | Go Agents, Prometheus (Pull), AWS CloudWatch (API) |
| **Database (Transactional)** | PostgreSQL 15 |
| **Database (Analytical)** | ClickHouse |
| **Caching** | Redis 7 |
| **Infrastructure** | Nginx, Docker, Docker Compose |
| **Security** | AES256 Encryption, JWT Authentication |

---

## 📊 LAMA API Specification (v1.2) Highlights

As per the official documentation, the system supports:

- **Authentication:** 
  - `POST /auth/login`: Requires `memberId`, `loginId`, and `password` (AES256 encrypted).
  - Returns a unique `token` valid for 24 hours.
- **Metrics Ingestion:**
  - `POST /metrics/application`: Tracks trade failures, throughput, and latency.
  - `POST /metrics/hardware`: Tracks CPU, Memory, Disk, and Uptime.
  - `POST /metrics/network`: Tracks Bandwidth, Latency, and Packet Loss.
  - `POST /metrics/database`: Tracks Replication status and Queue sizes.
- **Error Handling:** 
  - Standardized error codes (e.g., `601` for Success, `704` for Invalid Sequence ID).
  - Supports partial success responses for bulk metric uploads.

---

## 📂 Project Directory Structure

- `agent/`: Go source code for multi-OS agents.
- `api/backend/`: FastAPI implementation and database migrations.
- `ui/`: React frontend with dashboard components.
- `docs/`: Technical manuals, API specs, and architecture diagrams.
- `smc-lama-config/`: Nginx and Docker deployment configurations.
- `scripts/`: Maintenance and data validation utilities.
