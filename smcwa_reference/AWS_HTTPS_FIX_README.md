# Issue: smclama.smcindiaonline.com Not Opening

## Diagnosis
- **Server Status:** Healthy.
- **Nginx:** Running and configured correctly for SSL/HTTPS locally.
- **DNS:** Correctly points to the AWS Application Load Balancer (ALB).
- **Root Cause:** The AWS ALB is receiving the HTTPS request but does not have the SSL certificate attached. It fails to handshake with the browser before it can even talk to your server.

## Solution Steps (AWS Console)

### 1. Get the Certificate Data
You need to copy the text content of your certificates to your local machine (clipboard).

**Certificate Body:**
Run this and copy the output:
```bash
cat /opt/smclama/smc-lama-config/certificates/fullchain.crt
```

**Private Key:**
Run this and copy the output:
```bash
cat /opt/smclama/smc-lama-config/certificates/wildcard_smcindiaonline_com.key
```

### 2. Import to AWS ACM
1. Log in to the AWS Console (`ap-south-1` region).
2. Go to **Certificate Manager (ACM)**.
3. Click **Import a certificate**.
4. **Certificate body:** Paste the content of `fullchain.crt`.
5. **Certificate private key:** Paste the content of the `.key` file.
6. Click **Import**.

### 3. Update the Load Balancer
1. Go to **EC2** -> **Load Balancers**.
2. Select your ALB (e.g., `smclama`).
3. Click the **Listeners** tab.
4. Locate the **HTTPS : 443** listener and click **Manage/Edit**.
   - *If it doesn't exist, Create it.*
5. Under **Default SSL certificate**, choose the certificate you just imported (Imported-...).
6. Ensure the **Forward to** action points to your target group on **Port 80** (HTTP).
   - *Note: Since the ALB handles the SSL, it talks to your server over HTTP to save processing power.*
7. Save changes.

## Verification
Wait 1-2 minutes, then try opening https://smclama.smcindiaonline.com in your browser.
