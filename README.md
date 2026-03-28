# ForkYouToo — Backend

> Django REST API powering the ForkYouToo ALU GitHub repository explorer.

Frontend repo: https://github.com/Oluwatimilehin2004/ForkYouToo

---

## 🔌 External APIs Used

| API | Purpose | Docs |
|-----|---------|------|
| [GitHub REST API v3](https://docs.github.com/en/rest) | Search repos, fork, update files | https://docs.github.com/en/rest |
| GitHub Search API | Find ALU repos by name/topic/description | https://docs.github.com/en/rest/search |
| GitHub Contents API | Read/write README and settings files | https://docs.github.com/en/rest/repos/contents |

*Credit: GitHub API provided by GitHub, Inc. — https://github.com*

---

## ✨ Key Features

- JWT authentication (register, login)
- GitHub API integration — search, fork, rename, attribute repos
- Parallel repo fetching with `ThreadPoolExecutor` (14 queries at once)
- 30-minute in-memory caching of GitHub results
- Server-side pagination (`?page=&per_page=&sort=`)
- Sort by recency, stars, or forks
- Import history tracked per user

---

## 🚀 Running Locally

### 1. Clone

```bash
git clone https://github.com/Oluwatimilehin2004/ForkYouToo-Backend.git
cd ForkYouToo-Backend
```

### 2. Virtual environment

```bash
python -m venv env

# Windows
env\Scripts\activate

# macOS / Linux
source env/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment variables

```bash
cp .env.example .env
# Edit .env with your values
```

Required values in `.env`:
```
SECRET_KEY=your-django-secret-key
DEBUG=True
GITHUB_TOKEN=your-github-pat-with-repo-and-user-scopes
```

### 5. Settings — cache

Add to `settings.py`:
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
```

### 6. Migrate and run

```bash
python manage.py migrate
python manage.py runserver
```

---

## 🌐 API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/register/` | None | Register new user |
| POST | `/api/login/` | None | Login, returns JWT |
| GET | `/api/alu-repos/` | JWT | Paginated ALU repos |
| POST | `/api/import/` | JWT | Fork a repo |
| GET | `/api/imports/` | JWT | User's import history |
| GET | `/api/import/<id>/status/` | JWT | Single import status |
| POST | `/api/connect-github/` | JWT | Save user's GitHub token |

### `GET /api/alu-repos/` query params

| Param | Default | Options |
|-------|---------|---------|
| `page` | 1 | any integer |
| `per_page` | 20 | 1–100 |
| `sort` | recent | `recent`, `stars`, `forks` |

---

## 🚢 Deployment (Part Two)

### Architecture

```
Internet (HTTPS)
      │
      ▼
  Lb01 — HAProxy (SSL termination, load balancing)
      │
      ├──▶ Web01 — Nginx + Gunicorn (Django)
      └──▶ Web02 — Nginx + Gunicorn (Django)
```

---

### A. Deploy Backend on Web01 AND Web02

Run all of the following on **both** Web01 and Web02:

#### 1. SSH into the server
```bash
ssh ubuntu@<WEB01_IP>
# repeat separately for Web02
```

#### 2. Install system dependencies
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv nginx git -y
```

#### 3. Clone backend repo
```bash
cd /var/www
sudo git clone https://github.com/Oluwatimilehin2004/ForkYouToo-Backend.git forkyoutoo-backend
sudo chown -R ubuntu:ubuntu /var/www/forkyoutoo-backend
cd /var/www/forkyoutoo-backend
```

#### 4. Set up virtual environment
```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

#### 5. Set up environment variables
```bash
cp .env.example .env
nano .env
```

Fill in:
```
SECRET_KEY=your-production-secret-key
DEBUG=False
GITHUB_TOKEN=your-github-pat
ALLOWED_HOSTS=<WEB01_IP>,<LB01_IP>,localhost
```

#### 6. Update settings.py for production
```python
# settings.py
import os
from decouple import config

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
```

#### 7. Migrate and collect static files
```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

#### 8. Create Gunicorn systemd service

```bash
sudo nano /etc/systemd/system/forkyoutoo.service
```

Paste:
```ini
[Unit]
Description=ForkYouToo Gunicorn Daemon
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/var/www/forkyoutoo-backend
ExecStart=/var/www/forkyoutoo-backend/env/bin/gunicorn \
    --workers 3 \
    --bind 127.0.0.1:8000 \
    forkyoutoo.wsgi:application \
    --log-file /var/log/forkyoutoo-gunicorn.log \
    --access-logfile /var/log/forkyoutoo-access.log
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable forkyoutoo
sudo systemctl start forkyoutoo
sudo systemctl status forkyoutoo   # should show: active (running)
```

---

### B. Deploy Frontend (Static Files) on Web01 AND Web02

On **both** Web01 and Web02:

```bash
cd /var/www
sudo git clone https://github.com/Oluwatimilehin2004/ForkYouToo-Frontend.git forkyoutoo-frontend
sudo chown -R ubuntu:ubuntu /var/www/forkyoutoo-frontend
```

Update API URLs in each HTML file to point to your load balancer:
```bash
cd /var/www/forkyoutoo-frontend
# Replace localhost with your LB01 IP in all HTML files
sed -i 's|http://127.0.0.1:8000|http://<LB01_IP>|g' *.html
```

---

### C. Configure Nginx on Web01 AND Web02

```bash
sudo nano /etc/nginx/sites-available/forkyoutoo
```

Paste:
```nginx
server {
    listen 80;
    server_name _;

    # Frontend static files
    root /var/www/forkyoutoo-frontend;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # CORS headers
        add_header Access-Control-Allow-Origin *;
        add_header Access-Control-Allow-Methods 'GET, POST, OPTIONS, PATCH, DELETE';
        add_header Access-Control-Allow-Headers 'Authorization, Content-Type';
    }

    # Static/media files from Django
    location /static/ {
        alias /var/www/forkyoutoo-backend/staticfiles/;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/forkyoutoo /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default   # remove default site
sudo nginx -t                                   # must say: syntax is ok
sudo systemctl reload nginx
```

#### Test each server directly (before load balancer):
```bash
curl http://<WEB01_IP>/api/alu-repos/ -H "Authorization: Bearer <your_token>"
curl http://<WEB02_IP>/api/alu-repos/ -H "Authorization: Bearer <your_token>"
```

Both should return JSON, not an HTML error page.

---

### D. Configure HAProxy on Lb01 (You Said This Is Done — Verify It)

SSH into Lb01:
```bash
ssh ubuntu@<LB01_IP>
cat /etc/haproxy/haproxy.cfg
```

It should look like this (if not, update it):
```
global
    log /dev/log local0
    maxconn 2048
    daemon

defaults
    log global
    mode http
    option httplog
    option dontlognull
    timeout connect 5s
    timeout client  30s
    timeout server  30s

frontend http_front
    bind *:80
    default_backend web_servers

backend web_servers
    balance roundrobin
    option httpchk GET /
    server web01 <WEB01_IP>:80 check
    server web02 <WEB02_IP>:80 check
```

```bash
sudo haproxy -c -f /etc/haproxy/haproxy.cfg   # check config
sudo systemctl restart haproxy
sudo systemctl status haproxy                   # must be active
```

#### Verify load balancing is working:
```bash
# Run this 4 times — you should see traffic alternate between Web01 and Web02
curl http://<LB01_IP>/
```

---

### E. SSL/TLS with Self-Signed Certificate on Lb01

Since you said you haven't confirmed this yet — do it now. SSL goes on the **load balancer**, not the web servers (HAProxy terminates SSL, then forwards plain HTTP to Web01/Web02).

#### 1. Generate the self-signed certificate
```bash
sudo mkdir -p /etc/ssl/forkyoutoo
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/ssl/forkyoutoo/forkyoutoo.key \
    -out /etc/ssl/forkyoutoo/forkyoutoo.crt \
    -subj "/C=RW/ST=Kigali/L=Kigali/O=ALU/OU=Student/CN=<LB01_IP>"
```

#### 2. Combine cert + key for HAProxy (HAProxy needs them in one file)
```bash
sudo cat /etc/ssl/forkyoutoo/forkyoutoo.crt \
         /etc/ssl/forkyoutoo/forkyoutoo.key \
    | sudo tee /etc/ssl/forkyoutoo/forkyoutoo.pem
sudo chmod 600 /etc/ssl/forkyoutoo/forkyoutoo.pem
```

#### 3. Update HAProxy config to add HTTPS
```bash
sudo nano /etc/haproxy/haproxy.cfg
```

Replace/update to:
```
global
    log /dev/log local0
    maxconn 2048
    daemon

defaults
    log global
    mode http
    option httplog
    option dontlognull
    timeout connect 5s
    timeout client  30s
    timeout server  30s

# Redirect HTTP → HTTPS
frontend http_front
    bind *:80
    redirect scheme https code 301 if !{ ssl_fc }

# HTTPS frontend — SSL terminates here
frontend https_front
    bind *:443 ssl crt /etc/ssl/forkyoutoo/forkyoutoo.pem
    default_backend web_servers

backend web_servers
    balance roundrobin
    option httpchk GET /
    server web01 <WEB01_IP>:80 check
    server web02 <WEB02_IP>:80 check
```

```bash
sudo haproxy -c -f /etc/haproxy/haproxy.cfg   # verify config
sudo systemctl restart haproxy
```

#### 4. Test HTTPS (the -k flag skips cert validation since it's self-signed)
```bash
curl -k https://<LB01_IP>/
curl -k https://<LB01_IP>/api/alu-repos/
```

You should get a response, not a connection refused.

#### 5. Update frontend HTML files to use HTTPS

On both Web01 and Web02:
```bash
cd /var/www/forkyoutoo-frontend
sed -i 's|http://<LB01_IP>|https://<LB01_IP>|g' *.html
```

---

### F. Final End-to-End Test Checklist

Run through every one of these:

```bash
# 1. Both web servers respond directly
curl http://<WEB01_IP>/
curl http://<WEB02_IP>/

# 2. Load balancer HTTPS works
curl -k https://<LB01_IP>/

# 3. API works through load balancer (get a JWT first via login)
curl -k -X POST https://<LB01_IP>/api/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass"}'

# 4. HAProxy stats (if enabled) show both servers UP
curl http://<LB01_IP>:8404/stats
```

In the browser, open `https://<LB01_IP>` — you'll see a cert warning (expected for self-signed), click "proceed anyway" and the app should load fully.

---

## ⚠️ Challenges & Solutions

| Challenge | Solution |
|-----------|----------|
| 500 repos causing 30+ second load times | Parallel `ThreadPoolExecutor` + 30-min cache |
| Infinite scroll not actually helping load time | True server-side pagination `?page=&per_page=` |
| Redis not installed but configured as cache | Switched to `LocMemCache` (zero setup) |
| `.env` accidentally committed with real token | Rewrote git history, revoked old token |
| `import_status` querying wrong FK | Fixed `user=request.user.profile` → `user=request.user` |

---

## 📦 Requirements

```
django
djangorestframework
djangorestframework-simplejwt
requests
Pillow
python-decouple
gunicorn
```

---

## 📄 License

MIT — built for educational purposes as part of ALU coursework.