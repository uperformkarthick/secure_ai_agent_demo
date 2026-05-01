"""
mcp_server/server.py
MCP server — exposes bank tools via stdio transport.
Start with:  python -m mcp_server.server
The Bedrock agent launches this as a subprocess and communicates
over stdin / stdout using the MCP protocol.
"""
import asyncio
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from . import tools as T

logging.basicConfig(level=logging.INFO, format="%(asctime)s [MCP] %(message)s")
log = logging.getLogger(__name__)

app = Server("bank-ai-mcp-server")

# ── Tool registry ─────────────────────────────────────────────────────────────

TOOLS: list[Tool] = [
    Tool(
        name="get_customers",
        description=(
            "Search and list bank customers. "
            "Filter by name/email, employment status, credit score range, or KYC status."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "search":            {"type": "string",  "description": "Name, email or customer_id search term"},
                "employment_status": {"type": "string",  "enum": ["employed","self_employed","unemployed","retired"]},
                "min_credit_score":  {"type": "integer", "description": "Minimum credit score filter"},
                "max_credit_score":  {"type": "integer", "description": "Maximum credit score filter"},
                "kyc_verified":      {"type": "boolean", "description": "Filter by KYC verification status"},
                "limit":             {"type": "integer", "default": 20, "description": "Max rows to return"},
            },
        },
    ),
    Tool(
        name="get_customer_detail",
        description="Get full profile and complete loan history for a specific customer.",
        inputSchema={
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer ID e.g. CUST0001"},
            },
            "required": ["customer_id"],
        },
    ),
    Tool(
        name="get_loan_applications",
        description=(
            "List loan applications with optional filters. "
            "Filter by status, loan type, customer, or amount range."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "status":      {"type": "string", "enum": ["pending","under_review","approved","rejected","disbursed","closed"]},
                "loan_type":   {"type": "string", "enum": ["personal","home","auto","business","education"]},
                "customer_id": {"type": "string"},
                "min_amount":  {"type": "number"},
                "max_amount":  {"type": "number"},
                "limit":       {"type": "integer", "default": 25},
            },
        },
    ),
    Tool(
        name="get_loan_detail",
        description="Get full details and repayment schedule for a single loan application.",
        inputSchema={
            "type": "object",
            "properties": {
                "application_id": {"type": "string", "description": "Loan application ID e.g. LOAN-2024-0001"},
            },
            "required": ["application_id"],
        },
    ),
    Tool(
        name="update_loan_status",
        description=(
            "Update the status of a loan application. "
            "Can approve (with amount & rate), reject (with reason), move to disbursed, etc."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "application_id":  {"type": "string"},
                "new_status":      {"type": "string", "enum": ["pending","under_review","approved","rejected","disbursed","closed"]},
                "approved_amount": {"type": "number",  "description": "Set approved amount (for approvals)"},
                "interest_rate":   {"type": "number",  "description": "Set interest rate (for approvals)"},
                "agent_notes":     {"type": "string",  "description": "Internal notes from the agent"},
                "rejection_reason":{"type": "string",  "description": "Reason for rejection"},
            },
            "required": ["application_id", "new_status"],
        },
    ),
    Tool(
        name="get_portfolio_stats",
        description=(
            "Get aggregate portfolio statistics: total applications by status, "
            "breakdown by loan type, and repayment health metrics."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="execute_query",
        description=(
            "Run a custom read-only SELECT query against the database. "
            "Tables: customers, loan_applications, loan_products, loan_repayments, ai_audit_log. "
            "Views: v_loan_summary, v_portfolio_stats. "
            "Only SELECT is permitted."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SQL SELECT statement to execute"},
            },
            "required": ["sql"],
        },
    ),
    Tool(
        name="log_ai_action",
        description="Write an audit log entry recording what the AI agent did and why.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id":    {"type": "string"},
                "action_type":   {"type": "string", "description": "e.g. LOAN_APPROVAL, CUSTOMER_LOOKUP"},
                "entity_type":   {"type": "string", "description": "e.g. loan_application, customer"},
                "entity_id":     {"type": "string"},
                "tool_name":     {"type": "string"},
                "tool_input":    {"type": "object"},
                "tool_output":   {"type": "string"},
                "ai_reasoning":  {"type": "string", "description": "Agent's reasoning for this action"},
            },
            "required": ["session_id","action_type","entity_type","entity_id","tool_name","tool_input","tool_output"],
        },
    ),
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

# ── Handlers ──────────────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools():
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    log.info("Tool called: %s  args=%s", name, arguments)
    fn = TOOL_MAP.get(name)
    if fn is None:
        result = f'{{"error": "Unknown tool: {name}"}}'
    else:
        try:
            result = fn(arguments)
        except Exception as exc:
            log.exception("Tool %s raised an exception", name)
            result = f'{{"error": "{exc}"}}'
    return [TextContent(type="text", text=result)]


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    log.info("Bank AI MCP server starting (stdio transport)…")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
