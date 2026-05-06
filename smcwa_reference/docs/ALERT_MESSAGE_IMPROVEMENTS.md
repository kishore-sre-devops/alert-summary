# Alert Message Improvements - Analysis & Implementation

## Current Issues

### 1. **Severity Label: "ERROR" instead of "CRITICAL"**
**Current:** `[UAT] [ERROR] Alert: hardware.disk on WIN-TJA196FJV8M`
**Should be:** `[UAT] [CRITICAL] Alert: hardware.disk on WIN-TJA196FJV8M`

**Root Cause:** Subject line uses `severity.upper()` which shows "ERROR" instead of mapping to "CRITICAL"

### 2. **Missing IP Address in Subject**
**Current:** `Alert: hardware.disk on WIN-TJA196FJV8M`
**Should be:** `Alert: hardware.disk on WIN-TJA196FJV8M (192.168.1.134)`

**Root Cause:** Subject line only includes `server_name`, not `server_ip`

### 3. **Unprofessional Timestamp Format**
**Current:** 
- Email: `Timestamp: 2025-12-16T15:40:52.508738`
- Slack: `2025-12-16T15:44:32.845517`

**Issues:**
- ISO 8601 format with microseconds looks technical/raw
- No timezone indicator (UTC not explicit)
- Not user-friendly for quick reading

**Should be:**
- Email: `Timestamp: 16 Dec 2025, 03:40:52 PM UTC` or `2025-12-16 15:40:52 UTC`
- Slack: `16 Dec 2025, 03:40 PM UTC` (more compact for mobile)

---

## Implementation Plan

### File to Modify: `/opt/smc-lama/api/backend/app/utils/alert_sender.py`

### Changes Required:

#### 1. Add Timestamp Formatting Function
```python
def format_timestamp_professional(dt: datetime) -> str:
    """
    Format datetime in professional, user-friendly format
    Example: "16 Dec 2025, 03:40:52 PM UTC"
    """
    return dt.strftime("%d %b %Y, %I:%M:%S %p UTC")

def format_timestamp_compact(dt: datetime) -> str:
    """
    Format datetime in compact format for Slack
    Example: "16 Dec 2025, 03:40 PM UTC"
    """
    return dt.strftime("%d %b %Y, %I:%M %p UTC")
```

#### 2. Add Severity Label Mapping Function
```python
def get_severity_label(severity: str) -> str:
    """
    Map internal severity to user-facing labels
    - error -> CRITICAL
    - warning -> WARNING
    - info -> INFO
    """
    severity_map = {
        'error': 'CRITICAL',
        'critical': 'CRITICAL',
        'warning': 'WARNING',
        'info': 'INFO',
        'high': 'CRITICAL',
        'medium': 'WARNING',
        'low': 'INFO'
    }
    return severity_map.get(severity.lower(), severity.upper())
```

#### 3. Update Email Alert Function (`send_email_alert`)

**Current (line 79-89):**
```python
msg['Subject'] = f"{env_prefix}[{severity.upper()}] Alert: {metric_type}.{metric_key} on {server_name}"

body = f"""
Alert Details:
- Environment: {environment.upper() if environment else 'PROD'}
- Server: {server_name} ({server_ip})
- Metric: {metric_type}.{metric_key}
- Current Value: {value:.2f}
- Severity: {severity.upper()}
- Message: {message}
- Alert ID: {alert_id}
- Timestamp: {datetime.utcnow().isoformat()}
```

**Should be:**
```python
severity_label = get_severity_label(severity)
msg['Subject'] = f"{env_prefix}[{severity_label}] Alert: {metric_type}.{metric_key} on {server_name} ({server_ip})"

timestamp = format_timestamp_professional(datetime.utcnow())

body = f"""
Alert Details:
- Environment: {environment.upper() if environment else 'PROD'}
- Server: {server_name}
- IP Address: {server_ip}
- Metric: {metric_type}.{metric_key}
- Current Value: {value:.2f}
- Severity: {severity_label}
- Message: {message}
- Alert ID: {alert_id}
- Timestamp: {timestamp}
```

#### 4. Update Slack Alert Function (`send_slack_alert`)

