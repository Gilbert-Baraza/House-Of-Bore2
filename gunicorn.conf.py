# gunicorn.conf.py
"""
gunicorn.conf.py
──────────────────────────────────────────────────────────────────────────────
WHY THIS FILE EXISTS:
    Production-grade Gunicorn WSGI server configuration for House of Bore.
    This replaces Django's built-in development server, which is single-threaded,
    not hardened for security, and cannot handle concurrent requests.

USAGE:
    gunicorn config.wsgi:application -c gunicorn.conf.py

    Or with environment variables:
    DJANGO_ENV=production gunicorn config.wsgi:application -c gunicorn.conf.py

KEY DESIGN DECISIONS:
    • Workers = 2 * CPU_COUNT + 1 — Gunicorn's official recommendation
    • Sync worker class — safest for Django ORM (avoids async footguns)
    • Max requests = 1000 — automatic worker recycling prevents memory leaks
    • Graceful timeout = 30s — allows in-flight requests to complete on reload
    • Preload = True — shares loaded app memory across forked workers
──────────────────────────────────────────────────────────────────────────────
"""

import multiprocessing
import os

# ─── Binding ──────────────────────────────────────────────────────────────────
# Bind to all interfaces on port 8000. Nginx reverse proxy connects here.
# Override with GUNICORN_BIND environment variable.
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")

# ─── Workers ──────────────────────────────────────────────────────────────────
# Gunicorn recommendation: 2-4 workers per CPU core.
# (2 * CPU_COUNT + 1) provides a balance between throughput and memory usage.
# Override with WEB_CONCURRENCY environment variable.
workers = int(os.environ.get("WEB_CONCURRENCY", multiprocessing.cpu_count() * 2 + 1))

# Sync worker class: each worker handles one request at a time.
# This is the safest option for Django because the ORM is not async-safe.
# Switch to "gthread" if you need concurrent I/O within a single worker.
worker_class = "sync"

# Number of threads per worker (only used with gthread worker class).
threads = int(os.environ.get("GUNICORN_THREADS", 1))

# ─── Timeouts ─────────────────────────────────────────────────────────────────
# Maximum time (seconds) a worker can spend processing a single request.
# 120s accommodates slow payment webhook verification and report generation.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 120))

# Time to wait for workers to finish during graceful reload/shutdown.
# Workers receive SIGTERM, then SIGKILL after this many seconds.
graceful_timeout = 30

# Time to wait for the next request on a Keep-Alive connection.
keepalive = 5

# ─── Worker Lifecycle ─────────────────────────────────────────────────────────
# Automatically restart workers after serving this many requests.
# Prevents gradual memory leaks from accumulating over long-running workers.
max_requests = 1000

# Add random jitter (0 to max_requests_jitter) to prevent all workers from
# restarting simultaneously, which would cause a brief service interruption.
max_requests_jitter = 50

# ─── Application Preloading ──────────────────────────────────────────────────
# Load the Django application before forking workers. This shares the loaded
# code in memory across all workers (copy-on-write) and catches import errors
# at startup rather than per-worker.
preload_app = True

# ─── Logging ──────────────────────────────────────────────────────────────────
# Access log: records every HTTP request handled by Gunicorn.
# Error log: captures worker errors, startup/shutdown events, and exceptions.
accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")  # "-" means stdout
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")     # "-" means stderr
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Custom access log format matching our structured logging pattern.
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ─── Process Naming ──────────────────────────────────────────────────────────
# Name shown in `ps aux` and system monitoring tools.
proc_name = "house_of_bore"

# ─── Security ────────────────────────────────────────────────────────────────
# Limit the size of HTTP request headers to prevent slow-loris attacks.
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# ─── Temporary Files ─────────────────────────────────────────────────────────
# Directory for Gunicorn's temporary worker heartbeat files.
# Use /dev/shm (shared memory) on Linux for better performance.
tmp_dir = os.environ.get("GUNICORN_TMP_DIR", "/tmp")


# ─── Server Hooks ────────────────────────────────────────────────────────────

def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("House of Bore — Gunicorn starting with %d workers", server.app.cfg.workers)


def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)


def worker_exit(server, worker):
    """Called when a worker process exits."""
    server.log.info("Worker exited (pid: %s)", worker.pid)
