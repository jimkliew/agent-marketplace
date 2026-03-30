#!/bin/bash
# Start AgentMarket — server + seed agents
# Usage: ./start.sh
# Usage: ./start.sh --seed  (also run 10 seed agents for marketplace liquidity)

set -e

echo "╔══════════════════════════════════════════╗"
echo "║  AgentMarket v0.1.0 — Satoshi Commerce   ║"
echo "╚══════════════════════════════════════════╝"

# Setup
cp -n .env.example .env 2>/dev/null || true

# Start server
echo "[1/2] Starting API server on :8000..."
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
sleep 2

# Health check
if curl -sf http://localhost:8000/api/health > /dev/null; then
    echo "[OK]  Server healthy"
else
    echo "[ERR] Server failed to start"
    kill $SERVER_PID 2>/dev/null
    exit 1
fi

echo ""
echo "Dashboard:    http://localhost:8000"
echo "Jobs:         http://localhost:8000/jobs.html"
echo "Agents:       http://localhost:8000/agents.html"
echo "Simulation:   http://localhost:8000/simulation.html"
echo "Admin:        http://localhost:8000/admin.html"
echo "API docs:     http://localhost:8000/docs"
echo "Agent spec:   http://localhost:8000/api/onboard/spec"
echo ""

# Seed agents (optional)
if [ "$1" = "--seed" ]; then
    echo "[2/2] Starting 10 seed agents..."
    uv run python -m simulate.seed_agents &
    SEED_PID=$!
    echo "[OK]  Seed agents running (PID: $SEED_PID)"
fi

echo "Press Ctrl+C to stop"
wait $SERVER_PID
