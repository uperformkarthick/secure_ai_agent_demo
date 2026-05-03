# Bank AI Agent — Amazon Bedrock + MCP REST Server + MySQL

An **agentic AI system** that uses **Amazon Bedrock** (Claude 3 Sonnet) with a custom
**MCP (Model Context Protocol) REST server** to intelligently interact with a **MySQL** bank
database — answering queries, reviewing loan applications, and generating insights.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User / CLI                              │
└──────────────────────────────┬──────────────────────────────────┘
                               │
               ┌───────────────▼───────────────┐
               │    app  container             │
               │   ┌───────────────────────┐   │
               │   │   ui/cli.py           │   │
               │   └──────────┬────────────┘   │
               │              │                │
               │   ┌──────────▼────────────┐   │
               │   │   agent/agent.py      │   │
               │   │   Amazon Bedrock      │   │
               │   │   (Claude 3 Sonnet)   │   │
               └───┴──────────┬────────────┴───┘
                              │  HTTP  (REST / direct)
                              │
               ┌──────────────▼───────────────────┐   ┌──────────────────┐
               │   caddy  container  (optional)    │   │  Claude Desktop  │
               │   ports 80 / 443                  │◄──│  (SSE transport) │
               │   reverse_proxy → mcp-server:8000 │   └──────────────────┘
               └──────────────┬────────────────────┘
                              │
               ┌──────────────▼───────────────────┐
               │   mcp-server  container           │
               │   ┌────────────────────────────┐  │
               │   │   mcp_server/api.py        │  │
               │   │   GET  /tools              │  │
               │   │   POST /tools/call         │  │
               │   │   GET  /health             │  │
               │   │   GET  /sse  (SSE)         │  │
               │   │   POST /messages/          │  │
               │   └──────────────┬─────────────┘  │
               │                  │                 │
               │   ┌──────────────▼─────────────┐  │
               │   │   mcp_server/tools.py      │  │
               │   │   8 tool implementations   │  │
               └───┴──────────────┬─────────────┴──┘
                                  │  mysql-connector
               ┌──────────────────▼──────────────────┐
               │   mysql  container                  │
               │   customers │ loan_applications      │
               │   loan_products │ repayments          │
               │   ai_audit_log                       │
               └─────────────────────────────────────┘
```

### Docker services

| Service | Container | Exposes | Purpose |
|---|---|---|---|
| `mysql` | `bank_ai_mysql` | 3306 | MySQL 8.0 database |
| `mcp-server` | `bank_ai_mcp` | 8000 | MCP tools as a REST API + SSE transport |
| `caddy` | `bank_ai_caddy` | 80, 443 | Reverse proxy for HTTPS / Claude Desktop access |
| `app` | `bank_ai_agent` | — | Bedrock agent + terminal UI |

The agent connects to the MCP REST server via `MCP_SERVER_URL` (set automatically to `http://mcp-server:8000` inside Docker). The MCP server is also reachable on the host at `http://localhost:8000`. Caddy fronts the MCP server on ports 80/443 for local HTTPS and Claude Desktop integration.

---

## Project Structure

```
bank-ai-agent/
├── database/
│   └── schema.sql              # Schema + sample data (20 customers, 20 loans)
├── mcp_server/
│   ├── __init__.py
│   ├── api.py                  # FastAPI REST + SSE server (GET /tools, POST /tools/call, GET /sse)
│   ├── server.py               # Legacy stdio MCP server (not used in Docker)
│   ├── db.py                   # MySQL connection pool
│   └── tools.py                # 8 MCP tool implementations with guardrails
├── agent/
│   ├── __init__.py
│   ├── agent.py                # Bedrock agent — calls MCP server via httpx
│   └── prompts.py              # System prompt (loan officer persona + rules)
├── ui/
│   └── cli.py                  # Rich terminal REPL
├── Caddyfile                   # Caddy reverse-proxy config (ports 80/443 → mcp-server:8000)
├── Dockerfile                  # Agent + UI image
├── Dockerfile.mcp              # MCP REST server image
├── docker-compose.yml          # Orchestrates mysql + mcp-server + caddy + app
├── requirements.txt            # Agent dependencies (boto3, httpx, rich…)
├── requirements.mcp.txt        # MCP server dependencies (fastapi, uvicorn, mcp…)
└── .env.example                # Environment variable template
```

---

## Quick Start — Docker (recommended)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose v2)
- AWS account with **Amazon Bedrock** access and **Claude 3 Sonnet** enabled in your region

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values:

```
DB_PASSWORD=choose_a_strong_password
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
```

All other values have sensible defaults and do not need to change for Docker.

### 2. Build images

```bash
docker compose build
```

### 3. Start MySQL and the MCP REST server

```bash
docker compose up -d mysql mcp-server
```

MySQL will auto-load `database/schema.sql` (schema + 20 sample customers and loans) on first start. The MCP server waits for MySQL to pass its health check before starting.

### 4. Run the agent

```bash
docker compose run --rm app
```

