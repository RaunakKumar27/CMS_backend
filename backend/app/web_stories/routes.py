import json
import re
import secrets
from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.core.auth import require_super_admin_web, require_writer_or_admin_web
from app.core.database import (
    articles_collection,
    categories_collection,
    notifications_collection,
    story_events_collection,
    users_collection,
    web_stories_collection,
)
from app.core.templates import templates
from app.public.routes import get_common_public_context
from app.services.audit_service import log_activity
from app.services.upload_service import save_web_story_image

admin_router = APIRouter(prefix="/admin/web-stories", tags=["Web Stories Admin"])
writer_router = APIRouter(prefix="/writer/web-stories", tags=["Web Stories Writer"])
public_router = APIRouter(tags=["Public Web Stories"])

ALLOWED_STORY_STATUSES = {"draft", "pending_review", "approved", "scheduled", "published", "rejected", "unpublished"}
ALLOWED_POSITIONS = {"top", "center", "bottom"}
ALLOWED_ALIGNMENTS = {"left", "center", "right"}
ALLOWED_SIZES = {"small", "medium", "large"}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:110] or "web-story"


async def unique_slug(title: str, excluding_id: Optional[ObjectId] = None) -> str:
    base = slugify(title)
    candidate = base
    number = 2
    query = {"slug": candidate}
    while True:
        if excluding_id:
            query["_id"] = {"$ne": excluding_id}
        if not await web_stories_collection.find_one(query):
            return candidate
        candidate = f"{base}-{number}"
        query = {"slug": candidate}
        number += 1


def serialize_story(story: dict) -> dict:
    story["_id"] = str(story["_id"])
    return story


def is_local_story_asset(url: str) -> bool:
    return isinstance(url, str) and url.startswith("/static/") and ".." not in url


def parse_pages(pages_json: str) -> list[dict]:
    try:
        pages = json.loads(pages_json)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=422, detail="Story pages contain invalid data.")
    if not isinstance(pages, list) or not pages or len(pages) > 30:
        raise HTTPException(status_code=422, detail="A story needs between 1 and 30 pages.")
    cleaned = []
    for index, page in enumerate(pages):
        if not isinstance(page, dict) or not is_local_story_asset(page.get("image", "")):
            raise HTTPException(status_code=422, detail="Every page needs an uploaded local image.")
        position = page.get("text_position", "bottom")
        alignment = page.get("text_alignment", "left")
        size = page.get("text_size", "medium")
        if position not in ALLOWED_POSITIONS or alignment not in ALLOWED_ALIGNMENTS or size not in ALLOWED_SIZES:
            raise HTTPException(status_code=422, detail="A story page contains unsupported display settings.")
        duration = int(page.get("duration", 5))
        if duration < 2 or duration > 30:
            raise HTTPException(status_code=422, detail="Page duration must be between 2 and 30 seconds.")
        cta_url = str(page.get("cta_url", "")).strip()
        if cta_url and not (cta_url.startswith("/") or cta_url.startswith("https://") or cta_url.startswith("http://")):
            raise HTTPException(status_code=422, detail="CTA links must be a site path or an http(s) URL.")
        cleaned.append({
            "id": str(page.get("id") or secrets.token_hex(8)),
            "order": index + 1,
            "image": page["image"],
            "headline": str(page.get("headline", ""))[:180],
            "description": str(page.get("description", ""))[:360],
            "text_position": position,
            "text_alignment": alignment,
            "text_size": size,
            "overlay": bool(page.get("overlay", True)),
            "background_position_x": max(0, min(100, int(page.get("background_position_x", 50)))),
            "background_position_y": max(0, min(100, int(page.get("background_position_y", 50)))),
            "zoom": max(100, min(180, int(page.get("zoom", 100)))),
            "duration": duration,
            "cta_text": str(page.get("cta_text", ""))[:60] or None,
            "cta_url": cta_url or None,
        })
    return cleaned


