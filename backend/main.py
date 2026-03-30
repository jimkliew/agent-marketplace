"""AgentMarket API — FastAPI application. Production-hardened."""

import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from backend.database import init_db
from backend.config import validate_config, API_PORT, API_HOST, PAYMENT_CURRENCY, PAYMENT_UNIT
from backend.security import SecurityHeadersMiddleware
from backend.logging_config import RequestLoggingMiddleware, logger
from backend.routes_agents import router as agents_router
from backend.routes_jobs import router as jobs_router
from backend.routes_escrow import router as escrow_router
from backend.routes_messages import router as messages_router
from backend.routes_admin import router as admin_router
from backend.routes_public import router as public_router
from backend.routes_feedback import router as feedback_router
from backend.routes_onboard import router as onboard_router
from backend.routes_webhooks import router as webhooks_router
from backend.routes_ratings import router as ratings_router
from backend.auth import router as auth_router

app = FastAPI(
    title="AgentMarket",
    description="Multi-agent marketplace with ANS, escrow, and satoshi micropayments",
    version="0.1.0",
)

# CORS — production: set ALLOWED_ORIGINS env var to your domain
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# Request body size limit (1MB)
MAX_BODY_BYTES = 1_048_576


@app.middleware("http")
async def limit_request_body(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": "Request body too large. Max 1MB."})
    return await call_next(request)


# Global exception handler — no stack traces in production
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "currency": PAYMENT_CURRENCY, "unit": PAYMENT_UNIT}


app.include_router(agents_router, prefix="/api/agents", tags=["agents"])
app.include_router(auth_router, prefix="/api/agents", tags=["auth"])
app.include_router(jobs_router, prefix="/api/jobs", tags=["jobs"])
app.include_router(escrow_router, prefix="/api/escrow", tags=["escrow"])
app.include_router(messages_router, prefix="/api/messages", tags=["messages"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(public_router, prefix="/api/public", tags=["public"])
app.include_router(feedback_router, prefix="/api/feedback", tags=["feedback"])
app.include_router(onboard_router, prefix="/api/onboard", tags=["onboard"])
app.include_router(webhooks_router, prefix="/api/webhooks", tags=["webhooks"])
app.include_router(ratings_router, prefix="/api/ratings", tags=["ratings"])

# Static files MUST be mounted last
frontend_path = Path(__file__).parent.parent / "frontend" / "public"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")


@app.on_event("startup")
async def startup():
    import asyncio
    from backend.scheduler import deadline_loop
    validate_config()
    init_db()
    asyncio.create_task(deadline_loop())
    logger.info(f"AgentMarket v0.1.0 | {PAYMENT_CURRENCY} ({PAYMENT_UNIT}) | http://{API_HOST}:{API_PORT}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
