"""
mcp_server/api.py
FastAPI REST server that exposes the bank MCP tools over HTTP.

Endpoints:
  GET  /health      — liveness probe
  GET  /tools       — list all available tools with their schemas
  POST /tools/call  — invoke a tool by name with arguments
  GET  /sse         — MCP SSE transport (Claude Desktop)
  POST /messages/   — MCP SSE message handler (Claude Desktop)
"""
import logging
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mcp.server import Server as MCPServer
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from pydantic import BaseModel
from starlette.requests import Request

from . import tools as T
from .auth import (
    ENABLE_AUTH,
    TOKEN_EXPIRY,
    create_access_token,
    validate_token,
    verify_client,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [MCP-API] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Bank AI MCP REST Server", version="1.0.0")

# ── Auth ──────────────────────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


def require_auth(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)):
    if not ENABLE_AUTH:
        return
    if credentials is None or not validate_token(credentials.credentials):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "get_customers",
        "description": (
            "Search and list bank customers. "
            "Filter by name/email, employment status, credit score range, or KYC status."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "search":            {"type": "string",  "description": "Name, email or customer_id search term"},
                "employment_status": {"type": "string",  "enum": ["employed", "self_employed", "unemployed", "retired"]},
                "min_credit_score":  {"type": "integer", "description": "Minimum credit score filter"},
                "max_credit_score":  {"type": "integer", "description": "Maximum credit score filter"},
                "kyc_verified":      {"type": "boolean", "description": "Filter by KYC verification status"},
                "limit":             {"type": "integer", "default": 20, "description": "Max rows to return"},
            },
        },
    },
    {
        "name": "get_customer_detail",
        "description": "Get full profile and complete loan history for a specific customer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer ID e.g. CUST0001"},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_loan_applications",
        "description": (
            "List loan applications with optional filters. "
            "Filter by status, loan type, customer, or amount range."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "status":      {"type": "string", "enum": ["pending", "under_review", "approved", "rejected", "disbursed", "closed"]},
                "loan_type":   {"type": "string", "enum": ["personal", "home", "auto", "business", "education"]},
                "customer_id": {"type": "string"},
                "min_amount":  {"type": "number"},
                "max_amount":  {"type": "number"},
                "limit":       {"type": "integer", "default": 25},
            },
        },
    },
    {
        "name": "get_loan_detail",
        "description": "Get full details and repayment schedule for a single loan application.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "string", "description": "Loan application ID e.g. LOAN-2024-0001"},
            },
            "required": ["application_id"],
        },
    },
    {
        "name": "update_loan_status",
        "description": (
            "Update the status of a loan application. "
            "Can approve (with amount & rate), reject (with reason), move to disbursed, etc."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "application_id":   {"type": "string"},
                "new_status":       {"type": "string", "enum": ["pending", "under_review", "approved", "rejected", "disbursed", "closed"]},
                "approved_amount":  {"type": "number",  "description": "Set approved amount (for approvals)"},
                "interest_rate":    {"type": "number",  "description": "Set interest rate (for approvals)"},
                "agent_notes":      {"type": "string",  "description": "Internal notes from the agent"},
                "rejection_reason": {"type": "string",  "description": "Reason for rejection"},
            },
            "required": ["application_id", "new_status"],
        },
    },
    {
        "name": "get_portfolio_stats",
        "description": (
            "Get aggregate portfolio statistics: total applications by status, "
            "breakdown by loan type, and repayment health metrics."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "execute_query",
        "description": (
            "Run a custom read-only SELECT query against the database. "
            "Tables: customers, loan_applications, loan_products, loan_repayments, ai_audit_log. "
            "Views: v_loan_summary, v_portfolio_stats. "
            "Only SELECT is permitted."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SQL SELECT statement to execute"},
            },
            "required": ["sql"],
        },
    },
    {
        "name": "log_ai_action",
        "description": "Write an audit log entry recording what the AI agent did and why.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id":   {"type": "string"},
                "action_type":  {"type": "string", "description": "e.g. LOAN_APPROVAL, CUSTOMER_LOOKUP"},
                "entity_type":  {"type": "string", "description": "e.g. loan_application, customer"},
                "entity_id":    {"type": "string"},
                "tool_name":    {"type": "string"},
                "tool_input":   {"type": "object"},
                "tool_output":  {"type": "string"},
                "ai_reasoning": {"type": "string", "description": "Agent's reasoning for this action"},
            },
            "required": ["session_id", "action_type", "entity_type", "entity_id", "tool_name", "tool_input", "tool_output"],
        },
    },
]