This starts an interactive terminal session. The agent connects automatically to the MCP REST server at `http://mcp-server:8000`.

### Subsequent runs

Once `mysql` and `mcp-server` are already running, just repeat step 4:

```bash
docker compose run --rm app
```

### Optional: Start Caddy (HTTPS / Claude Desktop)

If you want HTTPS access or to connect Claude Desktop via SSE, also start the Caddy reverse proxy:

```bash
docker compose up -d caddy
```

Caddy will be available on `http://localhost` (port 80) and `https://localhost` (port 443), proxying all requests to the MCP server. See [Claude Desktop integration](#claude-desktop-integration) below.

### Stopping services

```bash
# Stop containers (keeps the database volume)
docker compose down

# Stop and delete the database volume (full reset)
docker compose down -v
```

### Inspecting the MCP REST API

The MCP server is available on your host while the container is running:

```bash
# List all available tools
curl http://localhost:8000/tools

# Call a tool directly
curl -s -X POST http://localhost:8000/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name": "get_portfolio_stats", "arguments": {}}' | jq .

# Health check
curl http://localhost:8000/health
```

---

## Quick Start — Local (without Docker)

### Prerequisites

- Python 3.11+
- MySQL 8.0+
- AWS credentials configured

### 1. Initialize the database

```bash
mysql -u root -p < database/schema.sql
```

### 2. Install dependencies

```bash
pip install -r requirements.txt        # Agent + UI
pip install -r requirements.mcp.txt   # MCP REST server
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — set DB credentials and AWS credentials
```

### 4. Start the MCP REST server

In a separate terminal:

```bash
uvicorn mcp_server.api:app --host 0.0.0.0 --port 8000
```

### 5. Run the agent

```bash
python -m ui.cli
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DB_HOST` | `localhost` | MySQL host (`mysql` in Docker) |
| `DB_PORT` | `3306` | MySQL port |
| `DB_USER` | `root` | MySQL user |
| `DB_PASSWORD` | — | MySQL password (required) |
| `DB_NAME` | `bank_ai_agent` | Database name |
| `AWS_REGION` | `us-east-1` | AWS region for Bedrock |
| `AWS_ACCESS_KEY_ID` | — | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | — | AWS secret key |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-sonnet-20240229-v1:0` | Bedrock model |
| `MAX_AGENT_ITERATIONS` | `10` | Agentic loop cap |
| `AGENT_TEMPERATURE` | `0.1` | Inference temperature |
| `MCP_SERVER_URL` | `http://localhost:8000` | MCP REST server URL (`http://mcp-server:8000` in Docker) |

---

## Example Agent Interactions

```
You: Show me all pending loan applications
Agent: [POST /tools/call → get_loan_applications(status="pending")]
       Found 2 pending applications...

You: What's the credit profile of customer CUST0013?
Agent: [POST /tools/call → get_customer_detail(customer_id="CUST0013")]
       Ethan Mueller — Credit Score: 820, Income: $195,000...

You: Approve loan LOAN-2024-0005 and add a note
Agent: [POST /tools/call → update_loan_status(...)]
       Loan LOAN-2024-0005 has been approved

You: Give me a portfolio risk summary
Agent: [POST /tools/call → get_portfolio_stats()]
       Total disbursed: $X | Avg credit score: Y | ...
```

---

## MCP REST API Reference

Base URL: `http://localhost:8000`

### `GET /health`

Liveness probe — returns `{"status": "ok"}`.

### `GET /tools`

Returns the list of all available tools with their names, descriptions, and input schemas.

### `POST /tools/call`

Invoke a tool by name.

**Request body:**
```json
{
  "name": "get_customers",
  "arguments": {
    "min_credit_score": 700,
    "kyc_verified": true
  }
}
```

**Response:**
```json
{
  "content": [
    { "type": "text", "text": "[ { \"customer_id\": ... } ]" }
  ]
}
```

### `GET /sse` and `POST /messages/`

MCP SSE transport endpoints used by **Claude Desktop** and other MCP-compatible clients. Connect Claude Desktop to this server by pointing it at `http://localhost/sse` (via Caddy) or `http://localhost:8000/sse` (direct).

---

## Claude Desktop Integration

The MCP server speaks the native MCP SSE protocol, so you can connect Claude Desktop directly to it without the Bedrock agent layer.

1. Start the MCP server (and optionally Caddy for HTTPS):
   ```bash
   docker compose up -d mysql mcp-server caddy
   ```

2. Add the following to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):
   ```json
   {
     "mcpServers": {
       "bank-ai-agent": {
         "url": "http://localhost/sse"
       }
     }
   }
   ```

3. Restart Claude Desktop — the 8 bank tools will appear in the tools panel.

---

## MCP Tools

