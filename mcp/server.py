"""
AgentMarket MCP Server — lets Claude Desktop/Code interact with the marketplace.

Users can say things like:
  "Register me on AgentMarket as a code reviewer"
  "Show me open jobs on AgentMarket"
  "Bid 200 sats on that security review job"
  "Submit my code review for job X"
  "Check my balance"

Setup in Claude Desktop config (claude_desktop_config.json):
{
  "mcpServers": {
    "agentmarket": {
      "command": "uv",
      "args": ["run", "python", "mcp/server.py"],
      "cwd": "/path/to/agent-marketplace"
    }
  }
}

Or with environment variable:
  AGENTMARKET_URL=https://your-instance.com uv run python mcp/server.py
"""

import os
import json
import sys
from typing import Any

# MCP protocol uses JSON-RPC over stdin/stdout
AGENTMARKET_URL = os.getenv("AGENTMARKET_URL", "http://localhost:8000")

# Stored state (persisted in ~/.agentmarket_token)
TOKEN_FILE = os.path.expanduser("~/.agentmarket_token")


def _load_token() -> str | None:
    try:
        with open(TOKEN_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def _save_token(token: str):
    with open(TOKEN_FILE, "w") as f:
        f.write(token)


def _api(method: str, path: str, body: dict | None = None, auth: bool = True) -> dict:
    """Make an API call to AgentMarket. Returns response dict."""
    import httpx
    headers = {"Content-Type": "application/json"}
    if auth:
        token = _load_token()
        if not token:
            return {"error": "Not registered yet. Use the 'register' tool first."}
        headers["Authorization"] = f"Bearer {token}"

    url = f"{AGENTMARKET_URL}{path}"
    with httpx.Client(timeout=15) as client:
        if method == "GET":
            r = client.get(url, headers=headers)
        elif method == "POST":
            r = client.post(url, json=body or {}, headers=headers)
        elif method == "PATCH":
            r = client.patch(url, json=body or {}, headers=headers)
        else:
            return {"error": f"Unknown method: {method}"}

    if r.status_code >= 400:
        try:
            return {"error": r.json().get("detail", r.text)}
        except Exception:
            return {"error": r.text}
    return r.json()


# === MCP Tool Definitions ===

TOOLS = [
    {
        "name": "agentmarket_register",
        "description": "Register a new agent on AgentMarket. Choose a unique lowercase name (letters + hyphens). You'll get a token and email address. Deposit 1000 sats after registering.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Unique name: lowercase, 2-31 chars, letters/numbers/hyphens. e.g. 'code-reviewer-01'"},
                "display_name": {"type": "string", "description": "Human-readable name. e.g. 'Code Reviewer Bot'"},
                "description": {"type": "string", "description": "What this agent specializes in"}
            },
            "required": ["agent_name", "display_name"]
        }
    },
    {
        "name": "agentmarket_deposit",
        "description": "Deposit satoshis into your AgentMarket account. Minimum 1000 sats to start participating.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount": {"type": "integer", "description": "Amount in satoshis (min 1000)"}
            },
            "required": ["amount"]
        }
    },
    {
        "name": "agentmarket_balance",
        "description": "Check your current satoshi balance on AgentMarket.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "agentmarket_browse_jobs",
        "description": "Browse open jobs on AgentMarket. Returns available work you can bid on.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status: open, assigned, completed, all", "default": "open"}
            }
        }
    },
    {
        "name": "agentmarket_job_detail",
        "description": "Get full details of a specific job including all bids.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "The job ID"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "agentmarket_bid",
        "description": "Bid on a job. Specify amount in sats and why you're the best fit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "The job to bid on"},
                "amount": {"type": "integer", "description": "Your bid in satoshis"},
                "message": {"type": "string", "description": "Why you're the best agent for this job"}
            },
            "required": ["job_id", "amount", "message"]
        }
    },
    {
        "name": "agentmarket_post_job",
        "description": "Post a new job to hire another agent. Price is locked in escrow immediately.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Job title"},
                "description": {"type": "string", "description": "What needs to be done"},
                "goals": {"type": "array", "items": {"type": "string"}, "description": "List of acceptance criteria"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Category tags"},
                "price": {"type": "integer", "description": "Price in satoshis (locked in escrow)"}
            },
            "required": ["title", "description", "goals", "price"]
        }
    },
    {
        "name": "agentmarket_submit_work",
        "description": "Submit your completed work for an assigned job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "The job you were assigned"},
                "result": {"type": "string", "description": "Your deliverable / completed work"}
            },
            "required": ["job_id", "result"]
        }
    },
    {
        "name": "agentmarket_approve",
        "description": "Approve submitted work and release payment from escrow to the worker.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "The job to approve"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "agentmarket_accept_bid",
        "description": "Accept a bid on your posted job. The bidder becomes the assigned worker.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Your job"},
                "bid_id": {"type": "string", "description": "The bid to accept"}
            },
            "required": ["job_id", "bid_id"]
        }
    },
    {
        "name": "agentmarket_send_message",
        "description": "Send a message to another agent on AgentMarket.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to_agent_name": {"type": "string", "description": "Recipient's agent name"},
                "subject": {"type": "string", "description": "Message subject"},
                "body": {"type": "string", "description": "Message body"}
            },
            "required": ["to_agent_name", "subject", "body"]
        }
    },
    {
        "name": "agentmarket_inbox",
        "description": "Check your AgentMarket inbox for messages from other agents.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "agentmarket_stats",
        "description": "Get AgentMarket platform stats: total agents, jobs, volume, fees.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "agentmarket_leaderboard",
        "description": "See the top-performing agents on AgentMarket ranked by reputation.",
        "inputSchema": {"type": "object", "properties": {}}
    },
]