async def categories_for_editor() -> list[dict]:
    categories = await categories_collection.find({"is_active": True}).sort("order", 1).to_list(100)
    for category in categories:
        category["_id"] = str(category["_id"])
    return categories


async def editor_context(request: Request, user: dict, active_tab: str, story: Optional[dict] = None, from_article: str = "") -> dict:
    ctx = {"request": request, "current_user": user, "active_tab": active_tab, "categories": await categories_for_editor(), "story": story}
    if from_article and ObjectId.is_valid(from_article):
        article = await articles_collection.find_one({"_id": ObjectId(from_article)})
        if article:
            article["_id"] = str(article["_id"])
            ctx["from_article"] = article
    return ctx


async def save_story(
    *, story: Optional[dict], user: dict, title: str, description: str, category_id: str, tags: str,
    cover_image: str, pages_json: str, related_article_id: str, seo_title: str, seo_description: str,
    action_type: str, request: Request,
) -> str:
    title = title.strip()
    if not title or len(title) > 180:
        raise HTTPException(status_code=422, detail="Story title is required and must be under 180 characters.")
    if not ObjectId.is_valid(category_id):
        raise HTTPException(status_code=422, detail="Select a valid category.")
    category = await categories_collection.find_one({"_id": ObjectId(category_id), "is_active": True})
    if not category:
        raise HTTPException(status_code=422, detail="Selected category is not available.")
    pages = parse_pages(pages_json)
    if not is_local_story_asset(cover_image):
        raise HTTPException(status_code=422, detail="Upload a local cover image before saving.")
    related_id = related_article_id if ObjectId.is_valid(related_article_id) else None
    tag_list = [tag.strip()[:40] for tag in tags.split(",") if tag.strip()][:15]
    now = datetime.utcnow()
    status = "pending_review" if action_type == "submit" else "draft"
    if story and story.get("status") == "published" and user.get("role") != "super_admin":
        status = story["status"]
    document = {
        "title": title,
        "slug": await unique_slug(title, ObjectId(story["_id"]) if story else None),
        "description": description.strip()[:500],
        "category_id": category_id,
        "category_name": category.get("name", "General"),
        "tags": tag_list,
        "cover_image": cover_image,
        "pages": pages,
        "related_article_id": related_id,
        "seo_title": seo_title.strip()[:180] or title,
        "seo_description": seo_description.strip()[:320] or description.strip()[:320],
        "status": status,
        "updated_at": now,
    }
    if story:
        await web_stories_collection.update_one({"_id": ObjectId(story["_id"])}, {"$set": document})
        story_id = story["_id"]
        await log_activity(user, "WEB_STORY_UPDATED", f"Web Story '{title}' saved as {status}", request=request)
    else:
        document.update({
            "author_id": str(user["_id"]), "author_name": user.get("name", "DO Record"),
            "author_avatar": user.get("avatar_url", "/static/images/default_avatar.png"),
            "view_count": 0, "created_at": now, "published_at": None, "scheduled_at": None,
            "rejection_feedback": "",
        })
        result = await web_stories_collection.insert_one(document)
        story_id = str(result.inserted_id)
        await log_activity(user, "WEB_STORY_CREATED", f"Web Story '{title}' created as {status}", request=request)
    if status == "pending_review":
        await notifications_collection.insert_one({"user_id": "super_admin", "title": "Web Story awaiting review", "message": f"{user.get('name', 'A writer')} submitted '{title}'.", "read": False, "created_at": now})
        await log_activity(user, "WEB_STORY_SUBMITTED", f"Web Story '{title}' submitted for review", request=request)
    return story_id


@writer_router.get("", response_class=HTMLResponse)
async def writer_story_list(request: Request, status: str = "", user: dict = Depends(require_writer_or_admin_web)):
    query = {"author_id": str(user["_id"])}
    if status in ALLOWED_STORY_STATUSES:
        query["status"] = status
    stories = await web_stories_collection.find(query).sort("updated_at", -1).to_list(100)
    for story in stories: serialize_story(story)
    return templates.TemplateResponse(request=request, name="writer/web_stories_list.html", context={"request": request, "current_user": user, "active_tab": "web_stories", "stories": stories, "current_status": status})


