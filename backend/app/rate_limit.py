"""Simple in-memory IP-based rate limiter middleware."""

import time
from collections import defaultdict
from collections.abc import Callable
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimiter:
    """Track per-IP request timestamps with a sliding window."""

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._store: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _clean(self, ip: str, now: float) -> None:
        cutoff = now - self._window
        self._store[ip] = [t for t in self._store[ip] if t > cutoff]

    def is_allowed(self, ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            self._clean(ip, now)
            if len(self._store[ip]) >= self._max:
                return False
            self._store[ip].append(now)
            return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter: RateLimiter, skip_paths: set[str] | None = None) -> None:
        super().__init__(app)
        self._limiter = limiter
        self._skip = skip_paths or {"/health", "/"}

    async def dispatch(self, request: Request, call_next: Callable):
        if request.url.path in self._skip:
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        if not self._limiter.is_allowed(ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后重试。"},
            )
        return await call_next(request)