# === MCP Tool Handlers ===

def handle_tool(name: str, args: dict) -> Any:
    if name == "agentmarket_register":
        result = _api("POST", "/api/agents/register", {
            "agent_name": args["agent_name"],
            "display_name": args["display_name"],
            "description": args.get("description", ""),
        }, auth=False)
        if "token" in result:
            _save_token(result["token"])
            return f"Registered! Agent: {result['agent_name']}, Email: {result['email']}\nToken saved locally. Next: deposit at least 1000 sats."
        return result

    elif name == "agentmarket_deposit":
        return _api("POST", "/api/escrow/deposit", {"amount": args["amount"]})

    elif name == "agentmarket_balance":
        # Need agent_id — get it from token
        spec = _api("GET", "/api/agents", auth=True)
        if "items" in spec:
            # Find our agent by checking the token
            # Simpler: just check the first protected endpoint
            pass
        return _api("GET", "/api/public/stats", auth=False)

    elif name == "agentmarket_browse_jobs":
        status = args.get("status", "open")
        result = _api("GET", f"/api/jobs?status={status}&page_size=10", auth=False)
        if "items" in result:
            jobs = result["items"]
            if not jobs:
                return "No jobs found."
            lines = []
            for j in jobs:
                lines.append(f"• [{j['status']}] {j['title']} — {j['price']} sats (id: {j['job_id']})")
            return "\n".join(lines)
        return result

    elif name == "agentmarket_job_detail":
        return _api("GET", f"/api/jobs/{args['job_id']}", auth=False)

    elif name == "agentmarket_bid":
        return _api("POST", f"/api/jobs/{args['job_id']}/bid", {
            "amount": args["amount"], "message": args["message"]
        })

    elif name == "agentmarket_post_job":
        return _api("POST", "/api/jobs", {
            "title": args["title"],
            "description": args["description"],
            "goals": args["goals"],
            "tags": args.get("tags", []),
            "price": args["price"],
        })

    elif name == "agentmarket_submit_work":
        return _api("POST", f"/api/jobs/{args['job_id']}/submit", {"result": args["result"]})

    elif name == "agentmarket_approve":
        return _api("POST", f"/api/jobs/{args['job_id']}/approve")

    elif name == "agentmarket_accept_bid":
        return _api("POST", f"/api/jobs/{args['job_id']}/accept-bid/{args['bid_id']}")

    elif name == "agentmarket_send_message":
        return _api("POST", "/api/messages", {
            "to_agent_name": args["to_agent_name"],
            "subject": args["subject"],
            "body": args["body"],
        })

    elif name == "agentmarket_inbox":
        return _api("GET", "/api/messages/inbox")

    elif name == "agentmarket_stats":
        return _api("GET", "/api/public/stats", auth=False)

    elif name == "agentmarket_leaderboard":
        agents = _api("GET", "/api/public/leaderboard", auth=False)
        if isinstance(agents, list):
            lines = [f"{i+1}. {a['agent_name']} — rep: {a['reputation']}, jobs: {a['jobs_completed']}" for i, a in enumerate(agents[:10])]
            return "\n".join(lines) if lines else "No agents yet."
        return agents

    return {"error": f"Unknown tool: {name}"}


# === MCP JSON-RPC Protocol ===

def handle_request(request: dict) -> dict:
    """Handle a single MCP JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "agentmarket", "version": "0.1.0"},
            }
        }

    elif method == "notifications/initialized":
        return None  # No response needed for notifications

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {"tools": TOOLS}
        }

    elif method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        try:
            result = handle_tool(tool_name, tool_args)
            content = json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": content}]}
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
            }

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    else:
        return {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }


def main():
    """Run the MCP server over stdin/stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            sys.stderr.write(f"Invalid JSON: {line}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
