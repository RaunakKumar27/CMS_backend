from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.templates import templates
from app.models.content import ContentCreate, ContentUpdate
from app.services.content_service import (
    create_content,
    get_content,
    get_all_content,
    update_content,
    delete_content,
)
from app.core.cache import redis_client  # ✅ REQUIRED

router = APIRouter()

# ---------- CREATE ----------
@router.post("/")
async def create(data: ContentCreate):
    return await create_content(data)


# ---------- READ ALL ----------
@router.get("/")
async def read_all():
    return await get_all_content()


# ---------- READ ONE ----------
@router.get("/{content_id}")
async def read(content_id: str):
    return await get_content(content_id)


# ---------- UPDATE ----------
@router.put("/{content_id}")
async def update_content_route(content_id: str, data: ContentUpdate):
    return await update_content(content_id, data)


# ---------- DELETE ----------
@router.delete("/{content_id}")
async def remove(content_id: str):
    return await delete_content(content_id)


# ---------- RENDER (KEEP ABOVE {content_id} IF EVER REORDERED) ----------
@router.get("/render/{content_id}", response_class=HTMLResponse)
async def render_content(content_id: str, request: Request):
    cache_key = f"content:{content_id}"

    # 1️⃣ Redis cache
    cached_html = redis_client.get(cache_key)
    if cached_html:
        return HTMLResponse(cached_html)

    # 2️⃣ MongoDB
    content = await get_content(content_id)

    # 3️⃣ Render HTML
    response = templates.TemplateResponse(request=request, name="page.html", context={"request": request, "content": content})


    # 4️⃣ Cache HTML
    html_body = response.body.decode("utf-8")
    redis_client.setex(cache_key, 3600, html_body)

    return response