TOOL_MAP = {
    "get_customers":         lambda a: T.get_customers(**a),
    "get_customer_detail":   lambda a: T.get_customer_detail(**a),
    "get_loan_applications": lambda a: T.get_loan_applications(**a),
    "get_loan_detail":       lambda a: T.get_loan_detail(**a),
    "update_loan_status":    lambda a: T.update_loan_status(**a),
    "get_portfolio_stats":   lambda a: T.get_portfolio_stats(),
    "execute_query":         lambda a: T.execute_query(**a),
    "log_ai_action":         lambda a: T.log_ai_action(**a),
}


# ── MCP SSE server (Claude Desktop) ──────────────────────────────────────────

_mcp = MCPServer("bank-ai-mcp-server")


@_mcp.list_tools()
async def _list_mcp_tools():
    return [
        Tool(name=t["name"], description=t.get("description", ""), inputSchema=t["inputSchema"])
        for t in TOOLS
    ]


@_mcp.call_tool()
async def _call_mcp_tool(name: str, arguments: dict):
    fn = TOOL_MAP.get(name)
    if fn is None:
        return [TextContent(type="text", text=f'{{"error": "Unknown tool: {name}"}}')]
    try:
        result = fn(arguments)
    except Exception as exc:
        log.exception("MCP tool %s raised an exception", name)
        result = f'{{"error": "{exc}"}}'
    return [TextContent(type="text", text=result)]


_sse = SseServerTransport("/messages/")


@app.get("/sse", dependencies=[Depends(require_auth)])
async def sse_endpoint(request: Request):
    async with _sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await _mcp.run(streams[0], streams[1], _mcp.create_initialization_options())


@app.post("/messages/")
async def messages_endpoint(request: Request):
    await _sse.handle_post_message(request.scope, request.receive, request._send)


# ── Request / Response models ─────────────────────────────────────────────────

class ToolCallRequest(BaseModel):
    name: str
    arguments: dict = {}


class ToolCallResponse(BaseModel):
    content: list[dict]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/.well-known/oauth-authorization-server")
def oauth_metadata(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "issuer": base,
        "token_endpoint": f"{base}/token",
        "grant_types_supported": ["client_credentials"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "response_types_supported": ["token"],
    }


@app.post("/token")
def token_endpoint(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
):
    if grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail="Only client_credentials grant type is supported")
    if not verify_client(client_id, client_secret):
        raise HTTPException(status_code=401, detail="Invalid client credentials")
    log.info("Token issued for client_id=%s", client_id)
    return {
        "access_token": create_access_token(),
        "token_type": "Bearer",
        "expires_in": TOKEN_EXPIRY,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/tools", dependencies=[Depends(require_auth)])
def list_tools():
    return {"tools": TOOLS}


@app.post("/tools/call", response_model=ToolCallResponse, dependencies=[Depends(require_auth)])
def call_tool(req: ToolCallRequest):
    log.info("Tool called: %s  args=%s", req.name, str(req.arguments)[:200])
    fn = TOOL_MAP.get(req.name)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {req.name}")
    try:
        result = fn(req.arguments)
    except Exception as exc:
        log.exception("Tool %s raised an exception", req.name)
        raise HTTPException(status_code=500, detail=str(exc))
    return ToolCallResponse(content=[{"type": "text", "text": result}])
