#!/usr/bin/env bash
# setup.sh — interactive prompt to configure the Bank AI Agent environment.
# Writes all answers to .env in the current directory.

set -euo pipefail

ENV_FILE=".env"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

print_header() {
    echo ""
    echo -e "${BOLD}╔══════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║       Bank AI Agent — Environment Setup  ║${RESET}"
    echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"
    echo ""
}

ask() {
    # ask <VAR_NAME> <prompt> <default>
    local var="$1"
    local prompt="$2"
    local default="$3"

    if [[ -n "$default" ]]; then
        read -rp "  $prompt [${default}]: " value
        value="${value:-$default}"
    else
        read -rp "  $prompt (required): " value
        while [[ -z "$value" ]]; do
            echo -e "  ${RED}This field is required.${RESET}"
            read -rp "  $prompt (required): " value
        done
    fi

    printf -v "$var" '%s' "$value"
}

ask_secret() {
    # ask_secret <VAR_NAME> <prompt>
    local var="$1"
    local prompt="$2"

    read -rsp "  $prompt (required, input hidden): " value
    echo ""
    while [[ -z "$value" ]]; do
        echo -e "  ${RED}This field is required.${RESET}"
        read -rsp "  $prompt (required, input hidden): " value
        echo ""
    done

    printf -v "$var" '%s' "$value"
}

# ── Main ──────────────────────────────────────────────────────────────────────

print_header

# Back up existing .env if present
if [[ -f "$ENV_FILE" ]]; then
    backup="${ENV_FILE}.bak"
    cp "$ENV_FILE" "$backup"
    echo -e "${YELLOW}  Existing .env backed up to ${backup}${RESET}"
    echo ""
fi

# ── MySQL ─────────────────────────────────────────────────────────────────────
echo -e "${BOLD}── MySQL ─────────────────────────────────────────────${RESET}"
ask     DB_HOST "Database host"     "localhost"
ask     DB_PORT "Database port"     "3306"
ask     DB_USER "Database user"     "root"
ask_secret DB_PASSWORD "Database password"
ask     DB_NAME "Database name"     "bank_ai_agent"
echo ""

# ── AWS / Bedrock ─────────────────────────────────────────────────────────────
echo -e "${BOLD}── AWS / Bedrock ─────────────────────────────────────${RESET}"
ask     AWS_REGION           "AWS region"              "us-east-1"
ask_secret AWS_ACCESS_KEY_ID "AWS access key ID"
ask_secret AWS_SECRET_ACCESS_KEY "AWS secret access key"
ask     BEDROCK_MODEL_ID     "Bedrock model ID"        "anthropic.claude-3-sonnet-20240229-v1:0"
echo ""

# ── Agent behaviour ───────────────────────────────────────────────────────────
echo -e "${BOLD}── Agent Behaviour ───────────────────────────────────${RESET}"
ask MAX_AGENT_ITERATIONS "Max agent iterations"    "10"
ask AGENT_TEMPERATURE    "Agent temperature (0–1)" "0.1"
echo ""

# ── MCP REST server ───────────────────────────────────────────────────────────
echo -e "${BOLD}── MCP REST Server ───────────────────────────────────${RESET}"
echo -e "  ${YELLOW}Note: Docker overrides this to http://mcp-server:8000 automatically.${RESET}"
ask MCP_SERVER_URL "MCP server URL" "http://localhost:8000"
echo ""

# ── Write .env ────────────────────────────────────────────────────────────────
cat > "$ENV_FILE" <<EOF
# ─── MySQL ────────────────────────────────────────────────
DB_HOST=${DB_HOST}
DB_PORT=${DB_PORT}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
DB_NAME=${DB_NAME}

# ─── AWS / Bedrock ────────────────────────────────────────
AWS_REGION=${AWS_REGION}
AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
BEDROCK_MODEL_ID=${BEDROCK_MODEL_ID}

# ─── Agent Behaviour ──────────────────────────────────────
MAX_AGENT_ITERATIONS=${MAX_AGENT_ITERATIONS}
AGENT_TEMPERATURE=${AGENT_TEMPERATURE}

# ─── MCP REST Server ──────────────────────────────────────
# Docker overrides this to http://mcp-server:8000 automatically
MCP_SERVER_URL=${MCP_SERVER_URL}
EOF

chmod 600 "$ENV_FILE"

echo -e "${GREEN}${BOLD}  .env written successfully (permissions: 600)${RESET}"
echo ""
echo -e "${BOLD}  Summary${RESET}"
echo -e "  DB_HOST              = ${DB_HOST}"
echo -e "  DB_PORT              = ${DB_PORT}"
echo -e "  DB_USER              = ${DB_USER}"
echo -e "  DB_PASSWORD          = ********"
echo -e "  DB_NAME              = ${DB_NAME}"
echo -e "  AWS_REGION           = ${AWS_REGION}"
echo -e "  AWS_ACCESS_KEY_ID    = ********"
echo -e "  AWS_SECRET_ACCESS_KEY= ********"
echo -e "  BEDROCK_MODEL_ID     = ${BEDROCK_MODEL_ID}"
echo -e "  MAX_AGENT_ITERATIONS = ${MAX_AGENT_ITERATIONS}"
echo -e "  AGENT_TEMPERATURE    = ${AGENT_TEMPERATURE}"
echo -e "  MCP_SERVER_URL       = ${MCP_SERVER_URL}"
echo ""
echo -e "${YELLOW}  Next steps:${RESET}"
echo -e "  Docker:  docker compose build && docker compose up -d mysql mcp-server && docker compose run --rm app"
echo -e "  Local:   uvicorn mcp_server.api:app --port 8000  (separate terminal)"
echo -e "           python -m ui.cli"
echo ""
