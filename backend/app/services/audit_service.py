from fastapi import Request
from typing import Optional
from datetime import datetime
from app.core.database import activity_logs_collection

async def log_activity(
    user: dict,
    action: str,
    target: str,
    details: Optional[str] = "",
    request: Optional[Request] = None
):
    """Helper to log security, workflow, and management actions into audit log collection."""
    ip_address = ""
    user_agent = ""
    if request:
        client = request.client
        ip_address = client.host if client else ""
        user_agent = request.headers.get("user-agent", "")
        
    log_doc = {
        "user_id": str(user.get("_id", "system")),
        "username": user.get("username", "System"),
        "role": user.get("role", "unknown"),
        "action": action,
        "target": target,
        "details": details,
        "ip_address": ip_address,
        "user_agent": user_agent[:200], # truncate
        "created_at": datetime.utcnow()
    }
    
    try:
        await activity_logs_collection.insert_one(log_doc)
    except Exception as e:
        print(f"Failed to log activity: {e}")
