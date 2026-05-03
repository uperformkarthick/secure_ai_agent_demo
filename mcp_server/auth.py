"""
mcp_server/auth.py
OAuth 2.0 Client Credentials authentication.
Enabled only when ENABLE_AUTH=true in the environment.
"""
import os
import time

import jwt

ENABLE_AUTH: bool = os.getenv("ENABLE_AUTH", "false").lower() == "true"

_CLIENT_ID: str = os.getenv("OAUTH_CLIENT_ID", "")
_CLIENT_SECRET: str = os.getenv("OAUTH_CLIENT_SECRET", "")
_JWT_SECRET: str = os.getenv("OAUTH_JWT_SECRET", "")
TOKEN_EXPIRY: int = int(os.getenv("OAUTH_TOKEN_EXPIRY", "3600"))


def verify_client(client_id: str, client_secret: str) -> bool:
    return bool(_CLIENT_ID) and client_id == _CLIENT_ID and client_secret == _CLIENT_SECRET


def create_access_token() -> str:
    now = int(time.time())
    return jwt.encode(
        {"iss": "bank-ai-agent", "sub": _CLIENT_ID, "iat": now, "exp": now + TOKEN_EXPIRY},
        _JWT_SECRET,
        algorithm="HS256",
    )


def validate_token(token: str) -> bool:
    if not _JWT_SECRET:
        return False
    try:
        jwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
        return True
    except jwt.InvalidTokenError:
        return False