@writer_router.get("/create", response_class=HTMLResponse)
async def writer_story_create_form(request: Request, from_article: str = "", user: dict = Depends(require_writer_or_admin_web)):
    return templates.TemplateResponse(request=request, name="stories/editor.html", context=await editor_context(request, user, "create_web_story", from_article=from_article))


@writer_router.post("/create")
async def writer_story_create(request: Request, title: str = Form(...), description: str = Form(""), category_id: str = Form(...), tags: str = Form(""), cover_image: str = Form(...), pages_json: str = Form(...), related_article_id: str = Form(""), seo_title: str = Form(""), seo_description: str = Form(""), action_type: str = Form("draft"), user: dict = Depends(require_writer_or_admin_web)):
    await save_story(story=None, user=user, title=title, description=description, category_id=category_id, tags=tags, cover_image=cover_image, pages_json=pages_json, related_article_id=related_article_id, seo_title=seo_title, seo_description=seo_description, action_type=action_type, request=request)
    return RedirectResponse("/writer/web-stories", status_code=303)


@writer_router.post("/upload-image")
async def writer_upload_story_image(file: UploadFile = File(...), user: dict = Depends(require_writer_or_admin_web)):
    url = await save_web_story_image(file)
    return JSONResponse({"success": True, "url": url, "filename": url.rsplit("/", 1)[-1]})


@writer_router.get("/{story_id}", response_class=HTMLResponse)
async def writer_story_edit_form(story_id: str, request: Request, user: dict = Depends(require_writer_or_admin_web)):
    if not ObjectId.is_valid(story_id): raise HTTPException(status_code=404, detail="Story not found.")
    story = await web_stories_collection.find_one({"_id": ObjectId(story_id)})
    if not story: raise HTTPException(status_code=404, detail="Story not found.")
    if user.get("role") != "super_admin" and story.get("author_id") != str(user["_id"]): raise HTTPException(status_code=403, detail="You can only edit your own stories.")
    serialize_story(story)
    return templates.TemplateResponse(request=request, name="stories/editor.html", context=await editor_context(request, user, "web_stories", story))


@writer_router.post("/{story_id}")
async def writer_story_update(story_id: str, request: Request, title: str = Form(...), description: str = Form(""), category_id: str = Form(...), tags: str = Form(""), cover_image: str = Form(...), pages_json: str = Form(...), related_article_id: str = Form(""), seo_title: str = Form(""), seo_description: str = Form(""), action_type: str = Form("draft"), user: dict = Depends(require_writer_or_admin_web)):
    if not ObjectId.is_valid(story_id): raise HTTPException(status_code=404, detail="Story not found.")
    story = await web_stories_collection.find_one({"_id": ObjectId(story_id)})
    if not story: raise HTTPException(status_code=404, detail="Story not found.")
    if user.get("role") != "super_admin" and story.get("author_id") != str(user["_id"]): raise HTTPException(status_code=403, detail="You can only edit your own stories.")
    serialize_story(story)
    await save_story(story=story, user=user, title=title, description=description, category_id=category_id, tags=tags, cover_image=cover_image, pages_json=pages_json, related_article_id=related_article_id, seo_title=seo_title, seo_description=seo_description, action_type=action_type, request=request)
    return RedirectResponse("/writer/web-stories", status_code=303)


@writer_router.get("/articles/search")
async def writer_article_search(q: str = Query("", max_length=100), user: dict = Depends(require_writer_or_admin_web)):
    query = {"status": "published"}
    if q.strip(): query["title"] = {"$regex": re.escape(q.strip()), "$options": "i"}
    docs = await articles_collection.find(query, {"title": 1, "slug": 1, "featured_image": 1, "category_id": 1, "excerpt": 1}).sort("published_at", -1).to_list(15)
    return [{"id": str(doc["_id"]), "title": doc.get("title", ""), "image": doc.get("featured_image", ""), "category_id": doc.get("category_id", ""), "description": doc.get("excerpt", "")} for doc in docs]