**Current (line 133-147):**
```python
payload = {
    "text": f"{env_prefix}Alert: {metric_type}.{metric_key} on {server_name}",
    "attachments": [
        {
            "color": color,
            "fields": [
                {"title": "Environment", "value": environment.upper() if environment else "PROD", "short": True},
                {"title": "Server", "value": f"{server_name} ({server_ip})", "short": True},
                {"title": "Metric", "value": f"{metric_type}.{metric_key}", "short": True},
                {"title": "Value", "value": f"{value:.2f}", "short": True},
                {"title": "Severity", "value": severity.upper(), "short": True},
                {"title": "Message", "value": message, "short": False},
                {"title": "Alert ID", "value": str(alert_id), "short": True},
                {"title": "Timestamp", "value": datetime.utcnow().isoformat(), "short": True}
```

**Should be:**
```python
severity_label = get_severity_label(severity)
timestamp = format_timestamp_compact(datetime.utcnow())

payload = {
    "text": f"{env_prefix}[{severity_label}] Alert: {metric_type}.{metric_key} on {server_name} ({server_ip})",
    "attachments": [
        {
            "color": color,
            "fields": [
                {"title": "Environment", "value": environment.upper() if environment else "PROD", "short": True},
                {"title": "Server", "value": server_name, "short": True},
                {"title": "IP Address", "value": server_ip, "short": True},
                {"title": "Metric", "value": f"{metric_type}.{metric_key}", "short": True},
                {"title": "Value", "value": f"{value:.2f}", "short": True},
                {"title": "Severity", "value": severity_label, "short": True},
                {"title": "Message", "value": message, "short": False},
                {"title": "Alert ID", "value": str(alert_id), "short": True},
                {"title": "Timestamp", "value": timestamp, "short": True}
```

#### 5. Update SMS/Mobile Alert Function (`send_mobile_alert`)

**Current (line 193):**
```python
sms_message = f"{env_prefix}[{severity.upper()}] {metric_type}.{metric_key} on {server_name}: {value:.2f} - {message}"
```

**Should be:**
```python
severity_label = get_severity_label(severity)
sms_message = f"{env_prefix}[{severity_label}] {metric_type}.{metric_key} on {server_name} ({server_ip}): {value:.2f} - {message}"
```

---

## Before vs After Comparison

### Email Alert

**BEFORE:**
```
Subject: [UAT] [ERROR] Alert: hardware.disk on WIN-TJA196FJV8M

Alert Details:
- Environment: UAT
- Server: WIN-TJA196FJV8M (192.168.1.134)
- Metric: hardware.disk
- Current Value: 95.50
- Severity: ERROR
- Message: Disk usage exceeded error threshold
- Alert ID: 123
- Timestamp: 2025-12-16T15:40:52.508738
```

**AFTER:**
```
Subject: [UAT] [CRITICAL] Alert: hardware.disk on WIN-TJA196FJV8M (192.168.1.134)

Alert Details:
- Environment: UAT
- Server: WIN-TJA196FJV8M
- IP Address: 192.168.1.134
- Metric: hardware.disk
- Current Value: 95.50
- Severity: CRITICAL
- Message: Disk usage exceeded error threshold
- Alert ID: 123
- Timestamp: 16 Dec 2025, 03:40:52 PM UTC
```

### Slack Alert

**BEFORE:**
```
[UAT] Alert: hardware.disk on WIN-TJA196FJV8M

Fields:
Environment: UAT
Server: WIN-TJA196FJV8M (192.168.1.134)
Metric: hardware.disk
Value: 95.50
Severity: ERROR
Message: Disk usage exceeded error threshold
Alert ID: 123
Timestamp: 2025-12-16T15:44:32.845517
```

**AFTER:**
```
[UAT] [CRITICAL] Alert: hardware.disk on WIN-TJA196FJV8M (192.168.1.134)

Fields:
Environment: UAT
Server: WIN-TJA196FJV8M
IP Address: 192.168.1.134
Metric: hardware.disk
Value: 95.50
Severity: CRITICAL
Message: Disk usage exceeded error threshold
Alert ID: 123
Timestamp: 16 Dec 2025, 03:44 PM UTC
```

### SMS Alert

**BEFORE:**
```
[UAT] [ERROR] hardware.disk on WIN-TJA196FJV8M: 95.50 - Disk usage exceeded error threshold
```

