# 🚀 Production Deployment Guide

This guide covers running the **AI Voice Calling & WhatsApp Outreach Platform** in production, with specific focus on running **OpenWA in Docker** reliably and safely.

---

## 📌 Does OpenWA in Docker Work for Production?

**Yes, running OpenWA inside Docker is the official and recommended method for production.**

Running OpenWA directly on a raw Linux host requires managing headless Chromium dependencies, Puppeteer binary versions, and OS graphics libraries (`libnss3`, `libasound2`, `libgbm`, etc.). Docker encapsulates all of this cleanly.

However, to run OpenWA reliably in production without crashes or losing WhatsApp connection, you **must satisfy these 5 critical requirements**:

### 1. Volume Persistence (Prevent Re-Scanning QR Code)
In Docker, containers are ephemeral. If you don't mount a persistent volume to `/app/data`, **every time the container restarts or updates, your WhatsApp session is deleted and you must scan the QR code again.**
```yaml
volumes:
  - openwa_data:/app/data  # Keeps WhatsApp credentials & SQLite database intact
```

### 2. Chromium Shared Memory (`shm_size: '1gb'`)
Chromium runs headless inside OpenWA. By default, Docker only allocates 64MB to `/dev/shm`. Under moderate message load, this causes Chromium to crash with `SIGBUS` or `Target closed` errors.
```yaml
shm_size: '1gb'  # Prevents browser tab out-of-memory crashes
```

### 3. Webhook URL Configuration
In production on Linux servers, `host.docker.internal` does **not** resolve by default without `extra_hosts`. 
- When running in our unified `docker-compose.yml`, OpenWA talks directly to the backend container:
  `WEBHOOK_URL=http://backend:8000/api/telephony/openwa/webhook`
- When using a public domain:
  `WEBHOOK_URL=https://your-domain.com/api/telephony/openwa/webhook`

### 4. API Key Security
Never expose OpenWA's port `2785` to the public internet without an API Key. Anyone discovering the port could control your WhatsApp account.
Set `OPENWA_API_KEY` in both OpenWA and the FastAPI backend.

### 5. WhatsApp Account Safety & Anti-Ban Rules
Because OpenWA uses WhatsApp Web automation:
- **Warm up new SIM cards**: Start with 20–30 messages/day for the first week before scaling.
- **Use delays**: Never blast 500 messages in 1 second. The platform's campaign runner distributes dispatches with human-like delays.
- **Honour Opt-Outs**: If a customer replies "STOP" or "UNSUBSCRIBE", the platform marks them as unsubscribed automatically.

---

## 🏗️ Production Architecture

```
[ Internet / Customer ]
         │
         ▼
[ Nginx Reverse Proxy / SSL (Port 80/443) ]
         │
         ├───► / (Frontend UI - React/Vite served via Nginx)
         ├───► /api/ & /ws/ (Backend - FastAPI + Uvicorn)
         │           │
         │           ├───► PostgreSQL (Database)
         │           ├───► Redis (Queue & Cache)
         │           └───► OpenWA Gateway (Port 2785)
         │                       │
         └───────────────────────┴───► WhatsApp Web Servers
```

---

## 🛠️ Step-by-Step Production Deployment

### Step 1: Copy Production Environment Configuration
```bash
cp .env.production.example .env.production
```

Edit `.env.production` and configure your production values:
```ini
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_db_password
POSTGRES_DB=voice_platform

SECRET_KEY=generate_via_openssl_rand_hex_32
GEMINI_API_KEY=your_gemini_api_key
OPENWA_API_KEY=your_openwa_api_key
FRONTEND_ORIGIN=https://yourdomain.com
```

### Step 2: Build & Start All Services
Run Docker Compose in detached mode:
```bash
docker compose --env-file .env.production up -d --build
```

### Step 3: Verify Container Health
Check that all 5 services are running and healthy:
```bash
docker compose ps
```
You should see:
- `voice-calling-postgres` (healthy)
- `voice-calling-redis` (healthy)
- `openwa-gateway` (running)
- `voice-calling-backend` (healthy)
- `voice-calling-frontend` (running)