@admin_router.get("", response_class=HTMLResponse)
async def admin_story_list(request: Request, status: str = "", category_id: str = "", author_id: str = "", search: str = "", sort: str = "newest", user: dict = Depends(require_super_admin_web)):
    query = {}
    if status in ALLOWED_STORY_STATUSES: query["status"] = status
    if ObjectId.is_valid(category_id): query["category_id"] = category_id
    if ObjectId.is_valid(author_id): query["author_id"] = author_id
    if search.strip(): query["title"] = {"$regex": re.escape(search.strip()), "$options": "i"}
    sort_map = {"oldest": [("created_at", 1)], "views": [("view_count", -1)], "newest": [("created_at", -1)]}
    stories = await web_stories_collection.find(query).sort(sort_map.get(sort, sort_map["newest"])).to_list(100)
    for story in stories: serialize_story(story)
    writers = await users_collection.find({"role": {"$in": ["writer", "editor"]}}, {"name": 1}).sort("name", 1).to_list(100)
    for writer in writers: writer["_id"] = str(writer["_id"])
    pending_count = await web_stories_collection.count_documents({"status": "pending_review"})
    return templates.TemplateResponse(request=request, name="admin/web_stories_list.html", context={"request": request, "current_user": user, "active_tab": "web_stories", "stories": stories, "categories": await categories_for_editor(), "writers": writers, "pending_count": pending_count, "current_status": status, "current_cat": category_id, "current_author": author_id, "search_query": search, "current_sort": sort})


@admin_router.get("/create", response_class=HTMLResponse)
async def admin_story_create_form(request: Request, from_article: str = "", user: dict = Depends(require_super_admin_web)):
    return templates.TemplateResponse(request=request, name="stories/editor.html", context=await editor_context(request, user, "create_web_story", from_article=from_article))


@admin_router.post("/create")
async def admin_story_create(request: Request, title: str = Form(...), description: str = Form(""), category_id: str = Form(...), tags: str = Form(""), cover_image: str = Form(...), pages_json: str = Form(...), related_article_id: str = Form(""), seo_title: str = Form(""), seo_description: str = Form(""), action_type: str = Form("draft"), user: dict = Depends(require_super_admin_web)):
    story_id = await save_story(story=None, user=user, title=title, description=description, category_id=category_id, tags=tags, cover_image=cover_image, pages_json=pages_json, related_article_id=related_article_id, seo_title=seo_title, seo_description=seo_description, action_type=action_type, request=request)
    if action_type == "publish": await set_story_status(story_id, "published", user, request)
    return RedirectResponse("/admin/web-stories", status_code=303)


@admin_router.post("/upload-image")
async def admin_upload_story_image(file: UploadFile = File(...), user: dict = Depends(require_super_admin_web)):
    url = await save_web_story_image(file)
    return JSONResponse({"success": True, "url": url, "filename": url.rsplit("/", 1)[-1]})


@admin_router.get("/{story_id}", response_class=HTMLResponse)
async def admin_story_edit_form(story_id: str, request: Request, user: dict = Depends(require_super_admin_web)):
    if not ObjectId.is_valid(story_id): raise HTTPException(status_code=404, detail="Story not found.")
    story = await web_stories_collection.find_one({"_id": ObjectId(story_id)})
    if not story: raise HTTPException(status_code=404, detail="Story not found.")
    serialize_story(story)
    return templates.TemplateResponse(request=request, name="stories/editor.html", context=await editor_context(request, user, "web_stories", story))


