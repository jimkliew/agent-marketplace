"""Structured JSON logging + request tracing middleware."""

import json
import time
import uuid
import logging
import sys
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request


class JSONFormatter(logging.Formatter):
    """Structured JSON log output for production."""

    def format(self, record):
        log = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "msg": record.getMessage(),
            "module": record.module,
        }
        if hasattr(record, "request_id"):
            log["request_id"] = record.request_id
        if hasattr(record, "agent_id"):
            log["agent_id"] = record.agent_id
        if record.exc_info and record.exc_info[1]:
            log["error"] = str(record.exc_info[1])
        return json.dumps(log)


def setup_logging():
    """Configure structured logging. Call once at startup."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger = logging.getLogger("agentmarket")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


logger = setup_logging()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs every request with timing, status, and request_id for tracing."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        start = time.time()

        response = await call_next(request)

        duration_ms = round((time.time() - start) * 1000, 1)
        agent_id = getattr(request.state, "agent_id", None)

        # Skip noisy health checks
        if request.url.path == "/api/health":
            return response

        extra = {"request_id": request_id}
        if agent_id:
            extra["agent_id"] = agent_id

        record = logging.LogRecord(
            name="agentmarket", level=logging.INFO, pathname="", lineno=0,
            msg=f"{request.method} {request.url.path} {response.status_code} {duration_ms}ms",
            args=(), exc_info=None,
        )
        for k, v in extra.items():
            setattr(record, k, v)
        logger.handle(record)

        response.headers["X-Request-ID"] = request_id
        return response
