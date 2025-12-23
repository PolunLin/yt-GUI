import os
from fastapi import Header, HTTPException

def require_api_key(x_api_key: str | None = Header(default=None)):
    expected = os.getenv("API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(401, "invalid api key")