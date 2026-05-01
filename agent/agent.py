"""
agent/agent.py

Amazon Bedrock agent that:
1. Connects to the MCP REST server over HTTP
2. Fetches tool definitions and converts them to Bedrock toolSpec format
3. Runs the full tool-use agentic loop
"""

import asyncio
import json
import logging
import os
import uuid
from typing import Any

import boto3
import httpx
from botocore.config import Config
from dotenv import load_dotenv

from .prompts import SYSTEM_PROMPT

load_dotenv()
log = logging.getLogger(__name__)

MODEL_ID        = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")
AWS_REGION      = os.getenv("AWS_REGION", "us-east-1")
MAX_ITER        = int(os.getenv("MAX_AGENT_ITERATIONS", "10"))
TEMPERATURE     = float(os.getenv("AGENT_TEMPERATURE", "0.1"))
MCP_SERVER_URL  = os.getenv("MCP_SERVER_URL", "http://localhost:8000")


# ── Bedrock client ─────────────────────────────────────────────────────────────

def _bedrock_client():
    return boto3.client(
        "bedrock-runtime",
        region_name=AWS_REGION,
        config=Config(retries={"max_attempts": 3, "mode": "adaptive"}),
    )


# ── Tool conversion helpers ───────────────────────────────────────────────────

def _tool_dict_to_bedrock(tool: dict) -> dict:
    """Convert a tool definition dict to Bedrock's toolSpec format."""
    return {
        "toolSpec": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "inputSchema": {"json": tool["inputSchema"]},
        }
    }


# ── Main agent class ──────────────────────────────────────────────────────────

class BankAgent:
    """
    Agentic loop:
      user message → Bedrock (Claude) → tool_use blocks
      → MCP REST server → tool_result → Bedrock → … → final text
    """

    def __init__(self):
        self.session_id     = str(uuid.uuid4())[:8]
        self.bedrock        = _bedrock_client()
        self.http_client: httpx.AsyncClient | None = None
        self.bedrock_tools: list[dict] = []
        self.conversation:  list[dict] = []

    # ── MCP session management ────────────────────────────────────────────────

    async def _start_mcp(self):
        """Create HTTP client and fetch tool definitions from the MCP REST server."""
        self.http_client = httpx.AsyncClient(base_url=MCP_SERVER_URL, timeout=30.0)
        response = await self.http_client.get("/tools")
        response.raise_for_status()
        tools = response.json()["tools"]
        self.bedrock_tools = [_tool_dict_to_bedrock(t) for t in tools]
        log.info("MCP REST server ready at %s — %d tools loaded", MCP_SERVER_URL, len(self.bedrock_tools))

    async def _stop_mcp(self):
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None

    # ── Tool execution ────────────────────────────────────────────────────────

    async def _call_tool(self, tool_name: str, tool_input: dict) -> str:
        """Call an MCP tool via REST and return the text result."""
        log.info("→ Calling tool: %s  input=%s", tool_name, json.dumps(tool_input)[:200])
        response = await self.http_client.post(
            "/tools/call",
            json={"name": tool_name, "arguments": tool_input},
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("content", [])
        if content and content[0].get("type") == "text":
            return content[0]["text"]
        return json.dumps({"result": str(content)})

    # ── Bedrock invocation ────────────────────────────────────────────────────

    def _invoke_bedrock(self) -> dict:
        """Send current conversation to Bedrock and return the raw response."""
        return self.bedrock.converse(
            modelId=MODEL_ID,
            system=[{"text": SYSTEM_PROMPT}],
            messages=self.conversation,
            toolConfig={"tools": self.bedrock_tools},
            inferenceConfig={
                "temperature": TEMPERATURE,
                "maxTokens": 4096,
            },
        )

    # ── Agentic loop ──────────────────────────────────────────────────────────

    async def chat(self, user_message: str, on_token=None) -> str:
        """
        Process one user message through the full agentic loop.
        `on_token` is an optional async callback(str) for streaming text chunks.
        Returns the final assistant text response.
        """
        self.conversation.append({"role": "user", "content": [{"text": user_message}]})

        final_text = ""

        for iteration in range(MAX_ITER):
            log.info("Agent iteration %d/%d", iteration + 1, MAX_ITER)
            response = self._invoke_bedrock()

            output_msg  = response["output"]["message"]
            stop_reason = response["stopReason"]

            text_parts: list[str]  = []
            tool_calls: list[dict] = []

            for block in output_msg["content"]:
                if block.get("text"):
                    text_parts.append(block["text"])
                    if on_token:
                        await on_token(block["text"])
                elif block.get("toolUse"):
                    tool_calls.append(block["toolUse"])

            self.conversation.append({"role": "assistant", "content": output_msg["content"]})

            if text_parts:
                final_text = "\n".join(text_parts)

            if stop_reason == "end_turn" or not tool_calls:
                break

            tool_results: list[dict] = []
            for tc in tool_calls:
                tool_output = await self._call_tool(tc["name"], tc["input"])
                tool_results.append({
                    "toolResult": {
                        "toolUseId": tc["toolUseId"],
                        "content": [{"text": tool_output}],
                    }
                })

                # Auto-audit significant write operations
                if tc["name"] == "update_loan_status":
                    await self._call_tool("log_ai_action", {
                        "session_id":   self.session_id,
                        "action_type":  "LOAN_STATUS_UPDATE",
                        "entity_type":  "loan_application",
                        "entity_id":    tc["input"].get("application_id", ""),
                        "tool_name":    tc["name"],
                        "tool_input":   tc["input"],
                        "tool_output":  tool_output,
                        "ai_reasoning": final_text or "Agent decision",
                    })

            self.conversation.append({"role": "user", "content": tool_results})

        else:
            final_text += "\n\n⚠️ Max iterations reached."

        return final_text

    async def reset(self):
        """Clear conversation history."""
        self.conversation = []
        self.session_id   = str(uuid.uuid4())[:8]
        log.info("Conversation reset — new session %s", self.session_id)

    # ── Context manager ───────────────────────────────────────────────────────

    async def __aenter__(self):
        await self._start_mcp()
        return self

    async def __aexit__(self, *_):
        await self._stop_mcp()
