from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException
from datetime import datetime

from app.core.database import content_collection
from app.models.content import ContentCreate, ContentUpdate


# ---------- CREATE ----------
async def create_content(data: ContentCreate):
    content = data.dict()
    content["created_at"] = datetime.utcnow()
    content["updated_at"] = datetime.utcnow()

    result = await content_collection.insert_one(content)
    content["_id"] = str(result.inserted_id)
    return content


# ---------- READ ONE ----------
async def get_content(content_id: str):
    try:
        oid = ObjectId(content_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid content ID")

    content = await content_collection.find_one({"_id": oid})
    if content is None:
        raise HTTPException(status_code=404, detail="Content not found")

    content["_id"] = str(content["_id"])
    return content


# ---------- READ ALL ----------
async def get_all_content():
    contents = []
    async for c in content_collection.find():
        c["_id"] = str(c["_id"])
        contents.append(c)
    return contents


# ---------- UPDATE ----------
async def update_content(content_id: str, data: ContentUpdate):
    try:
        oid = ObjectId(content_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid content ID")

    update_data = data.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow()

    result = await content_collection.update_one(
        {"_id": oid},
        {"$set": update_data},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Content not found")

    return {"message": "Content updated successfully"}


# ---------- DELETE ----------
async def delete_content(content_id: str):
    try:
        oid = ObjectId(content_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid content ID")

    result = await content_collection.delete_one({"_id": oid})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Content not found")

    return {"message": "Content deleted successfully"}


from app.core.cache import redis_client

async def render_content(content_id: str):
    cache_key = f"rendered:{content_id}"

    cached_html = redis_client.get(cache_key)
    if cached_html:
        return cached_html   # ⚡ FAST (Redis)

    html = render_with_jinja(content_id)

    redis_client.setex(cache_key, 3600, html)  # cache for 1 hour
    return html
