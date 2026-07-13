# House of Bore — Deployment & Operations Guide

This document provides complete, step-by-step instructions for deploying and operating the **House of Bore** ecommerce platform across Local Development, Staging, and Production environments.

---

## 1. Environment Overview & Architecture

House of Bore uses a unified codebase with environment-driven configuration routing (`config/settings/__init__.py`).

| Component | Development | Production |
| :--- | :--- | :--- |
| **Settings Module** | `config.settings.development` (`DJANGO_ENV=development`) | `config.settings.production` (`DJANGO_ENV=production`) |
| **WSGI / ASGI Server** | `python manage.py runserver` | Gunicorn (`sync` workers, preloaded) / Uvicorn |
| **Reverse Proxy** | None (direct access) | Nginx (TLS termination, gzip, headers, rate limit) |
| **Database** | SQLite (`db.sqlite3`) | PostgreSQL (`CONN_MAX_AGE=60`) |
| **Cache & Sessions** | LocMemCache / local Redis | Redis via `django-redis` / `django.contrib.sessions.backends.cache` |
| **Background Queue** | Celery (local broker / eager mode) | Celery Worker & Celery Beat via Redis (`high_priority`, `default`, `low_priority` queues) |
| **Static Files** | Django `staticfiles` app | WhiteNoise (`CompressedManifestStaticFilesStorage`) |
| **Media Storage** | Local filesystem (`media/`) | Cloudinary (`django-cloudinary-storage`) or local with Nginx |
| **Email Delivery** | Console output (`console.EmailBackend`) | SMTP (`smtp.EmailBackend`) / SendGrid / Amazon SES |
| **Error Monitoring** | Console traceback logs | Sentry SDK (`sentry_sdk`) |

---

## 2. Local Development Setup

### Prerequisites
- Python 3.11+
- Node.js & npm (required for Tailwind CSS build pipeline)
- Git

### Initial Setup Commands
```bash
# 1. Clone the repository
git clone https://github.com/your-org/House-Of-Bore.git
cd House-Of-Bore

# 2. Create and activate Python virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# 3. Install development requirements
pip install -r requirements/development.txt

# 4. Copy environment variables template
cp .env.example .env

# 5. Run database migrations
python manage.py migrate

# 6. Install Tailwind CSS Node modules and build styles
python manage.py tailwind install
python manage.py tailwind build

# 7. Create an administrative superuser
python manage.py createsuperuser

# 8. Start the local development server
python manage.py runserver
```

To run the full test suite during development:
```bash
python manage.py test --noinput
```

---

## 3. Production Deployment Guide (Ubuntu / Debian Linux)

### Step 1: System Dependencies & PostgreSQL Setup
```bash
sudo apt update && sudo apt install -y python3-venv python3-dev postgresql postgresql-contrib redis-server nginx git build-essential

# Create PostgreSQL database and user
sudo -u postgres psql <<EOF
CREATE DATABASE house_of_bore_db;
CREATE USER hob_user WITH PASSWORD 'secure_production_password_here';
ALTER ROLE hob_user SET client_encoding TO 'utf8';
ALTER ROLE hob_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE hob_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE house_of_bore_db TO hob_user;
EOF
```

### Step 2: Application Code Setup
```bash
sudo mkdir -p /var/www/house-of-bore && sudo chown $USER:$USER /var/www/house-of-bore
cd /var/www/house-of-bore
git clone https://github.com/your-org/House-Of-Bore.git .

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements/production.txt

# Configure environment variables
cp .env.example .env
nano .env  # Set DJANGO_ENV=production, DB credentials, REDIS_URL, SECRET_KEY, ALLOWED_HOSTS
```

### Step 3: Database Migrations & Static Files
```bash
export DJANGO_ENV=production
python manage.py migrate --noinput
python manage.py tailwind install
python manage.py tailwind build
python manage.py collectstatic --noinput --clear
```

### Step 4: Systemd Service Configuration (Gunicorn)
Create `/etc/systemd/system/house-of-bore.service`:
```ini
[Unit]
Description=House of Bore Gunicorn WSGI Daemon
After=network.target postgresql.service redis.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/house-of-bore
Environment="PATH=/var/www/house-of-bore/venv/bin"
Environment="DJANGO_ENV=production"
ExecStart=/var/www/house-of-bore/venv/bin/gunicorn config.wsgi:application -c /var/www/house-of-bore/gunicorn.conf.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### Step 5: Systemd Service Configuration (Celery Worker & Beat)
Create `/etc/systemd/system/house-of-bore-celery.service`:
```ini
[Unit]
Description=House of Bore Celery Background Worker
After=network.target redis.service house-of-bore.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/house-of-bore
Environment="PATH=/var/www/house-of-bore/venv/bin"
Environment="DJANGO_ENV=production"
ExecStart=/var/www/house-of-bore/venv/bin/celery -A config worker -l info -Q high_priority,default,low_priority --concurrency=4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/house-of-bore-beat.service`:
```ini
[Unit]
Description=House of Bore Celery Beat Scheduler
After=network.target redis.service house-of-bore-celery.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/house-of-bore
Environment="PATH=/var/www/house-of-bore/venv/bin"
Environment="DJANGO_ENV=production"
ExecStart=/var/www/house-of-bore/venv/bin/celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Step 6: Enable Services & Nginx Reverse Proxy
```bash
sudo chown -R www-data:www-data /var/www/house-of-bore/staticfiles /var/www/house-of-bore/media /var/www/house-of-bore/logs
sudo systemctl daemon-reload
sudo systemctl enable --now house-of-bore.service house-of-bore-celery.service house-of-bore-beat.service

# Setup Nginx
sudo cp deploy/nginx/house_of_bore.conf /etc/nginx/sites-available/house_of_bore
sudo ln -s /etc/nginx/sites-available/house_of_bore /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

---

## 4. Verification & Health Monitoring

Verify that the platform is operating cleanly:
```bash
# Check Django readiness probe (verifies database and Redis cache connectivity)
curl -s http://localhost/health/ready/ | jq .

# Check liveness heartbeat
curl -s http://localhost/health/live/ | jq .

# Check Gunicorn status and logs
sudo systemctl status house-of-bore.service
sudo tail -n 50 /var/www/house-of-bore/logs/django.log

# Check Celery worker queues and registered tasks
/var/www/house-of-bore/venv/bin/celery -A config inspect active
```

---

## 5. Zero-Downtime Rollback Procedure

If a production release introduces critical errors:
```bash
cd /var/www/house-of-bore
# 1. Revert Git checkout to the last stable release tag or commit hash
git checkout v1.4.2

# 2. Re-collect static files and sync dependencies if changed
source venv/bin/activate
pip install -r requirements/production.txt
python manage.py collectstatic --noinput

# 3. Gracefully reload Gunicorn workers (SIGHUP triggers zero-downtime worker replacement)
sudo systemctl reload house-of-bore.service

# 4. Restart Celery workers
sudo systemctl restart house-of-bore-celery.service

# 5. Verify readiness endpoint confirms recovery
curl -f http://localhost/health/ready/ || echo "CRITICAL: Rollback verification failed!"
```