**AFTER:**
```
[UAT] [CRITICAL] hardware.disk on WIN-TJA196FJV8M (192.168.1.134): 95.50 - Disk usage exceeded error threshold
```

---

## Timestamp Format Options

You can choose from these professional formats:

1. **Recommended (Default):** `16 Dec 2025, 03:40:52 PM UTC`
   - Most user-friendly
   - Clear AM/PM indicator
   - Explicit UTC timezone

2. **Alternative 1:** `2025-12-16 15:40:52 UTC`
   - ISO-like but with timezone
   - 24-hour format
   - Professional and clear

3. **Alternative 2:** `Dec 16, 2025 at 3:40:52 PM UTC`
   - Natural language style
   - Very readable
   - Good for non-technical users

4. **Alternative 3 (IST):** `16 Dec 2025, 09:10:52 PM IST`
   - Convert to Indian Standard Time
   - Better for India-based teams
   - Shows local time instead of UTC

### To Use IST Instead of UTC:

```python
from pytz import timezone as pytz_timezone

def format_timestamp_ist(dt: datetime) -> str:
    """
    Format datetime in IST (Indian Standard Time)
    Example: "16 Dec 2025, 09:10:52 PM IST"
    """
    ist = pytz_timezone('Asia/Kolkata')
    dt_ist = dt.replace(tzinfo=pytz_timezone('UTC')).astimezone(ist)
    return dt_ist.strftime("%d %b %Y, %I:%M:%S %p IST")
```

---

## Additional Improvements (Optional)

### 1. Add Emoji Indicators for Severity
```python
def get_severity_emoji(severity: str) -> str:
    """Add emoji for visual quick identification"""
    emoji_map = {
        'error': '🔴',
        'critical': '🔴',
        'warning': '⚠️',
        'info': 'ℹ️'
    }
    return emoji_map.get(severity.lower(), '⚠️')

# In subject line:
emoji = get_severity_emoji(severity)
msg['Subject'] = f"{emoji} {env_prefix}[{severity_label}] Alert: ..."
```

**Result:** 
```
🔴 [UAT] [CRITICAL] Alert: hardware.disk on WIN-TJA196FJV8M (192.168.1.134)
```

### 2. Add Alert Duration (for recurring alerts)
```python
# In email body, add:
- Alert Duration: 5 minutes (first triggered at 15:35:52)
```

### 3. Add Quick Action Links (for web dashboard)
```python
# In email body:
- View Details: https://smclama.smcindiaonline.com/alerts?id=123
- Acknowledge Alert: https://smclama.smcindiaonline.com/alerts/acknowledge?id=123
```

---

## Testing Checklist

After implementing changes, test:

- [ ] Email alert with ERROR severity shows "CRITICAL"
- [ ] Email subject includes both hostname and IP
- [ ] Email timestamp is human-readable (not ISO format)
- [ ] Slack alert title includes severity label
- [ ] Slack alert shows separate fields for Server and IP Address
- [ ] Slack timestamp is compact and readable
- [ ] SMS includes IP address
- [ ] All three channels (Email, Slack, SMS) consistent

---

## Deployment Notes

1. **No database changes required** - all changes in Python code only
2. **No container restart needed** - backend auto-reloads on file change (in dev mode)
3. **For production:** Restart API container after changes
   ```bash
   docker-compose restart api
   ```

4. **Test in UAT first** before deploying to PROD

---

## Summary

**Changes to make in `/opt/smc-lama/api/backend/app/utils/alert_sender.py`:**

1. ✅ Add `get_severity_label()` function to map "error" → "CRITICAL"
2. ✅ Add `format_timestamp_professional()` for email (with seconds)
3. ✅ Add `format_timestamp_compact()` for Slack (without seconds)
4. ✅ Update `send_email_alert()`:
   - Change subject to include IP: `on {server_name} ({server_ip})`
   - Use severity label instead of raw severity
   - Format timestamp professionally
   - Split Server and IP Address into separate lines

5. ✅ Update `send_slack_alert()`:
   - Change text to include IP and severity label
   - Split Server and IP Address fields
   - Use severity label
   - Format timestamp compactly

6. ✅ Update `send_mobile_alert()`:
   - Include IP in message
   - Use severity label

**Result:** Professional, consistent, and user-friendly alerts across all channels.
