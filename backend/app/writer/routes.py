from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse

from fastapi.responses import HTMLResponse, RedirectResponse
from datetime import datetime
from bson import ObjectId
from typing import Optional
from app.core.database import (
    articles_collection,
    users_collection,
    categories_collection,
    notifications_collection,
)
from app.core.auth import require_writer_or_admin_web
from app.core.security import hash_password, verify_password
from app.services.audit_service import log_activity
from app.services.upload_service import save_article_image, save_profile_photo
from app.core.templates import templates

router = APIRouter(prefix="/writer", tags=["Writer Panel"])

async def get_writer_common_ctx(request: Request, user: dict, active_tab: str = "dashboard"):
    return {
        "request": request,
        "current_user": user,
        "active_tab": active_tab,
    }


# ==========================================
# 1. WRITER DASHBOARD
# ==========================================
@router.get("", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def writer_dashboard(request: Request, user: dict = Depends(require_writer_or_admin_web)):
    ctx = await get_writer_common_ctx(request, user, "dashboard")
    writer_id = str(user["_id"])
    
    total_articles = await articles_collection.count_documents({"author_id": writer_id})
    published_articles = await articles_collection.count_documents({"author_id": writer_id, "status": "published"})
    pending_articles = await articles_collection.count_documents({"author_id": writer_id, "status": "pending"})
    draft_articles = await articles_collection.count_documents({"author_id": writer_id, "status": "draft"})
    rejected_articles = await articles_collection.count_documents({"author_id": writer_id, "status": "rejected"})
    
    pipeline = [
        {"$match": {"author_id": writer_id}},
        {"$group": {"_id": None, "total": {"$sum": "$views_count"}}}
    ]
    views_res = await articles_collection.aggregate(pipeline).to_list(1)
    total_views = views_res[0]["total"] if views_res else 0
    
    ctx["stats"] = {
        "total_articles": total_articles,
        "published_articles": published_articles,
        "pending_articles": pending_articles,
        "draft_articles": draft_articles,
        "rejected_articles": rejected_articles,
        "total_views": total_views,
    }
    
    rejected_list = await articles_collection.find({"author_id": writer_id, "status": "rejected"}).to_list(10)
    for r in rejected_list:
        r["_id"] = str(r["_id"])
    ctx["rejected_articles"] = rejected_list
    
    my_articles = await articles_collection.find({"author_id": writer_id}).sort("updated_at", -1).to_list(6)
    for m in my_articles:
        m["_id"] = str(m["_id"])
    ctx["my_articles"] = my_articles
    
    return templates.TemplateResponse(request=request, name="writer/dashboard.html", context=ctx)


# ==========================================
# 2. MY ARTICLES & EDITOR
# ==========================================
@router.get("/articles", response_class=HTMLResponse)
async def list_my_articles(request: Request, status: Optional[str] = None, user: dict = Depends(require_writer_or_admin_web)):
    ctx = await get_writer_common_ctx(request, user, "my_articles")
    writer_id = str(user["_id"])
    
    query = {"author_id": writer_id}
    if status:
        query["status"] = status
        
    articles = await articles_collection.find(query).sort("updated_at", -1).to_list(100)
    for a in articles:
        a["_id"] = str(a["_id"])
    ctx["articles"] = articles
    ctx["current_status"] = status
    
    return templates.TemplateResponse(request=request, name="writer/articles_list.html", context=ctx)


@router.post("/articles/upload-image")
async def upload_article_image(file: UploadFile = File(...), user: dict = Depends(require_writer_or_admin_web)):
    url = await save_article_image(file)
    return JSONResponse({"success": True, "url": url, "filename": url.rsplit("/", 1)[-1]})


@router.get("/articles/create", response_class=HTMLResponse)
async def create_story_form(request: Request, user: dict = Depends(require_writer_or_admin_web)):
    ctx = await get_writer_common_ctx(request, user, "create")
    categories = await categories_collection.find({}).to_list(100)
    for c in categories:
        c["_id"] = str(c["_id"])
    ctx["categories"] = categories
    ctx["article"] = None
    return templates.TemplateResponse(request=request, name="writer/article_editor.html", context=ctx)


@router.post("/articles/create")
async def process_create_story(
    request: Request,
    title: str = Form(...),
    excerpt: str = Form(""),
    body: str = Form(...),
    category_id: str = Form(...),
    cover_image: Optional[UploadFile] = File(None),
    featured_image: Optional[str] = Form(None),
    tags: str = Form(""),
    is_breaking: bool = Form(False),
    is_web_story: bool = Form(False),
    web_story_template: str = Form("classic"),
    action_type: str = Form("submit"), # "draft" or "submit"
    user: dict = Depends(require_writer_or_admin_web)
):
    cat = await categories_collection.find_one({"_id": ObjectId(category_id)}) if ObjectId.is_valid(category_id) else None
    cat_name = cat["name"] if cat else "General"
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    status = "pending" if action_type == "submit" else "draft"
    image_url = featured_image.strip() if featured_image is not None else ""
    if not image_url and cover_image and cover_image.filename:
        image_url = await save_article_image(cover_image)
    image_url = image_url or "/static/images/default_news.jpg"
    
    doc = {
        "title": title.strip(),
        "slug": title.lower().replace(" ", "-"),
        "excerpt": excerpt.strip(),
        "body": body,
        "featured_image": image_url,
        "category_id": category_id,
        "category_name": cat_name,
        "tags": tag_list,
        "author_id": str(user["_id"]),
        "author_name": user["name"],
        "author_avatar": user.get("avatar_url", "/static/images/default_avatar.png"),
        "status": status,
        "is_featured": False,
        "is_breaking": is_breaking,
        "is_web_story": is_web_story,
        "web_story_template": web_story_template if is_web_story else None,
        "views_count": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    res = await articles_collection.insert_one(doc)
    
    if status == "pending":
        # Create notification for super admin
        await notifications_collection.insert_one({
            "user_id": "super_admin",
            "title": "New Article Submitted for Editorial Review",
            "message": f"Writer {user['name']} submitted '{title.strip()}' for review.",
            "read": False,
            "created_at": datetime.utcnow()
        })
        
    await log_activity(user, f"WRITER_STORY_{status.upper()}", f"Story '{title}' submitted as {status}", request=request)
    return RedirectResponse(url="/writer/articles", status_code=303)


@router.get("/articles/{article_id}", response_class=HTMLResponse)
async def edit_my_story_form(article_id: str, request: Request, user: dict = Depends(require_writer_or_admin_web)):
    ctx = await get_writer_common_ctx(request, user, "my_articles")
    writer_id = str(user["_id"])
    
    article = await articles_collection.find_one({"_id": ObjectId(article_id)})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found.")
        
    # Enforce ownership check for normal writers
    if user.get("role") == "writer" and article.get("author_id") != writer_id:
        raise HTTPException(status_code=403, detail="You can only edit your own articles.")
        
    article["_id"] = str(article["_id"])
    ctx["article"] = article
    
    categories = await categories_collection.find({}).to_list(100)
    for c in categories:
        c["_id"] = str(c["_id"])
    ctx["categories"] = categories
    
    return templates.TemplateResponse(request=request, name="writer/article_editor.html", context=ctx)


@router.post("/articles/{article_id}")
async def process_update_my_story(
    article_id: str,
    request: Request,
    title: str = Form(...),
    excerpt: str = Form(""),
    body: str = Form(...),
    category_id: str = Form(...),
    cover_image: Optional[UploadFile] = File(None),
    featured_image: Optional[str] = Form(None),
    tags: str = Form(""),
    is_breaking: bool = Form(False),
    is_web_story: bool = Form(False),
    web_story_template: str = Form("classic"),
    action_type: str = Form("submit"),
    user: dict = Depends(require_writer_or_admin_web)
):
    writer_id = str(user["_id"])
    existing = await articles_collection.find_one({"_id": ObjectId(article_id)})
    if not existing:
        raise HTTPException(status_code=404, detail="Article not found.")
        
    if user.get("role") == "writer" and existing.get("author_id") != writer_id:
        raise HTTPException(status_code=403, detail="Access denied.")
        
    cat = await categories_collection.find_one({"_id": ObjectId(category_id)}) if ObjectId.is_valid(category_id) else None
    cat_name = cat["name"] if cat else "General"
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    status = "pending" if action_type == "submit" else "draft"
    if featured_image is None:
        image_url = existing.get("featured_image", "/static/images/default_news.jpg")
    else:
        image_url = featured_image.strip() or "/static/images/default_news.jpg"
    if cover_image and cover_image.filename:
        image_url = await save_article_image(cover_image)
    
    update_doc = {
        "title": title.strip(),
        "excerpt": excerpt.strip(),
        "body": body,
        "featured_image": image_url,
        "category_id": category_id,
        "category_name": cat_name,
        "tags": tag_list,
        "status": status,
        "is_breaking": is_breaking,
        "is_web_story": is_web_story,
        "web_story_template": web_story_template if is_web_story else None,
        "updated_at": datetime.utcnow(),
    }
    
    await articles_collection.update_one({"_id": ObjectId(article_id)}, {"$set": update_doc})
    await log_activity(user, "WRITER_STORY_UPDATED", f"Story '{title}' updated ({status})", request=request)
    return RedirectResponse(url="/writer/articles", status_code=303)


# ==========================================
# 3. NOTIFICATIONS & FEEDBACK
# ==========================================
@router.get("/notifications", response_class=HTMLResponse)
async def writer_notifications(request: Request, user: dict = Depends(require_writer_or_admin_web)):
    ctx = await get_writer_common_ctx(request, user, "notifications")
    writer_id = str(user["_id"])
    
    notifs = await notifications_collection.find({"$or": [{"user_id": writer_id}, {"user_id": "all"}]}).sort("created_at", -1).to_list(50)
    for n in notifs:
        n["_id"] = str(n["_id"])
    ctx["notifications"] = notifs
    return templates.TemplateResponse(request=request, name="admin/notifications.html", context=ctx)


# ==========================================
# 4. PROFILE & SECURITY
# ==========================================
@router.get("/profile", response_class=HTMLResponse)
async def writer_profile_page(request: Request, msg: str = "", status: str = "success", user: dict = Depends(require_writer_or_admin_web)):
    ctx = await get_writer_common_ctx(request, user, "profile")
    ctx["msg"] = msg
    ctx["msg_status"] = status
    return templates.TemplateResponse(request=request, name="writer/profile.html", context=ctx)


@router.post("/profile")
async def update_writer_profile(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    avatar_url: str = Form(""),
    bio: str = Form(""),
    user: dict = Depends(require_writer_or_admin_web)
):
    writer_id = str(user["_id"])
    update_doc = {
        "name": name.strip(),
        "email": email.strip().lower(),
        "avatar_url": avatar_url.strip() or "/static/images/default_avatar.png",
        "bio": bio.strip(),
    }
    await users_collection.update_one({"_id": ObjectId(writer_id)}, {"$set": update_doc})
    # Update author avatar & name on articles
    await articles_collection.update_many({"author_id": writer_id}, {"$set": {"author_name": name.strip(), "author_avatar": update_doc["avatar_url"]}})
    await log_activity(user, "PROFILE_UPDATED", "Updated journalist bio & profile", request=request)
    return RedirectResponse(url="/writer/profile?msg=Profile+updated+successfully.", status_code=303)


@router.post("/profile/upload-photo")
async def upload_writer_profile_photo(
    request: Request,
    photo_file: UploadFile = File(...),
    user: dict = Depends(require_writer_or_admin_web)
):
    writer_id = str(user["_id"])
    avatar_url = await save_profile_photo(photo_file)
    
    await users_collection.update_one({"_id": ObjectId(writer_id)}, {"$set": {"avatar_url": avatar_url}})
    await articles_collection.update_many({"author_id": writer_id}, {"$set": {"author_avatar": avatar_url}})
    await log_activity(user, "PROFILE_PHOTO_UPLOADED", f"Writer uploaded new profile photo: {avatar_url}", request=request)
    return RedirectResponse(url="/writer/profile?msg=Profile+photo+updated+successfully.", status_code=303)


@router.post("/profile/photo")
async def upload_writer_profile_photo_json(
    photo_file: UploadFile = File(...),
    user: dict = Depends(require_writer_or_admin_web),
):
    avatar_url = await save_profile_photo(photo_file)
    writer_id = str(user["_id"])
    await users_collection.update_one({"_id": ObjectId(writer_id)}, {"$set": {"avatar_url": avatar_url}})
    await articles_collection.update_many({"author_id": writer_id}, {"$set": {"author_avatar": avatar_url}})
    return JSONResponse({"success": True, "url": avatar_url, "filename": avatar_url.rsplit("/", 1)[-1]})


@router.post("/profile/photo/remove")
async def remove_writer_profile_photo(request: Request, user: dict = Depends(require_writer_or_admin_web)):
    writer_id = str(user["_id"])
    default_avatar = "/static/images/default_avatar.png"
    await users_collection.update_one({"_id": ObjectId(writer_id)}, {"$set": {"avatar_url": default_avatar}})
    await articles_collection.update_many({"author_id": writer_id}, {"$set": {"author_avatar": default_avatar}})
    await log_activity(user, "PROFILE_PHOTO_REMOVED", "Writer removed the profile photo", request=request)
    return JSONResponse({"success": True, "url": default_avatar})



@router.get("/security", response_class=HTMLResponse)
async def writer_security_page(request: Request, user: dict = Depends(require_writer_or_admin_web)):
    return RedirectResponse(url="/writer/profile", status_code=302)


@router.post("/security")
async def writer_security_compatibility(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: dict = Depends(require_writer_or_admin_web),
):
    from app.auth.routes import change_password
    return await change_password(request, current_password, new_password, confirm_password, user)