@admin_router.post("/{story_id}")
async def admin_story_update(story_id: str, request: Request, title: str = Form(...), description: str = Form(""), category_id: str = Form(...), tags: str = Form(""), cover_image: str = Form(...), pages_json: str = Form(...), related_article_id: str = Form(""), seo_title: str = Form(""), seo_description: str = Form(""), action_type: str = Form("draft"), user: dict = Depends(require_super_admin_web)):
    if not ObjectId.is_valid(story_id): raise HTTPException(status_code=404, detail="Story not found.")
    story = await web_stories_collection.find_one({"_id": ObjectId(story_id)})
    if not story: raise HTTPException(status_code=404, detail="Story not found.")
    serialize_story(story)
    await save_story(story=story, user=user, title=title, description=description, category_id=category_id, tags=tags, cover_image=cover_image, pages_json=pages_json, related_article_id=related_article_id, seo_title=seo_title, seo_description=seo_description, action_type=action_type, request=request)
    if action_type == "publish": await set_story_status(story_id, "published", user, request)
    return RedirectResponse("/admin/web-stories", status_code=303)


async def set_story_status(story_id: str, new_status: str, user: dict, request: Request, feedback: str = "", scheduled_at: Optional[datetime] = None):
    if new_status not in ALLOWED_STORY_STATUSES or not ObjectId.is_valid(story_id): raise HTTPException(status_code=404, detail="Story not found.")
    story = await web_stories_collection.find_one({"_id": ObjectId(story_id)})
    if not story: raise HTTPException(status_code=404, detail="Story not found.")
    update = {"status": new_status, "updated_at": datetime.utcnow()}
    if new_status == "published": update["published_at"] = datetime.utcnow(); update["scheduled_at"] = None
    if new_status == "scheduled":
        if not scheduled_at or scheduled_at <= datetime.utcnow(): raise HTTPException(status_code=422, detail="Choose a future publish time.")
        update["scheduled_at"] = scheduled_at
    if new_status == "rejected": update["rejection_feedback"] = feedback.strip()[:500]
    await web_stories_collection.update_one({"_id": ObjectId(story_id)}, {"$set": update})
    action = f"WEB_STORY_{new_status.upper()}"
    await log_activity(user, action, f"Web Story '{story.get('title', '')}'", request=request)
    if new_status in {"approved", "rejected", "published"} and story.get("author_id"):
        await notifications_collection.insert_one({"user_id": story["author_id"], "title": f"Web Story {new_status.replace('_', ' ').title()}", "message": f"'{story.get('title', '')}' is now {new_status.replace('_', ' ')}." + (f" Feedback: {feedback.strip()}" if feedback.strip() else ""), "read": False, "created_at": datetime.utcnow()})


@admin_router.post("/{story_id}/status")
async def admin_story_status(story_id: str, request: Request, status: str = Form(...), feedback: str = Form(""), scheduled_at: str = Form(""), user: dict = Depends(require_super_admin_web)):
    schedule = None
    if scheduled_at:
        try: schedule = datetime.fromisoformat(scheduled_at)
        except ValueError: raise HTTPException(status_code=422, detail="Invalid scheduled time.")
    await set_story_status(story_id, status, user, request, feedback, schedule)
    return RedirectResponse("/admin/web-stories", status_code=303)


@admin_router.post("/{story_id}/delete")
async def admin_story_delete(story_id: str, request: Request, user: dict = Depends(require_super_admin_web)):
    if not ObjectId.is_valid(story_id): raise HTTPException(status_code=404, detail="Story not found.")
    story = await web_stories_collection.find_one_and_delete({"_id": ObjectId(story_id)})
    if not story: raise HTTPException(status_code=404, detail="Story not found.")
    await log_activity(user, "WEB_STORY_DELETED", f"Web Story '{story.get('title', '')}'", request=request)
    return RedirectResponse("/admin/web-stories", status_code=303)


@admin_router.get("/related-articles/search")
async def admin_article_search(q: str = Query("", max_length=100), user: dict = Depends(require_super_admin_web)):
    return await writer_article_search(q, user)


