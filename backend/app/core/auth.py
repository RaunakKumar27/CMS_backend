from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
from typing import Optional, List
from bson import ObjectId
from app.core.security import decode_access_token
from app.core.database import users_collection, sessions_collection

async def get_current_user_from_request(request: Request) -> Optional[dict]:
    """Retrieves current user from cookie or Authorization header."""
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
    if not token:
        return None
        
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
        
    user_id = payload["sub"]
    try:
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user or not user.get("is_active", True):
            return None
        user["_id"] = str(user["_id"])
        return user
    except Exception:
        return None

async def require_user_web(request: Request) -> dict:
    """Web route dependency enforcing authentication. Redirects to /login if unauthenticated."""
    user = await get_current_user_from_request(request)
    if not user:
        # Save intended destination in query string or cookie if needed
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login?next=" + str(request.url.path)}
        )
    return user

async def require_super_admin_web(request: Request) -> dict:
    """Web route dependency requiring Super Admin role."""
    user = await require_user_web(request)
    if user.get("role") != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin privileges required to access this section."
        )
    return user

async def require_writer_or_admin_web(request: Request) -> dict:
    """Web route dependency allowing Writers and Super Admins."""
    user = await require_user_web(request)
    if user.get("role") not in ["super_admin", "writer", "editor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Writer or Admin access required."
        )
    return user

async def require_user_api(request: Request) -> dict:
    """API endpoint dependency enforcing authentication (returns JSON 401)."""
    user = await get_current_user_from_request(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return user

def require_permission(permission_name: str):
    """API endpoint dependency enforcing specific permission check."""
    async def permission_checker(user: dict = Depends(require_user_api)):
        if user.get("role") == "super_admin":
            return user
        
        user_permissions = user.get("permissions", [])
        if permission_name not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission_name}' denied."
            )
        return user
    return permission_checker
