"""Security — rate limiting, input sanitization, headers."""

import os
import re
import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

_rate_limits: dict[str, list[float]] = defaultdict(list)
_TESTING = os.getenv("TESTING", "").lower() in ("1", "true", "yes")


def check_rate_limit(key: str, max_requests: int, window_seconds: int):
    if _TESTING:
        return
    now = time.time()
    window_start = now - window_seconds
    _rate_limits[key] = [t for t in _rate_limits[key] if t > window_start]
    if len(_rate_limits[key]) >= max_requests:
        raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": str(window_seconds)})
    _rate_limits[key].append(now)


_HTML_RE = re.compile(r"<[^>]+>")

def sanitize_text(text: str) -> str:
    return _HTML_RE.sub("", text)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response
