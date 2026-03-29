"""AgentMarket API — FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from backend.database import init_db
from backend.config import validate_config, API_PORT, API_HOST, PAYMENT_CURRENCY, PAYMENT_UNIT
from backend.security import SecurityHeadersMiddleware
from backend.routes_agents import router as agents_router
from backend.routes_jobs import router as jobs_router
from backend.routes_escrow import router as escrow_router
from backend.routes_messages import router as messages_router
from backend.routes_admin import router as admin_router
from backend.routes_public import router as public_router
from backend.routes_feedback import router as feedback_router
from backend.routes_onboard import router as onboard_router

app = FastAPI(
    title="AgentMarket",
    description="Multi-agent marketplace with ANS, escrow, and satoshi micropayments",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "currency": PAYMENT_CURRENCY, "unit": PAYMENT_UNIT}


app.include_router(agents_router, prefix="/api/agents", tags=["agents"])
app.include_router(jobs_router, prefix="/api/jobs", tags=["jobs"])
app.include_router(escrow_router, prefix="/api/escrow", tags=["escrow"])
app.include_router(messages_router, prefix="/api/messages", tags=["messages"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(public_router, prefix="/api/public", tags=["public"])
app.include_router(feedback_router, prefix="/api/feedback", tags=["feedback"])
app.include_router(onboard_router, prefix="/api/onboard", tags=["onboard"])

# Static files MUST be mounted last — Starlette mount() creates a catch-all sub-app
frontend_path = Path(__file__).parent.parent / "frontend" / "public"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")


@app.on_event("startup")
async def startup():
    validate_config()
    init_db()
    print(f"AgentMarket v0.1.0 | {PAYMENT_CURRENCY} ({PAYMENT_UNIT}) | http://{API_HOST}:{API_PORT}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