### Step 4: Link Your WhatsApp Number
1. Open your browser and navigate to:
   - Frontend Dashboard: `http://<your-server-ip>:3000/whatsapp-gateway`
   - Or directly to OpenWA Dashboard: `http://<your-server-ip>:2785`
2. Open WhatsApp on your phone -> **Linked Devices** -> **Link a Device**.
3. Scan the QR code displayed on the screen.
4. Once scanned, the status will show **CONNECTED**. The session is saved permanently in the Docker volume.

### Step 5: Test Webhook & Outbound Messages
Send a test message from `/whatsapp-gateway` on the frontend or trigger an AI campaign. 
Incoming replies will hit the webhook at `/api/telephony/openwa/webhook`, generate an AI response via Gemini, and automatically reply to the customer in real-time.

---

## 🔒 Production SSL / Domain Setup (Nginx Host Reverse Proxy)

If you have a domain name (e.g. `voice.yourcompany.com`), configure Nginx on your host with Let's Encrypt SSL:

```nginx
server {
    server_name voice.yourcompany.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Optional: Direct access to OpenWA dashboard (restricted to your IP or protected)
    location /openwa/ {
        proxy_pass http://localhost:2785/;
        proxy_set_header Host $host;
    }
}
```

Then install SSL via Certbot:
```bash
sudo certbot --nginx -d voice.yourcompany.com
```

---

## 📋 Useful Production Commands

```bash
# View live logs of all services
docker compose logs -f

# View live OpenWA logs (session & QR events)
docker compose logs -f openwa

# View backend logs (incoming webhooks & AI responses)
docker compose logs -f backend

# Restart OpenWA without losing WhatsApp login
docker compose restart openwa

# Gracefully stop the stack
docker compose down
```

---

## ⚠️ Troubleshooting: Render "502 Bad Gateway" on WhatsApp Gateway

If your production backend logs show `502 Bad Gateway` from Render when calling OpenWA or opening the QR code:

### 1. Root Causes:
1. **Binding to localhost**: OpenWA defaults `BIND_HOST` to `127.0.0.1`. Inside a Docker container on Render, Render's edge router attempts to reach the container and gets connection refused.
   - **Fix**: Set `BIND_HOST=0.0.0.0`.
2. **Headless Chromium Crash (Out of Memory)**: The default `whatsapp-web.js` engine launches headless Chromium, which consumes 800MB–1.2GB RAM and crashes on Render Starter or Free tier with exit code 137 (OOM).
   - **Fix**: Set `ENGINE_TYPE=baileys`. Baileys uses pure WebSockets, requires NO Chromium, uses only ~60MB RAM, boots in 2 seconds, and works reliably on small cloud instances.
3. **Render Free Tier Sleep / Spun Down**: Render free services spin down after 15 minutes of inactivity. When a request arrives, Render takes 45–60 seconds to wake up the service, returning 502 until the container is ready.
   - **Fix**: Upgrade to Starter ($7/mo) or wait 45 seconds and click "Retry Starting Session".
4. **Port Configuration**: OpenWA must have both `PORT=2785` and `API_PORT=2785` matching Render's routed port.

### 2. Required Render Environment Variables for `openwa-gateway`:
```env
PORT=2785
API_PORT=2785
BIND_HOST=0.0.0.0
ENGINE_TYPE=baileys
NODE_ENV=production
DB_TYPE=sqlite
DB_SQLITE_PATH=/app/data/openwa.sqlite
MEDIA_STORAGE=local
MEDIA_LOCAL_PATH=/app/data/media
MEDIA_CONVERSION_ENABLED=true
ENABLE_SWAGGER=true
WEBHOOK_SSRF_PROTECT=false
```

### 3. Backend Environment Variable:
For fastest performance and avoiding public timeouts, set `OPENWA_BASE_URL` on your backend:
- Over Render Private Network: `http://openwa-gateway:2785`
- Or your public service URL: `https://<your-openwa-slug>.onrender.com`
