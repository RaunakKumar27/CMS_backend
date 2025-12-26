from fastapi import APIRouter
from backend.api.v1.routes.content import router as content_router

api_router = APIRouter()

api_router.include_router(
    content_router,
    prefix="/content", 
    tags=["Content"]
)