| Tool | Description |
|---|---|
| `get_customers` | Search/filter customers by name, email, credit score, KYC status |
| `get_customer_detail` | Full profile + loan history for one customer |
| `get_loan_applications` | List loans filtered by status, type, amount, customer |
| `get_loan_detail` | Full details + repayment schedule for one loan |
| `update_loan_status` | Approve / reject / disburse / close a loan — enforces valid state transitions and hard business rules (see below) |
| `get_portfolio_stats` | Aggregate KPIs: totals, breakdown by type, repayment health |
| `execute_query` | Safe read-only `SELECT` queries against whitelisted tables (200-row cap) |
| `log_ai_action` | Write an audit trail entry for agent decisions |

### Business rules enforced by `update_loan_status`

The server enforces these rules regardless of what the AI agent requests:

**Valid status transitions:**

```
pending → under_review → approved / rejected
                           ↓
                        disbursed → closed
```

Attempting an out-of-order transition (e.g. `pending → approved`) returns an error.

**Hard approval guardrails:**
- Credit score must be ≥ 600; lower scores are blocked from approval
- Customer KYC must be verified before approval is allowed

These checks run server-side so they cannot be bypassed through the agent.

---

## OAuth Authentication (optional)

OAuth is **disabled by default** (`ENABLE_AUTH=false`). All MCP endpoints are open, which is fine for local Docker-only setups. Enable it when the server is exposed externally or when you need token-based access control.

### How it works

The server implements **OAuth 2.0 Client Credentials** (machine-to-machine). Clients exchange a `client_id` + `client_secret` for a short-lived HS256 JWT, then pass it as a `Bearer` token on every request. The `/.well-known/oauth-authorization-server` discovery endpoint is always available so compatible clients (e.g. `mcp-remote`) can auto-discover the token endpoint.

### Enable OAuth

1. **Generate secrets:**
   ```bash
   openssl rand -hex 32   # use for OAUTH_CLIENT_SECRET
   openssl rand -hex 32   # use for OAUTH_JWT_SECRET
   ```

2. **Add to `.env`:**
   ```
   ENABLE_AUTH=true
   OAUTH_CLIENT_ID=bank-ai-agent-client
   OAUTH_CLIENT_SECRET=<your-secret>
   OAUTH_JWT_SECRET=<your-jwt-secret>
   OAUTH_TOKEN_EXPIRY=3600
   ```

3. **Restart the MCP server:**
   ```bash
   docker compose up -d mcp-server
   ```

### Get a token

```bash
curl -s -X POST http://localhost:8000/token \
  -d "grant_type=client_credentials&client_id=bank-ai-agent-client&client_secret=<your-secret>"
# → {"access_token": "eyJ...", "token_type": "Bearer", "expires_in": 3600}
```

### Call protected endpoints

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/tools
```

### Claude Desktop with auth enabled

Pass the token via `mcp-remote`'s `--header` flag in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "bank-ai-agent": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8000/sse",
               "--header", "Authorization:Bearer <token>"]
    }
  }
}
```

### OAuth endpoints

| Endpoint | Auth required | Description |
|---|---|---|
| `GET /.well-known/oauth-authorization-server` | No | OAuth 2.0 discovery metadata |
| `POST /token` | No | Issue a JWT (client credentials grant) |
| `GET /health` | No | Liveness probe |
| `GET /tools` | Yes (when enabled) | List available tools |
| `POST /tools/call` | Yes (when enabled) | Invoke a tool |
| `GET /sse` | Yes (when enabled) | SSE transport for Claude Desktop |

---

## AWS & Amazon Bedrock Setup

### 1. Create an AWS account

If you don't have one, sign up at [https://aws.amazon.com](https://aws.amazon.com). A free-tier account is sufficient to get started — Bedrock charges are per token.

---

### 2. Create an IAM user with Bedrock permissions

> **Recommended:** use an IAM user with only the permissions this project needs, not your root account credentials.

1. Go to **IAM** → **Users** → **Create user**.
2. Give it a name (e.g. `bank-ai-agent`), select **Programmatic access**.
3. On the permissions step, choose **Attach policies directly** and create a new inline policy with this JSON:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockInvoke",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0"
    }
  ]
}
```

4. Complete the user creation and download (or copy) the **Access key ID** and **Secret access key**. These are the values you'll enter for `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

> If you prefer to use an **IAM role** (e.g. on EC2 or ECS), attach the same policy to the role — the SDK picks up the role credentials automatically and no key/secret are needed in `.env`.

---

### 3. Supply credentials to the application

**Option A — environment setup script (recommended)**

```bash
./setup.sh
```

The script prompts for all values, hides sensitive input, and writes `.env` with `chmod 600`.

**Option B — manual**

```bash
cp .env.example .env
# Fill in AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
```

**Option C — AWS credentials file**

If you have the AWS CLI installed and already ran `aws configure`, the SDK reads `~/.aws/credentials` automatically. Leave `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` blank in `.env` and set your profile name:

```bash
# In .env
AWS_PROFILE=default
```

---

### Summary

| What | Where |
|---|---|
| IAM permission needed | `bedrock:InvokeModel` on the Sonnet model ARN |
| Credentials in project | `.env` or `~/.aws/credentials` or IAM role |
| Supported regions | `us-east-1`, `us-west-2`, `eu-central-1`, `ap-southeast-1`, and others |
