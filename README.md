# SMC Alert Summary Dashboard

A simple dashboard to monitor "firing" and "resolved" alerts.

## Prerequisites
- Python 3.7+
- MySQL Server
## Running with Docker (Recommended)
The easiest way to run the entire stack (Database, Backend, and Frontend) is using Docker Compose.

1. **Build and start the containers:**
   ```bash
   docker-compose up --build -d
   ```

2. **Access the Dashboard:**
   Open `http://localhost:8001` in your browser.

3. **API Access:**
   The backend API is accessible at `http://localhost:8001/api` (via the frontend proxy).

## Manual Setup (Non-Docker)
1. **Clone/Navigate to the directory:**
...
   ```bash
   cd /opt/alert-summary
   ```

2. **Install dependencies:**
   ```bash
   pip install -r backend/requirements.txt
   ```

3. **Database Configuration:**
   Copy `.env.example` to `.env` and fill in your MySQL credentials:
   ```bash
   cp .env.example .env
   ```
   Ensure the `alert_summary` database exists in MySQL.

4. **Run the Backend:**
   ```bash
   python3 -m backend.main
   ```
   The API will start on `http://localhost:8000`.

5. **Open the Dashboard:**
   Open `frontend/index.html` in your web browser.

## Sending Alerts
You can send alerts from any server using a POST request to `http://<your-ip>:8000/api/alerts`.

Example JSON payload:
```json
{
    "alert_name": "High CPU",
    "status": "firing",
    "severity": "critical",
    "source": "server-01"
}
```

Use the provided `test_send_alerts.py` to test the dashboard:
```bash
python3 test_send_alerts.py
```
