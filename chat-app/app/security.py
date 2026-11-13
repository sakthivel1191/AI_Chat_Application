import os
import hashlib
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from dotenv import load_dotenv

load_dotenv()
api_key_header = APIKeyHeader(name="X-API-Key")
def verify_api_key(x_api_key: str = Security(api_key_header)):
    api_key = os.getenv("API_KEY")
    if not api_key or x_api_key != api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    return hashlib.sha256(x_api_key.encode()).hexdigest()
