"""
mcp_server/tools.py
All MCP tool implementations — called by the MCP server
and invoked by the Bedrock agent via tool_use.
"""
import json
from datetime import datetime
from decimal import Decimal

from .db import query, execute


# ── helpers ──────────────────────────────────────────────────────────────────

def _serial(obj):
    """JSON-serialise MySQL types (Decimal, datetime, date)."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    raise TypeError(f"Not serialisable: {type(obj)}")


def to_json(data) -> str:
    return json.dumps(data, default=_serial, indent=2)


# ── tools ─────────────────────────────────────────────────────────────────────

def get_customers(
    search: str | None = None,
    employment_status: str | None = None,
    min_credit_score: int | None = None,
    max_credit_score: int | None = None,
    kyc_verified: bool | None = None,
    limit: int = 20,
) -> str:
    """
    List customers with optional filters.
    Returns JSON array of customer records.
    """
    conditions, params = [], []

    if search:
        conditions.append(
            "(first_name LIKE %s OR last_name LIKE %s OR email LIKE %s OR customer_id = %s)"
        )
        like = f"%{search}%"
        params += [like, like, like, search]
    if employment_status:
        conditions.append("employment_status = %s")
        params.append(employment_status)
    if min_credit_score is not None:
        conditions.append("credit_score >= %s")
        params.append(min_credit_score)
    if max_credit_score is not None:
        conditions.append("credit_score <= %s")
        params.append(max_credit_score)
    if kyc_verified is not None:
        conditions.append("kyc_verified = %s")
        params.append(int(kyc_verified))

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"""
        SELECT customer_id, first_name, last_name, email, phone,
               credit_score, annual_income, employment_status,
               account_type, account_balance, member_since, kyc_verified
        FROM customers {where}
        ORDER BY customer_id
        LIMIT %s
    """
    params.append(limit)
    rows = query(sql, tuple(params))
    return to_json({"count": len(rows), "customers": rows})


def get_customer_detail(customer_id: str) -> str:
    """
    Full profile for a single customer including their loan history.
    """
    rows = query("SELECT * FROM customers WHERE customer_id = %s", (customer_id,))
    if not rows:
        return to_json({"error": f"Customer {customer_id} not found"})

    customer = rows[0]
    loans = query(
        """
        SELECT la.application_id, lp.product_name, lp.loan_type,
               la.requested_amount, la.approved_amount,
               la.tenure_months, la.interest_rate, la.emi_amount,
               la.status, la.applied_at
        FROM   loan_applications la
        JOIN   loan_products lp ON la.product_code = lp.product_code
        WHERE  la.customer_id = %s
        ORDER  BY la.applied_at DESC
        """,
        (customer_id,),
    )
    customer["loan_history"] = loans
    return to_json(customer)


def get_loan_applications(
    status: str | None = None,
    loan_type: str | None = None,
    customer_id: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    limit: int = 25,
) -> str:
    """
    List loan applications with optional filters.
    Returns enriched rows from v_loan_summary.
    """
    conditions, params = [], []

    if status:
        conditions.append("la.status = %s")
        params.append(status)
    if loan_type:
        conditions.append("lp.loan_type = %s")
        params.append(loan_type)
    if customer_id:
        conditions.append("la.customer_id = %s")
        params.append(customer_id)
    if min_amount is not None:
        conditions.append("la.requested_amount >= %s")
        params.append(min_amount)
    if max_amount is not None:
        conditions.append("la.requested_amount <= %s")
        params.append(max_amount)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"""
        SELECT la.application_id, la.customer_id,
               CONCAT(c.first_name,' ',c.last_name) AS customer_name,
               lp.product_name, lp.loan_type,
               la.requested_amount, la.approved_amount,
               la.tenure_months, la.interest_rate, la.emi_amount,
               la.status, la.applied_at, la.reviewed_at,
               c.credit_score, c.employment_status
        FROM   loan_applications la
        JOIN   customers c     ON la.customer_id  = c.customer_id
        JOIN   loan_products lp ON la.product_code = lp.product_code
        {where}
        ORDER  BY la.applied_at DESC
        LIMIT  %s
    """
    params.append(limit)
    rows = query(sql, tuple(params))
    return to_json({"count": len(rows), "applications": rows})


def get_loan_detail(application_id: str) -> str:
    """
    Full detail for a single loan application including repayment schedule.
    """
    rows = query(
        """
        SELECT la.*, lp.product_name, lp.loan_type, lp.base_interest_rate,
               lp.processing_fee_pct,
               CONCAT(c.first_name,' ',c.last_name) AS customer_name,
               c.credit_score, c.annual_income, c.employment_status, c.kyc_verified
        FROM   loan_applications la
        JOIN   customers c     ON la.customer_id  = c.customer_id
        JOIN   loan_products lp ON la.product_code = lp.product_code
        WHERE  la.application_id = %s
        """,
        (application_id,),
    )
    if not rows:
        return to_json({"error": f"Application {application_id} not found"})

    loan = rows[0]
    repayments = query(
        """
        SELECT emi_number, due_date, paid_date,
               emi_amount, paid_amount, principal_component,
               interest_component, status
        FROM   loan_repayments
        WHERE  application_id = %s
        ORDER  BY emi_number
        """,
        (application_id,),
    )
    loan["repayment_schedule"] = repayments
    return to_json(loan)


def update_loan_status(
    application_id: str,
    new_status: str,
    approved_amount: float | None = None,
    interest_rate: float | None = None,
    agent_notes: str | None = None,
    rejection_reason: str | None = None,
) -> str:
    """
    Update a loan application's status.
    Valid transitions: pending→under_review, under_review→approved/rejected,
                       approved→disbursed, disbursed→closed
    """
    valid_statuses = ("pending", "under_review", "approved", "rejected", "disbursed", "closed")
    if new_status not in valid_statuses:
        return to_json({"error": f"Invalid status '{new_status}'. Must be one of {valid_statuses}"})

    # Build SET clause dynamically
    set_parts = ["status = %s"]
    params: list = [new_status]

    if new_status in ("approved", "disbursed", "under_review"):
        set_parts.append("reviewed_at = NOW()")
    if new_status == "disbursed":
        set_parts.append("disbursed_at = NOW()")
    if approved_amount is not None:
        set_parts.append("approved_amount = %s")
        params.append(approved_amount)
    if interest_rate is not None:
        set_parts.append("interest_rate = %s")
        params.append(interest_rate)
    if agent_notes:
        set_parts.append("agent_notes = %s")
        params.append(agent_notes)
    if rejection_reason:
        set_parts.append("rejection_reason = %s")
        params.append(rejection_reason)

    params.append(application_id)
    sql = f"UPDATE loan_applications SET {', '.join(set_parts)} WHERE application_id = %s"
    affected = execute(sql, tuple(params))

    if affected == 0:
        return to_json({"error": f"Application {application_id} not found"})
    return to_json({
        "success": True,
        "application_id": application_id,
        "new_status": new_status,
        "message": f"Loan {application_id} updated to '{new_status}' successfully.",
    })


def get_portfolio_stats() -> str:
    """
    Aggregate statistics across the entire loan portfolio.
    """
    summary = query("SELECT * FROM v_portfolio_stats")[0]

    by_type = query(
        """
        SELECT lp.loan_type,
               COUNT(*)                  AS applications,
               SUM(la.status='disbursed') AS disbursed,
               SUM(la.status='rejected')  AS rejected,
               SUM(IFNULL(la.approved_amount,0)) AS total_approved,
               ROUND(AVG(c.credit_score),1)      AS avg_credit_score
        FROM   loan_applications la
        JOIN   loan_products lp ON la.product_code = lp.product_code
        JOIN   customers c      ON la.customer_id  = c.customer_id
        GROUP  BY lp.loan_type
        ORDER  BY applications DESC
        """
    )

    repayment_health = query(
        """
        SELECT
            SUM(status='paid')    AS paid_emis,
            SUM(status='pending') AS pending_emis,
            SUM(status='overdue') AS overdue_emis,
            ROUND(SUM(paid_amount),2) AS total_collected,
            ROUND(SUM(emi_amount - paid_amount),2) AS total_outstanding
        FROM loan_repayments
        """
    )[0]

    return to_json({
        "portfolio_summary": summary,
        "breakdown_by_loan_type": by_type,
        "repayment_health": repayment_health,
    })


def execute_query(sql: str) -> str:
    """
    Execute a read-only SELECT query against the database.
    Only SELECT statements are permitted.
    """
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return to_json({"error": "Only SELECT queries are allowed for security reasons."})

    # Rough safety check — block destructive keywords
    blocked = ("DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "GRANT", "REVOKE")
    for kw in blocked:
        if kw in stripped:
            return to_json({"error": f"Keyword '{kw}' is not permitted in ad-hoc queries."})

    try:
        rows = query(sql)
        return to_json({"count": len(rows), "rows": rows})
    except Exception as exc:
        return to_json({"error": str(exc)})


def log_ai_action(
    session_id: str,
    action_type: str,
    entity_type: str,
    entity_id: str,
    tool_name: str,
    tool_input: dict,
    tool_output: str,
    ai_reasoning: str | None = None,
) -> str:
    """
    Write an entry to the AI audit log.
    """
    execute(
        """
        INSERT INTO ai_audit_log
            (session_id, action_type, entity_type, entity_id,
             tool_name, tool_input, tool_output, ai_reasoning)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            session_id,
            action_type,
            entity_type,
            entity_id,
            tool_name,
            json.dumps(tool_input),
            tool_output[:4000],          # cap long outputs
            ai_reasoning,
        ),
    )
    return to_json({"logged": True, "session_id": session_id})
