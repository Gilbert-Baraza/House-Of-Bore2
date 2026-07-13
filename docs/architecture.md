# House of Bore — Production Architecture & Infrastructure Design

This document details the architectural principles, infrastructure topology, and subsystem configurations driving the **House of Bore** high-availability production deployment.

---

## 1. Production Architecture Topology

```
+─────────────────────────────────────────────────────────────────────────────+
|                              CLIENT DEVICES                                 |
+─────────────────────────────────────────────────────────────────────────────+
                                       │ HTTPS (TLS 1.2 / 1.3)
                                       ▼
+─────────────────────────────────────────────────────────────────────────────+
|                         NGINX REVERSE PROXY LAYER                           |
|  • TLS Termination     • Rate Limiting / DDoS Buffer  • Gzip Compression     |
|  • Static / Media CDN  • Security Headers (CSP/HSTS)  • Buffer Overflows    |
+─────────────────────────────────────────────────────────────────────────────+
         │                                                        │
         │ /static/ & /media/                                     │ / (Application Traffic)
         ▼                                                        ▼
+───────────────────+                                  +──────────────────────+
| LOCAL STATICS /   |                                  |   GUNICORN WSGI      |
| CLOUDINARY MEDIA  |                                  |   APPLICATION POOL   |
+───────────────────+                                  |  (Sync Workers,      |
                                                       |   Preloaded Memory)  |
                                                       +──────────────────────+
                                                                  │
                 ┌────────────────────────────────────────────────┼───────────────────────┐
                 │ Django ORM (Persistent Connections)            │ Cache / Session Engine │
                 ▼                                                ▼                       ▼
+───────────────────────────────────+          +─────────────────────────────+  +───────────────────+
|      POSTGRESQL DATABASE          |          |      REDIS IN-MEMORY STORE  |  | SENTRY MONITORING |
|  • ACID Compliant Transactions    |          |  • db 0: Celery Broker      |  | & ERROR TRACKING  |
|  • PgBouncer Connection Pool Ready|          |  • db 0: Celery Result      |  +───────────────────+
+───────────────────────────────────+          |  • db 1: django-redis Cache |
                 ▲                             |  • db 1: Session Store      |
                 │                             +─────────────────────────────+
                 │                                                ▲
                 │ Async DB Queries                               │ Redis Pub/Sub Tasks
+────────────────┴───────────────────+          +─────────────────┴───────────+
|        CELERY BEAT SCHEDULER       |─────────►|    CELERY ASYNC WORKERS     |
|  • Expire Pending Orders (Hourly)  |          |  • Queue: high_priority     |
|  • Clear Abandoned Carts (Daily)   |          |  • Queue: default           |
|  • Inventory Alerts (4 Hours)      |          |  • Queue: low_priority      |
+────────────────────────────────────+          +─────────────────────────────+
                                                                  │
                                                                  ▼
                                                   +──────────────────────────+
                                                   |    EXTERNAL GATEWAYS     |
                                                   |  • Stripe / PayPal / M-Pesa|
                                                   |  • SMTP / SendGrid Email |
                                                   +──────────────────────────+
```

---

## 2. Infrastructure Design Decisions

### 1. Unified Codebase with Environment Routing
Instead of separate branch trees for dev and prod, `config/settings/__init__.py` dynamically intercepts `DJANGO_ENV` (`development` vs `production`). Shared definitions live in `base.py`, while `development.py` and `production.py` only override what differs. Startup checks fail fast with formatted explanations when essential configuration keys (like `SECRET_KEY` or `REDIS_URL`) are omitted.

### 2. Gunicorn WSGI Worker Selection
We deploy Gunicorn using `sync` workers (`worker_class = "sync"`) with `preload_app = True` and worker recycling (`max_requests = 1000`).
- **Why `sync`?** Django's ORM and most third-party database drivers (including psycopg3 synchronous connections) are not fully async-safe under high concurrency without explicit thread isolation. `sync` workers guarantee deterministic request processing without async race conditions or thread deadlocks.
- **Why `preload_app`?** Preloading parses all Python modules and Django models once before worker forking, reducing RAM footprint by ~40% via Linux copy-on-write (COW) memory sharing.

### 3. Redis Separation Strategy
Redis (`django-redis` engine) serves three distinct high-throughput functions separated by database indexes:
- `redis://127.0.0.1:6379/0` (`db 0`): Celery Task Broker and Result Backend.
- `redis://127.0.0.1:6379/1` (`db 1`): Django Cache (`CACHES['default']`) and Session Backend (`SESSION_ENGINE = "django.contrib.sessions.backends.cache"`).
Separating `db 0` and `db 1` ensures `cache.clear()` operations or cache eviction policies do not flush active background tasks from Celery queues.

---

## 3. Celery & Celery Beat Architecture

All long-running, network-bound, or bulk operations are executed asynchronously across three prioritized queues:

| Queue Name | Responsibilities | Concurrency / Routing |
| :--- | :--- | :--- |
| **`high_priority`** | Payment webhook verifications, order confirmation email dispatches, security alerts. | Processed first; never blocked by background maintenance. |
| **`default`** | Order placement updates, inventory stock adjustments, fulfillment workflows. | Standard FIFO processing queue. |
| **`low_priority`** | Abandoned cart clearing, session cleanup, database `ANALYZE`, webhook log purging. | Processed during low traffic windows or idle worker capacity. |

---

## 4. Logging & Monitoring Strategy

### Structured Rotating File Handlers
Logs are separated by domain into `logs/*.log` files using `RotatingFileHandler` (capped at 10MB per file with 5 backups) to prevent disk exhaustion:
- **`django.log`**: Core framework errors, ORM anomalies, order lifecycle updates.
- **`requests.log`**: HTTP 4xx/5xx requests (`django.request`).
- **`payments.log`**: Webhook signatures, gateway API responses, payment state transitions (`payments`).
- **`security.log`**: Suspicious authentication attempts, CSRF failures, rate limit breaches (`security`).
- **`celery.log`**: Background task retries, worker errors (`celery`).

### Real-Time Error Monitoring (Sentry SDK)
When `SENTRY_DSN` is configured in `production.py`, the Sentry SDK automatically intercepts unhandled exceptions, attaches database queries, captures user identity (if authenticated), and tags the release version (`SENTRY_RELEASE`).

---

## 5. Secret Management & Security Hardening

- **Zero Hardcoded Secrets**: `python-decouple` reads variables strictly from environment memory (`.env` during local dev).
- **Cookie & Header Hardening**: Production enforces `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE="Lax"`, `SECURE_SSL_REDIRECT=True`, `SECURE_HSTS_SECONDS=31536000`, and `Referrer-Policy: strict-origin-when-cross-origin`.
- **Payload Protection**: `FILE_UPLOAD_MAX_MEMORY_SIZE=10MB` and `DATA_UPLOAD_MAX_MEMORY_SIZE=5MB` protect against memory exhaustion attacks during large file or webhook payload deliveries.
