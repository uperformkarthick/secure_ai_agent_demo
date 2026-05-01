"""
mcp_server/api.py
FastAPI REST server that exposes the bank MCP tools over HTTP.

Endpoints:
  GET  /health      — liveness probe
  GET  /tools       — list all available tools with their schemas
  POST /tools/call  — invoke a tool by name with arguments
"""
import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import tools as T

logging.basicConfig(level=logging.INFO, format="%(asctime)s [MCP-API] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Bank AI MCP REST Server", version="1.0.0")

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


# ── Request / Response models ─────────────────────────────────────────────────

class ToolCallRequest(BaseModel):
    name: str
    arguments: dict = {}


class ToolCallResponse(BaseModel):
    content: list[dict]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/tools")
def list_tools():
    return {"tools": TOOLS}


@app.post("/tools/call", response_model=ToolCallResponse)
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
