# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & Running

### Docker (recommended)

```bash
cp .env.example .env
# Edit .env — set DB_PASSWORD, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION

# First run: builds all images and starts MySQL + MCP server + agent
docker compose up -d mysql mcp-server
docker compose run --rm app

# Optional: start Caddy reverse proxy (HTTPS / Claude Desktop SSE)
docker compose up -d caddy

# Subsequent runs
docker compose run --rm app

# Tear down (keeps DB volume)
docker compose down

# Tear down including database volume
docker compose down -v
```

`DB_HOST` is overridden to `mysql` and `MCP_SERVER_URL` is set to `http://mcp-server:8000` by `docker-compose.yml`; no need to change these in `.env`.

The MCP REST server is also accessible on the host at `http://localhost:8000` (useful for local development or testing with tools like curl/Postman).

### Local (without Docker)

```bash
# 1. Initialize database (MySQL 8.0+ required)
mysql -u root -p < database/schema.sql

# 2. Install dependencies
pip install -r requirements.txt        # agent + UI
pip install -r requirements.mcp.txt   # MCP REST server

# 3. Configure environment
cp .env.example .env
# Edit .env with DB credentials and AWS credentials

# 4. Start the MCP REST server (in a separate terminal)
uvicorn mcp_server.api:app --host 0.0.0.0 --port 8000

# 5. Run the application
python -m ui.cli
```

## Environment Variables

Key variables in `.env`:
- `DB_HOST/PORT/USER/PASSWORD/DB_NAME` — MySQL connection (default DB: `bank_ai_agent`)
- `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` — Bedrock access
- `BEDROCK_MODEL_ID` — defaults to `anthropic.claude-3-sonnet-20240229-v1:0`
- `MAX_AGENT_ITERATIONS` — agentic loop cap (default: 10)
- `AGENT_TEMPERATURE` — Bedrock inference temperature (default: 0.1)
- `MCP_SERVER_URL` — URL of the MCP REST server (default: `http://localhost:8000`; Docker sets `http://mcp-server:8000`)
- `ENABLE_AUTH` — set `true` to enable OAuth 2.0 Bearer token enforcement on all MCP endpoints (default: `false`)
- `OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` — credentials used to obtain a token via `POST /token`
- `OAUTH_JWT_SECRET` — secret used to sign/verify JWTs (generate: `openssl rand -hex 32`)
- `OAUTH_TOKEN_EXPIRY` — token lifetime in seconds (default: `3600`)

## Architecture

```
ui/cli.py  →  agent/agent.py  ──HTTP──►  mcp_server/api.py  →  mcp_server/tools.py  →  mcp_server/db.py  →  MySQL
                                                  ▲
                                          (optional) caddy  ←  Claude Desktop (SSE)
```

The MCP server runs as a **separate Docker container** exposing a REST API on port 8000. The agent communicates with it over HTTP using `httpx`. An optional Caddy container (ports 80/443) reverse-proxies the MCP server for HTTPS and Claude Desktop SSE access.

**Entry point:** `ui/cli.py` — Rich terminal REPL with built-in commands (`/help`, `/reset`, `/stats`, `/pending`, `/quit`).

**Agent (`agent/agent.py`):** `BankAgent` is an async context manager. On `__aenter__`, it creates an `httpx.AsyncClient` and fetches tool definitions from `GET /tools`, converting them to Bedrock `toolSpec` format. `chat()` runs the agentic loop (up to `MAX_AGENT_ITERATIONS`): appends user message → calls `bedrock.converse()` → parses text/`toolUse` blocks → executes tools via `POST /tools/call` → feeds `toolResult` blocks back → repeats until `stop_reason == "end_turn"`.

**MCP REST Server (`mcp_server/api.py`):** FastAPI app running in its own container. Exposes `GET /health`, `GET /tools`, `POST /tools/call`, `GET /sse` (SSE transport for Claude Desktop), `POST /messages/`, `POST /token` (OAuth), and `GET /.well-known/oauth-authorization-server`. Dispatches tool calls via `TOOL_MAP` to implementations in `tools.py`.

**Auth (`mcp_server/auth.py`):** OAuth 2.0 Client Credentials with HS256 JWT. Toggled by `ENABLE_AUTH` env var. When disabled (default), the `require_auth` FastAPI dependency is a no-op.

**Legacy stdio server (`mcp_server/server.py`):** Retained for reference; not used in Docker deployment.

**Tools (`mcp_server/tools.py`):** 8 tools — `get_customers`, `get_customer_detail`, `get_loan_applications`, `get_loan_detail`, `update_loan_status`, `get_portfolio_stats`, `execute_query`, `log_ai_action`. All return JSON strings with a custom serializer for `Decimal`/`datetime`/`date`. `execute_query` is restricted to SELECT statements and a whitelist of tables/views (200-row cap). `update_loan_status` enforces valid state transitions and hard approval guardrails (credit score ≥ 600, KYC verified).

**Database (`mcp_server/db.py`):** MySQLConnectionPool (5 connections, autocommit). `query()` returns list of dicts; `execute()` returns affected row count. All SQL uses parameterized `%s` placeholders.

**System Prompt (`agent/prompts.py`):** Defines loan officer persona and decision rules (e.g., auto-approve if credit_score ≥ 750 + KYC verified + DTI < 40%; auto-reject if credit_score < 600 or DTI > 60%).

## Database Schema

Tables: `customers`, `loan_products` (5 types), `loan_applications`, `loan_repayments`, `ai_audit_log`.
Views: `v_loan_summary` (enriched loan + customer + product), `v_portfolio_stats` (aggregate KPIs).

Loan status flow: `pending` → `under_review` → `approved`/`rejected` → `disbursed` → `closed`.

The schema includes 20 sample customers and 20 loan applications for immediate testing.

## Key Design Patterns

- **Auto-audit:** `update_loan_status` calls automatically trigger `log_ai_action` for audit trail.
- **MCP over REST:** The agent calls the MCP server via `httpx` HTTP requests (`GET /tools`, `POST /tools/call`); the server runs as an isolated Docker container.
- **Dual transport:** The MCP server serves both REST (for the Bedrock agent) and SSE (`GET /sse`) for Claude Desktop via `mcp-remote`.
- **Streaming UI:** `chat()` accepts an `on_token` callback for progressive terminal output.
- **Tool results as "user" turns:** Bedrock's converse API requires tool results wrapped in a `user` role message with `toolResult` content blocks.
- **Toggleable auth:** `ENABLE_AUTH=true` enforces OAuth 2.0 Client Credentials on all tool endpoints; `false` (default) lets the `require_auth` dependency short-circuit with zero overhead.
- **Server-side guardrails:** Business rules in `update_loan_status` (valid transitions, credit score floor, KYC check) run in `tools.py` and cannot be bypassed by the agent.

## Claude Desktop Integration

Connect Claude Desktop to the MCP server using `mcp-remote` as a stdio↔SSE bridge:

```json
// ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "bank-ai-agent": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8000/sse"]
    }
  }
}
```

Make sure `mysql` and `mcp-server` containers are running before starting Claude Desktop.
