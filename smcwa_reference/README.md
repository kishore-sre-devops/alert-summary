# SMC LAMA (Log Analytics and Monitoring Application)

## 📌 Project Purpose

**SMC LAMA** is a comprehensive **Log Analytics and Monitoring Application** designed to provide real-time visibility into the health and performance of member end systems across various exchanges (NSE, BSE, MCX, NCDEX).

It acts as a centralized observability platform that collects, stores, and visualizes critical metrics, enabling system administrators to detect anomalies, troubleshoot issues, and ensure seamless trading operations.

The system adheres to the **API Specification Version 1.2**, ensuring secure and standardized data exchange for:
- **Application Metrics:** Throughput, Latency, Error Rates.
- **Hardware Metrics:** CPU, Memory, Disk Usage, Uptime.
- **Network Metrics:** Bandwidth, Latency, Packet Loss.
- **Database Metrics:** Replication Status, Queue Size, Latency.

---

## 🚀 Key Features

*   **🤖 AI-Enhanced Schedulers:** Intelligent, self-healing schedulers with predictive validation and auto-correction.
*   **Multi-Exchange Support:** Unified monitoring for NSE, BSE, MCX, and NCDEX.
*   **Secure Authentication:** AES256 encrypted password transmission and JWT-based session management.
*   **Real-time Metrics Ingestion:** High-performance APIs to receive metric payloads every 5 minutes (or configurable intervals).
*   **Granular Data Validation:** Robust error handling for partial successes, duplicate records, and invalid metric keys.
*   **Interactive Dashboards:** Rich visualizations using **Chart.js** and **Recharts** for historical and real-time trend analysis.
*   **Alerting & Thresholds:** Configurable thresholds for critical metrics (e.g., CPU > 90%, Replication Lag).
*   **Report Generation:** Export dashboards and metric reports to PDF.
*   **Scalable Architecture:** Built on **ClickHouse** for high-volume time-series data and **PostgreSQL** for transactional data.

---

## 🛠️ Technical Stack

### Frontend (UI)
*   **Framework:** React 18 (Create React App)
*   **UI Library:** Material UI (MUI) v5
*   **Visualization:** Chart.js, Recharts, React-Chartjs-2
*   **State/Data:** Axios, Date-fns
*   **Reporting:** jsPDF, html2canvas

### Backend (API & Scheduler)
*   **Language:** Python 3.x
*   **Framework:** FastAPI (High-performance Async Framework)
*   **Server:** Uvicorn / Gunicorn
*   **Task Scheduling:** APScheduler
*   **Data Processing:** Pandas, NumPy

### Database & Infrastructure
*   **Analytical DB:** ClickHouse (for high-speed logs & metrics)
*   **Relational DB:** PostgreSQL 15 (for user management & config)
*   **Caching:** Redis 7
*   **Proxy/Server:** Nginx
*   **Containerization:** Docker, Docker Compose

---

## 🔄 User Workflow (Step-by-Step)

1.  **Authentication:**
    *   User launches the LAMA Portal.
    *   Enters **Member ID**, **Login ID**, and **Password**.
    *   System validates credentials (password is AES256 encrypted) and issues a **Session Token**.

2.  **Dashboard Overview:**
    *   Upon login, the user lands on the **Main Dashboard**.
    *   Views a high-level summary of connected servers, active alerts, and overall system health.

3.  **Deep-Dive Monitoring:**
    *   User navigates to specific modules:
        *   **Application:** Checks trade API failures and throughput.
        *   **Hardware:** Monitors server resources (CPU/RAM spikes).
        *   **Network:** Verifies connectivity and bandwidth usage.
        *   **Database:** Ensures replication is in sync.

4.  **Analysis & Reporting:**
    *   User selects a date range to view **Historical Data**.
    *   Identifies trends or recurring issues.
    *   Clicks "Export PDF" to generate a report for management.

5.  **Logout:**
    *   User securely logs out, invalidating the session token.

---

## 🎬 Hinglish Demo Video Storyboard

This storyboard is designed for a developer or product manager creating a demo video for an Indian audience (Hinglish).

### **Scene 1: Introduction (The "Why")**
*   **Visual:** Show the LAMA Logo and the login screen.
*   **Audio (Hinglish):** "Hello everyone! Aaj hum baat karenge **SMC LAMA** ke baare mein. Yeh ek powerful monitoring tool hai jo hamare trading systems ki health ko track karta hai. Chahe wo CPU usage ho ya Application latency, LAMA sab kuch real-time mein dikhata hai."

### **Scene 2: Secure Login (Security First)**
*   **Visual:** Show the login page. Type Member ID and Password. Highlight the "Encrypted" badge/text if available, or mention it.
*   **Audio (Hinglish):** "Sabse pehle, security. Jab hum login karte hain, toh password plain text mein nahi, balki **AES256 encryption** ke saath secure hoke server pe jaata hai. Jisse hamara data hamesha safe rehta hai."

### **Scene 3: The Dashboard (Bird's Eye View)**
*   **Visual:** Land on the main dashboard. Hover over the gauges/charts.
*   **Audio (Hinglish):** "Login karte hi humein milta hai yeh **Dashboard**. Yahan aap ek nazar mein dekh sakte hain ki NSE, BSE ya MCX ke servers up hain ya down. Agar koi critical alert hai, toh wo yahan turant highlight ho jayega."

### **Scene 4: Monitoring Metrics (The Core)**
*   **Visual:** Click on "Hardware Metrics". Show the CPU and Memory graphs updating.
*   **Audio (Hinglish):** "Chaliye details mein dekhte hain. Yeh hai **Hardware Monitoring**. Agar kisi server ka CPU 90% cross karta hai, toh graph red ho jayega. Same way, hum **Network** aur **Database replication** ko bhi track kar sakte hain taaki trading mein koi rukawat na aaye."

### **Scene 5: Reporting & Export (Sharing Data)**
*   **Visual:** Click on a "Download Report" or "Export PDF" button. Show the downloaded PDF.
*   **Audio (Hinglish):** "Analysis ke baad, agar aapko management ko report bhejni hai, toh bas ek click karein aur **PDF report** generate ho jayegi with all the charts and data."

### **Scene 6: Conclusion**
*   **Visual:** Back to the main logo or a "Thank You" slide.
*   **Audio (Hinglish):** "Toh yeh tha SMC LAMA – Simple, Secure aur Scalable monitoring. For more technical details, please refer to the `README.md`. Thank you!"

---

## 📂 Directory Structure Overview

```bash
/opt/smclama/
├── agent/                  # Go-based agent for metric collection
├── api/                    # Python FastAPI backend
│   └── backend/            # Main application logic & migrations
├── docs/                   # API Specifications & Architecture guides
├── smc-lama-config/        # Docker setup & Nginx configurations
├── ui/                     # React Frontend application
└── scripts/                # Utility scripts for maintenance
```
