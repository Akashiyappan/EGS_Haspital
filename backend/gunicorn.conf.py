"""Gunicorn config for Linux production deployments (gunicorn does not run on Windows).

Run with: gunicorn app.main:app -c gunicorn.conf.py

Realtime note: WebSocket connections are tracked per worker process. With more
than one worker, chat/notification pushes only reach users connected to the same
worker (clients still receive everything on their next REST sync). Until a shared
broker (e.g. Redis pub/sub) is added behind app/realtime/manager.py, run a single
worker (WEB_CONCURRENCY=1) or accept polling-level latency across workers.
"""

import multiprocessing
import os

bind = os.getenv("BIND", "127.0.0.1:8000")
workers = int(os.getenv("WEB_CONCURRENCY", multiprocessing.cpu_count() * 2 + 1))
worker_class = "uvicorn.workers.UvicornWorker"
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1")
accesslog = None  # the app writes its own structured access log
errorlog = "-"