async def publish_due_stories():
    await web_stories_collection.update_many({"status": "scheduled", "scheduled_at": {"$lte": datetime.utcnow()}}, {"$set": {"status": "published", "published_at": datetime.utcnow(), "updated_at": datetime.utcnow()}})


async def public_story_query(extra: Optional[dict] = None) -> dict:
    await publish_due_stories()
    query = {"status": "published"}
    if extra: query.update(extra)
    return query


@public_router.get("/web-stories", response_class=HTMLResponse)
async def public_story_listing(request: Request):
    ctx = await get_common_public_context(request)
    ctx["current_page"] = "stories"
    stories = await web_stories_collection.find(await public_story_query()).sort("published_at", -1).to_list(60)
    for story in stories: serialize_story(story)
    ctx["stories"] = stories
    return templates.TemplateResponse(request=request, name="public/web_stories.html", context=ctx)


@public_router.get("/web-stories/{category_slug}", response_class=HTMLResponse)
async def public_story_category(category_slug: str, request: Request):
    ctx = await get_common_public_context(request)
    category = await categories_collection.find_one({"slug": category_slug, "is_active": True})
    if not category: raise HTTPException(status_code=404, detail="Story category not found.")
    stories = await web_stories_collection.find(await public_story_query({"category_id": str(category["_id"])})).sort("published_at", -1).to_list(60)
    for story in stories: serialize_story(story)
    ctx.update({"stories": stories, "story_category": category, "current_page": "stories"})
    return templates.TemplateResponse(request=request, name="public/web_stories.html", context=ctx)


@public_router.get("/web-stories/story/{slug}", response_class=HTMLResponse)
async def public_story_viewer(slug: str, request: Request):
    story = await web_stories_collection.find_one(await public_story_query({"slug": slug}))
    if not story: raise HTTPException(status_code=404, detail="Web Story not found.")
    await web_stories_collection.update_one({"_id": story["_id"]}, {"$inc": {"view_count": 1}})
    story["view_count"] = story.get("view_count", 0) + 1
    related = None
    if story.get("related_article_id") and ObjectId.is_valid(story["related_article_id"]):
        related = await articles_collection.find_one({"_id": ObjectId(story["related_article_id"]), "status": "published"}, {"title": 1, "slug": 1})
    viewer_story = {
        "title": str(story.get("title", "")),
        "description": str(story.get("description", "")),
        "seo_title": str(story.get("seo_title", "")),
        "seo_description": str(story.get("seo_description", "")),
        "cover_image": str(story.get("cover_image", "")),
        "published_at": story.get("published_at").isoformat() if story.get("published_at") else "",
        "author_name": str(story.get("author_name", "DO Record")),
        "category_name": str(story.get("category_name", "General")),
        "pages": story.get("pages", []),
    }
    viewer_related = {"title": related.get("title", ""), "slug": related.get("slug", "")} if related else None
    return templates.TemplateResponse(request=request, name="public/web_story_viewer.html", context={"request": request, "story": viewer_story, "related_article": viewer_related})


@public_router.post("/web-stories/story/{slug}/analytics")
async def public_story_analytics(slug: str, request: Request):
    story = await web_stories_collection.find_one(await public_story_query({"slug": slug}), {"_id": 1})
    if not story: raise HTTPException(status_code=404, detail="Web Story not found.")
    try: payload = await request.json()
    except Exception: payload = {}
    event = payload.get("event")
    if event not in {"opened", "page_viewed", "completed", "cta_clicked", "share_clicked"}: raise HTTPException(status_code=422, detail="Unsupported event.")
    page = payload.get("page")
    await story_events_collection.insert_one({"story_id": str(story["_id"]), "event": event, "page": int(page) if isinstance(page, int) or str(page).isdigit() else None, "created_at": datetime.utcnow(), "user_agent": request.headers.get("user-agent", "")[:200]})
    return {"ok": True}
