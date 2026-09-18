from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse, RedirectResponse
from datetime import datetime
from bson import ObjectId
from typing import Optional, List
import os
import secrets
from app.core.database import (
    articles_collection,
    users_collection,
    categories_collection,
    tags_collection,
    media_collection,
    notifications_collection,
    activity_logs_collection,
    sessions_collection,
    settings_collection,
)
from app.core.auth import require_super_admin_web
from app.core.security import hash_password
from app.services.audit_service import log_activity
from app.services.upload_service import save_article_image, save_profile_photo
from app.core.templates import templates

router = APIRouter(prefix="/admin", tags=["Super Admin Panel"])

async def get_admin_common_ctx(request: Request, user: dict, active_tab: str = "dashboard"):
    pending_count = await articles_collection.count_documents({"status": "pending"})
    from app.core.database import writer_applications_collection
    pending_apps_count = await writer_applications_collection.count_documents({"status": {"$in": ["PENDING", "UNDER_REVIEW"]}})
    return {
        "request": request,
        "current_user": user,
        "active_tab": active_tab,
        "pending_count": pending_count,
        "pending_apps_count": pending_apps_count,
    }



# ==========================================
# 1. DASHBOARD
# ==========================================
@router.get("", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: dict = Depends(require_super_admin_web)):
    ctx = await get_admin_common_ctx(request, user, "dashboard")
    
    total_articles = await articles_collection.count_documents({})
    published_articles = await articles_collection.count_documents({"status": "published"})
    pending_articles = await articles_collection.count_documents({"status": "pending"})
    draft_articles = await articles_collection.count_documents({"status": "draft"})
    rejected_articles = await articles_collection.count_documents({"status": "rejected"})
    total_writers = await users_collection.count_documents({"role": "writer"})
    total_categories = await categories_collection.count_documents({})
    
    # Views aggregation
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$views_count"}}}]
    views_res = await articles_collection.aggregate(pipeline).to_list(1)
    total_views = views_res[0]["total"] if views_res else 0
    
    ctx["stats"] = {
        "total_articles": total_articles,
        "published_articles": published_articles,
        "pending_articles": pending_articles,
        "draft_articles": draft_articles,
        "rejected_articles": rejected_articles,
        "total_writers": total_writers,
        "total_categories": total_categories,
        "total_views": total_views,
    }
    
    pending_list = await articles_collection.find({"status": "pending"}).sort("updated_at", -1).to_list(10)
    for p in pending_list:
        p["_id"] = str(p["_id"])
    ctx["pending_articles"] = pending_list
    
    recent_logs = await activity_logs_collection.find({}).sort("created_at", -1).to_list(8)
    for r in recent_logs:
        r["_id"] = str(r["_id"])
    ctx["recent_logs"] = recent_logs
    
    return templates.TemplateResponse(request=request, name="admin/dashboard.html", context=ctx)


# ==========================================
# 2. ARTICLE MANAGEMENT & EDITOR
# ==========================================
@router.get("/articles", response_class=HTMLResponse)
async def list_articles(
    request: Request,
    status: Optional[str] = None,
    category_id: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(require_super_admin_web)
):
    tab = f"articles_{status}" if status in ["published", "pending", "draft", "rejected"] else "articles_all"
    ctx = await get_admin_common_ctx(request, user, tab)
    
    query = {}
    if status:
        query["status"] = status
    if category_id:
        query["category_id"] = category_id
    if search:
        query["title"] = {"$regex": search.strip(), "$options": "i"}
        
    articles = await articles_collection.find(query).sort("updated_at", -1).to_list(100)
    for a in articles:
        a["_id"] = str(a["_id"])
    ctx["articles"] = articles
    ctx["current_status"] = status
    ctx["current_cat"] = category_id
    ctx["search_query"] = search
    
    categories = await categories_collection.find({}).to_list(100)
    for c in categories:
        c["_id"] = str(c["_id"])
    ctx["categories"] = categories
    
    return templates.TemplateResponse(request=request, name="admin/articles_list.html", context=ctx)


@router.post("/articles/upload-image")
async def upload_article_image(file: UploadFile = File(...), user: dict = Depends(require_super_admin_web)):
    url = await save_article_image(file)
    return JSONResponse({"success": True, "url": url, "filename": url.rsplit("/", 1)[-1]})


@router.get("/articles/create", response_class=HTMLResponse)
async def create_article_form(request: Request, user: dict = Depends(require_super_admin_web)):
    ctx = await get_admin_common_ctx(request, user, "articles_all")
    categories = await categories_collection.find({}).to_list(100)
    for c in categories:
        c["_id"] = str(c["_id"])
    ctx["categories"] = categories
    ctx["article"] = None
    return templates.TemplateResponse(request=request, name="admin/article_editor.html", context=ctx)


@router.post("/articles/create")
async def process_create_article(
    request: Request,
    title: str = Form(...),
    slug: str = Form(""),
    excerpt: str = Form(""),
    body: str = Form(...),
    category_id: str = Form(...),
    featured_image: str = Form(""),
    tags: str = Form(""),
    is_featured: bool = Form(False),
    is_breaking: bool = Form(False),
    is_web_story: bool = Form(False),
    seo_title: str = Form(""),
    seo_description: str = Form(""),
    seo_keywords: str = Form(""),
    action_type: str = Form("publish"), # "draft" or "publish"
    user: dict = Depends(require_super_admin_web)
):
    final_slug = slug.strip().lower() if slug.strip() else title.lower().replace(" ", "-")
    cat = await categories_collection.find_one({"_id": ObjectId(category_id)}) if ObjectId.is_valid(category_id) else None
    cat_name = cat["name"] if cat else "General"
    
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    status = "published" if action_type == "publish" else "draft"
    
    doc = {
        "title": title.strip(),
        "slug": final_slug,
        "excerpt": excerpt.strip(),
        "body": body,
        "featured_image": featured_image.strip() or "/static/images/default_news.jpg",
        "category_id": category_id,
        "category_name": cat_name,
        "tags": tag_list,
        "author_id": str(user["_id"]),
        "author_name": user["name"],
        "author_avatar": user.get("avatar_url", "/static/images/default_avatar.png"),
        "status": status,
        "is_featured": is_featured,
        "is_breaking": is_breaking,
        "is_web_story": is_web_story,
        "views_count": 0,
        "seo_title": seo_title.strip() or title.strip(),
        "seo_description": seo_description.strip() or excerpt.strip(),
        "seo_keywords": seo_keywords.strip(),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "published_at": datetime.utcnow() if status == "published" else None,
    }
    
    res = await articles_collection.insert_one(doc)
    await log_activity(user, f"ARTICLE_{status.upper()}", f"Article '{title}' created and {status}", request=request)
    return RedirectResponse(url="/admin/articles", status_code=303)


@router.get("/articles/{article_id}", response_class=HTMLResponse)
async def edit_article_form(article_id: str, request: Request, user: dict = Depends(require_super_admin_web)):
    ctx = await get_admin_common_ctx(request, user, "articles_all")
    article = await articles_collection.find_one({"_id": ObjectId(article_id)})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found.")
    article["_id"] = str(article["_id"])
    ctx["article"] = article
    
    categories = await categories_collection.find({}).to_list(100)
    for c in categories:
        c["_id"] = str(c["_id"])
    ctx["categories"] = categories
    
    return templates.TemplateResponse(request=request, name="admin/article_editor.html", context=ctx)


@router.post("/articles/{article_id}")
async def process_update_article(
    article_id: str,
    request: Request,
    title: str = Form(...),
    slug: str = Form(""),
    excerpt: str = Form(""),
    body: str = Form(...),
    category_id: str = Form(...),
    featured_image: str = Form(""),
    tags: str = Form(""),
    is_featured: bool = Form(False),
    is_breaking: bool = Form(False),
    is_web_story: bool = Form(False),
    seo_title: str = Form(""),
    seo_description: str = Form(""),
    seo_keywords: str = Form(""),
    action_type: str = Form("publish"),
    user: dict = Depends(require_super_admin_web)
):
    cat = await categories_collection.find_one({"_id": ObjectId(category_id)}) if ObjectId.is_valid(category_id) else None
    cat_name = cat["name"] if cat else "General"
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    
    existing = await articles_collection.find_one({"_id": ObjectId(article_id)})
    if not existing:
        raise HTTPException(status_code=404, detail="Article not found.")
        
    status = existing.get("status", "draft")
    if action_type == "publish":
        status = "published"
    elif action_type == "draft":
        status = "draft"
    elif action_type == "approve":
        status = "published"
    elif action_type == "unpublish":
        status = "draft"
        
    update_doc = {
        "title": title.strip(),
        "slug": slug.strip() or title.lower().replace(" ", "-"),
        "excerpt": excerpt.strip(),
        "body": body,
        "featured_image": featured_image.strip(),
        "category_id": category_id,
        "category_name": cat_name,
        "tags": tag_list,
        "status": status,
        "is_featured": is_featured,
        "is_breaking": is_breaking,
        "is_web_story": is_web_story,
        "seo_title": seo_title.strip(),
        "seo_description": seo_description.strip(),
        "seo_keywords": seo_keywords.strip(),
        "updated_at": datetime.utcnow(),
    }
    if status == "published" and not existing.get("published_at"):
        update_doc["published_at"] = datetime.utcnow()
        
    await articles_collection.update_one({"_id": ObjectId(article_id)}, {"$set": update_doc})
    await log_activity(user, "ARTICLE_UPDATED", f"Article '{title}' updated (Status: {status})", request=request)
    return RedirectResponse(url="/admin/articles", status_code=303)


@router.post("/articles/{article_id}/approve")
async def approve_article(article_id: str, request: Request, user: dict = Depends(require_super_admin_web)):
    art = await articles_collection.find_one({"_id": ObjectId(article_id)})
    if art:
        await articles_collection.update_one(
            {"_id": ObjectId(article_id)},
            {"$set": {"status": "published", "published_at": datetime.utcnow(), "updated_at": datetime.utcnow()}}
        )
        # Notify writer
        await notifications_collection.insert_one({
            "user_id": art.get("author_id"),
            "title": "Article Approved & Published!",
            "message": f"Your article '{art['title']}' has been approved and published on DO Record.",
            "read": False,
            "created_at": datetime.utcnow()
        })
        await log_activity(user, "ARTICLE_APPROVED", f"Approved article '{art['title']}'", request=request)
    return RedirectResponse(url="/admin/articles", status_code=303)


@router.post("/articles/{article_id}/reject")
async def reject_article(article_id: str, request: Request, feedback: str = Form(...), user: dict = Depends(require_super_admin_web)):
    art = await articles_collection.find_one({"_id": ObjectId(article_id)})
    if art:
        await articles_collection.update_one(
            {"_id": ObjectId(article_id)},
            {"$set": {"status": "rejected", "rejection_feedback": feedback.strip(), "updated_at": datetime.utcnow()}}
        )
        # Notify writer
        await notifications_collection.insert_one({
            "user_id": art.get("author_id"),
            "title": "Article Rejection Feedback",
            "message": f"Your article '{art['title']}' requires modifications: {feedback.strip()}",
            "read": False,
            "created_at": datetime.utcnow()
        })
        await log_activity(user, "ARTICLE_REJECTED", f"Rejected article '{art['title']}' with feedback", request=request)
    return RedirectResponse(url="/admin/articles", status_code=303)


@router.post("/articles/{article_id}/unpublish")
async def unpublish_article(article_id: str, request: Request, user: dict = Depends(require_super_admin_web)):
    art = await articles_collection.find_one({"_id": ObjectId(article_id)})
    if art:
        await articles_collection.update_one({"_id": ObjectId(article_id)}, {"$set": {"status": "draft", "updated_at": datetime.utcnow()}})
        await log_activity(user, "ARTICLE_UNPUBLISHED", f"Unpublished article '{art['title']}'", request=request)
    return RedirectResponse(url="/admin/articles", status_code=303)


@router.post("/articles/{article_id}/delete")
async def delete_article(article_id: str, request: Request, user: dict = Depends(require_super_admin_web)):
    art = await articles_collection.find_one({"_id": ObjectId(article_id)})
    if art:
        await articles_collection.delete_one({"_id": ObjectId(article_id)})
        await log_activity(user, "ARTICLE_DELETED", f"Deleted article '{art['title']}'", request=request)
    return RedirectResponse(url="/admin/articles", status_code=303)


# ==========================================
# 3. WRITERS MANAGEMENT
# ==========================================
@router.get("/writers", response_class=HTMLResponse)
async def list_writers(request: Request, create: bool = False, user: dict = Depends(require_super_admin_web)):
    ctx = await get_admin_common_ctx(request, user, "writers")
    writers = await users_collection.find({"role": "writer"}).to_list(100)
    
    for w in writers:
        w_id = str(w["_id"])
        w["_id"] = w_id
        w["article_count"] = await articles_collection.count_documents({"author_id": w_id})
        w["published_count"] = await articles_collection.count_documents({"author_id": w_id, "status": "published"})
        
    ctx["writers"] = writers
    ctx["show_create"] = create
    return templates.TemplateResponse(request=request, name="admin/writers_list.html", context=ctx)


@router.post("/writers")
async def create_writer(
    request: Request,
    name: str = Form(...),
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    bio: str = Form(""),
    user: dict = Depends(require_super_admin_web)
):
    from app.models.user import WRITER_PERMISSIONS
    writer_doc = {
        "username": username.strip(),
        "email": email.strip().lower(),
        "password": hash_password(password),
        "name": name.strip(),
        "role": "writer",
        "bio": bio.strip(),
        "avatar_url": "/static/images/default_avatar.png",
        "is_active": True,
        "permissions": WRITER_PERMISSIONS,
        "created_at": datetime.utcnow(),
    }
    await users_collection.insert_one(writer_doc)
    await log_activity(user, "WRITER_CREATED", f"Created writer account for {username.strip()}", request=request)
    return RedirectResponse(url="/admin/writers", status_code=303)


@router.post("/writers/{writer_id}/toggle-status")
async def toggle_writer_status(writer_id: str, request: Request, user: dict = Depends(require_super_admin_web)):
    w = await users_collection.find_one({"_id": ObjectId(writer_id)})
    if w:
        new_status = not w.get("is_active", True)
        await users_collection.update_one({"_id": ObjectId(writer_id)}, {"$set": {"is_active": new_status}})
        await log_activity(user, "WRITER_STATUS_CHANGED", f"Toggled status for writer {w['username']} to active={new_status}", request=request)
    return RedirectResponse(url="/admin/writers", status_code=303)


@router.post("/writers/{writer_id}/reset-pwd")
async def reset_writer_password(writer_id: str, request: Request, user: dict = Depends(require_super_admin_web)):
    w = await users_collection.find_one({"_id": ObjectId(writer_id)})
    if w:
        new_hash = hash_password("Writer@123456")
        await users_collection.update_one({"_id": ObjectId(writer_id)}, {"$set": {"password": new_hash}})
        await log_activity(user, "WRITER_PASSWORD_RESET", f"Reset password for writer {w['username']}", request=request)
    return RedirectResponse(url="/admin/writers", status_code=303)


@router.post("/writers/{writer_id}/upload-photo")
async def admin_upload_writer_photo(
    writer_id: str,
    request: Request,
    photo_file: UploadFile = File(...),
    user: dict = Depends(require_super_admin_web)
):
    from app.services.upload_service import save_profile_photo
    writer = await users_collection.find_one({"_id": ObjectId(writer_id)})
    if not writer:
        raise HTTPException(status_code=404, detail="Writer not found.")
        
    avatar_url = await save_profile_photo(photo_file)
    await users_collection.update_one({"_id": ObjectId(writer_id)}, {"$set": {"avatar_url": avatar_url}})
    await articles_collection.update_many({"author_id": writer_id}, {"$set": {"author_avatar": avatar_url}})
    await log_activity(user, "WRITER_PHOTO_UPDATED", f"Super Admin updated profile photo for writer {writer['username']}", request=request)
    return RedirectResponse(url="/admin/writers", status_code=303)


# ==========================================
# 3B. WRITER APPLICATIONS MANAGEMENT
# ==========================================
@router.get("/writer-applications", response_class=HTMLResponse)
async def list_writer_applications(
    request: Request,
    status: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(require_super_admin_web)
):
    ctx = await get_admin_common_ctx(request, user, "writer_applications")
    from app.core.database import writer_applications_collection
    
    query = {}
    if status:
        query["status"] = status
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search.strip(), "$options": "i"}},
            {"email": {"$regex": search.strip(), "$options": "i"}},
            {"areas_of_interest": {"$regex": search.strip(), "$options": "i"}},
        ]
        
    apps = await writer_applications_collection.find(query).sort("created_at", -1).to_list(100)
    for a in apps:
        a["_id"] = str(a["_id"])
    ctx["applications"] = apps
    ctx["current_status"] = status
    ctx["search_query"] = search
    
    # Stats
    total = await writer_applications_collection.count_documents({})
    pending = await writer_applications_collection.count_documents({"status": {"$in": ["PENDING", "UNDER_REVIEW"]}})
    approved = await writer_applications_collection.count_documents({"status": "APPROVED"})
    rejected = await writer_applications_collection.count_documents({"status": "REJECTED"})
    ctx["stats"] = {"total": total, "pending": pending, "approved": approved, "rejected": rejected}
    
    return templates.TemplateResponse(request=request, name="admin/writer_applications.html", context=ctx)


@router.get("/writer-applications/{app_id}", response_class=HTMLResponse)
async def view_writer_application(
    app_id: str,
    request: Request,
    activation_url: Optional[str] = None,
    user: dict = Depends(require_super_admin_web)
):
    ctx = await get_admin_common_ctx(request, user, "writer_applications")
    from app.core.database import writer_applications_collection
    
    app_item = await writer_applications_collection.find_one({"_id": ObjectId(app_id)})
    if not app_item:
        raise HTTPException(status_code=404, detail="Writer application not found.")
        
    app_item["_id"] = str(app_item["_id"])
    ctx["applicant"] = app_item
    ctx["activation_url"] = activation_url
    return templates.TemplateResponse(request=request, name="admin/writer_application_detail.html", context=ctx)


@router.post("/writer-applications/{app_id}/approve")
async def approve_writer_application(
    app_id: str,
    request: Request,
    admin_notes: str = Form(""),
    user: dict = Depends(require_super_admin_web)
):
    from app.core.database import writer_applications_collection, activation_tokens_collection
    from app.models.user import WRITER_PERMISSIONS
    from app.core.security import generate_random_token
    from datetime import timedelta
    
    app_item = await writer_applications_collection.find_one({"_id": ObjectId(app_id)})
    if not app_item:
        raise HTTPException(status_code=404, detail="Application record not found.")
        
    # Generate single-use activation token link
    act_token = generate_random_token()
    await activation_tokens_collection.insert_one({
        "token": act_token,
        "application_id": app_id,
        "email": app_item["email"],
        "expires_at": datetime.utcnow() + timedelta(days=7),
        "used": False,
        "created_at": datetime.utcnow()
    })
    
    # Update application status
    await writer_applications_collection.update_one(
        {"_id": ObjectId(app_id)},
        {
            "$set": {
                "status": "APPROVED",
                "admin_notes": admin_notes.strip(),
                "reviewed_by": user["name"],
                "reviewed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    # Create or update active Writer user account
    username_base = app_item["email"].split("@")[0]
    writer_user_doc = {
        "username": username_base,
        "email": app_item["email"],
        "password": app_item.get("password") or hash_password("Writer@123456"),
        "name": app_item["full_name"],
        "role": "writer",
        "bio": app_item.get("bio", ""),
        "avatar_url": app_item.get("avatar_url", "/static/images/default_avatar.png"),
        "social_linkedin": app_item.get("linkedin_url", ""),
        "is_active": True,
        "permissions": WRITER_PERMISSIONS,
        "created_at": datetime.utcnow(),
        "last_login": datetime.utcnow(),
    }
    
    await users_collection.update_one({"email": app_item["email"]}, {"$set": writer_user_doc}, upsert=True)
    await log_activity(user, "APPLICATION_APPROVED", f"Approved writer application for {app_item['email']}", request=request)
    
    # Redirect back to detail page with activation_url parameter
    activation_url = f"{request.base_url}activate-account?token={act_token}"
    return RedirectResponse(url=f"/admin/writer-applications/{app_id}?msg=Approved", status_code=303)


@router.post("/writer-applications/{app_id}/reject")
async def reject_writer_application(
    app_id: str,
    request: Request,
    applicant_feedback: str = Form(...),
    admin_notes: str = Form(""),
    user: dict = Depends(require_super_admin_web)
):
    from app.core.database import writer_applications_collection
    app_item = await writer_applications_collection.find_one({"_id": ObjectId(app_id)})
    if not app_item:
        raise HTTPException(status_code=404, detail="Application record not found.")
        
    await writer_applications_collection.update_one(
        {"_id": ObjectId(app_id)},
        {
            "$set": {
                "status": "REJECTED",
                "applicant_feedback": applicant_feedback.strip(),
                "admin_notes": admin_notes.strip(),
                "reviewed_by": user["name"],
                "reviewed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    await log_activity(user, "APPLICATION_REJECTED", f"Rejected writer application for {app_item['email']}", request=request)
    return RedirectResponse(url="/admin/writer-applications", status_code=303)



# ==========================================
# 4. CATEGORIES & TAGS
# ==========================================
@router.get("/categories", response_class=HTMLResponse)
async def list_categories(request: Request, user: dict = Depends(require_super_admin_web)):
    ctx = await get_admin_common_ctx(request, user, "categories")
    categories = await categories_collection.find({}).sort("order", 1).to_list(100)
    for c in categories:
        c_id = str(c["_id"])
        c["_id"] = c_id
        c["article_count"] = await articles_collection.count_documents({"category_id": c_id})
        
    ctx["categories"] = categories
    tags = await tags_collection.find({}).to_list(100)
    ctx["tags"] = tags
    return templates.TemplateResponse(request=request, name="admin/categories_tags.html", context=ctx)


@router.post("/categories")
async def create_category(
    request: Request,
    name: str = Form(...),
    slug: str = Form(""),
    description: str = Form(""),
    image_url: str = Form(""),
    user: dict = Depends(require_super_admin_web)
):
    final_slug = slug.strip().lower() if slug.strip() else name.lower().replace(" ", "-")
    cat_doc = {
        "name": name.strip(),
        "slug": final_slug,
        "description": description.strip(),
        "image_url": image_url.strip(),
        "order": (await categories_collection.count_documents({})) + 1,
        "is_active": True,
    }
    await categories_collection.insert_one(cat_doc)
    await log_activity(user, "CATEGORY_CREATED", f"Created category '{name}'", request=request)
    return RedirectResponse(url="/admin/categories", status_code=303)


@router.post("/categories/{cat_id}/delete")
async def delete_category(cat_id: str, request: Request, user: dict = Depends(require_super_admin_web)):
    await categories_collection.delete_one({"_id": ObjectId(cat_id)})
    await log_activity(user, "CATEGORY_DELETED", f"Deleted category {cat_id}", request=request)
    return RedirectResponse(url="/admin/categories", status_code=303)


@router.get("/tags", response_class=HTMLResponse)
async def list_tags(request: Request, user: dict = Depends(require_super_admin_web)):
    return RedirectResponse(url="/admin/categories", status_code=302)


@router.post("/tags")
async def create_tag(request: Request, name: str = Form(...), user: dict = Depends(require_super_admin_web)):
    slug = name.strip().lower().replace(" ", "-")
    await tags_collection.update_one({"slug": slug}, {"$set": {"name": name.strip(), "slug": slug}}, upsert=True)
    await log_activity(user, "TAG_CREATED", f"Created tag '{name}'", request=request)
    return RedirectResponse(url="/admin/categories", status_code=303)


# ==========================================
# 5. MEDIA LIBRARY
# ==========================================
@router.get("/media", response_class=HTMLResponse)
async def list_media(request: Request, user: dict = Depends(require_super_admin_web)):
    ctx = await get_admin_common_ctx(request, user, "media")
    items = await media_collection.find({}).sort("created_at", -1).to_list(100)
    for m in items:
        m["_id"] = str(m["_id"])
    ctx["media_items"] = items
    return templates.TemplateResponse(request=request, name="admin/media_library.html", context=ctx)


@router.post("/media/upload")
async def upload_media(request: Request, file: UploadFile = File(...), user: dict = Depends(require_super_admin_web)):
    upload_dir = "backend/static/uploads"
    os.makedirs(upload_dir, exist_ok=True)
    
    file_ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    unique_filename = f"{secrets.token_hex(8)}.{file_ext}"
    file_path = os.path.join(upload_dir, unique_filename)
    
    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)
        
    file_url = f"/static/uploads/{unique_filename}"
    media_doc = {
        "filename": unique_filename,
        "original_name": file.filename,
        "file_url": file_url,
        "file_type": "image" if file_ext.lower() in ["jpg", "jpeg", "png", "webp", "gif"] else "document",
        "mime_type": file.content_type,
        "file_size": len(contents),
        "uploaded_by_id": str(user["_id"]),
        "uploaded_by_name": user["name"],
        "created_at": datetime.utcnow(),
    }
    await media_collection.insert_one(media_doc)
    await log_activity(user, "MEDIA_UPLOADED", f"Uploaded media file '{file.filename}'", request=request)
    return RedirectResponse(url="/admin/media", status_code=303)


@router.post("/media/{media_id}/delete")
async def delete_media(media_id: str, request: Request, user: dict = Depends(require_super_admin_web)):
    item = await media_collection.find_one({"_id": ObjectId(media_id)})
    if item:
        file_path = os.path.join("backend/static/uploads", item["filename"])
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        await media_collection.delete_one({"_id": ObjectId(media_id)})
        await log_activity(user, "MEDIA_DELETED", f"Deleted media '{item['filename']}'", request=request)
    return RedirectResponse(url="/admin/media", status_code=303)


# ==========================================
# 6. HOMEPAGE MANAGER
# ==========================================
@router.get("/homepage", response_class=HTMLResponse)
async def homepage_manager(request: Request, user: dict = Depends(require_super_admin_web)):
    ctx = await get_admin_common_ctx(request, user, "homepage")
    settings = await settings_collection.find_one({})
    ctx["settings"] = settings
    
    articles = await articles_collection.find({"status": "published"}).to_list(100)
    for a in articles:
        a["_id"] = str(a["_id"])
    ctx["articles"] = articles
    
    hero_art = None
    if settings and settings.get("hero_article_id"):
        hero_art = await articles_collection.find_one({"_id": ObjectId(settings["hero_article_id"])})
    ctx["hero_article"] = hero_art
    
    return templates.TemplateResponse(request=request, name="admin/homepage_manager.html", context=ctx)


@router.post("/homepage")
async def process_homepage_manager(
    request: Request,
    breaking_news_text: str = Form(...),
    breaking_news_active: bool = Form(False),
    hero_article_id: str = Form(""),
    user: dict = Depends(require_super_admin_web)
):
    update_doc = {
        "breaking_news_text": breaking_news_text.strip(),
        "breaking_news_active": breaking_news_active,
        "hero_article_id": hero_article_id if hero_article_id else None,
        "updated_at": datetime.utcnow(),
    }
    await settings_collection.update_one({}, {"$set": update_doc}, upsert=True)
    await log_activity(user, "HOMEPAGE_UPDATED", "Updated breaking news ticker & hero article configuration", request=request)
    return RedirectResponse(url="/admin/homepage", status_code=303)


# ==========================================
# 7. ANALYTICS
# ==========================================
@router.get("/analytics", response_class=HTMLResponse)
async def channel_analytics(request: Request, user: dict = Depends(require_super_admin_web)):
    ctx = await get_admin_common_ctx(request, user, "analytics")
    
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$views_count"}}}]
    views_res = await articles_collection.aggregate(pipeline).to_list(1)
    total_views = views_res[0]["total"] if views_res else 0
    published_count = await articles_collection.count_documents({"status": "published"})
    
    ctx["total_views"] = total_views
    ctx["published_count"] = published_count
    
    top_articles = await articles_collection.find({"status": "published"}).sort("views_count", -1).to_list(10)
    for t in top_articles:
        t["_id"] = str(t["_id"])
    ctx["top_articles"] = top_articles
    
    writers = await users_collection.find({"role": "writer"}).to_list(100)
    writer_stats = []
    for w in writers:
        w_id = str(w["_id"])
        w_pub = await articles_collection.count_documents({"author_id": w_id, "status": "published"})
        w_views = await articles_collection.aggregate([
            {"$match": {"author_id": w_id}},
            {"$group": {"_id": None, "total": {"$sum": "$views_count"}}}
        ]).to_list(1)
        
        writer_stats.append({
            "name": w["name"],
            "avatar_url": w.get("avatar_url"),
            "published_count": w_pub,
            "total_views": w_views[0]["total"] if w_views else 0
        })
    ctx["writer_stats"] = sorted(writer_stats, key=lambda x: x["total_views"], reverse=True)
    
    return templates.TemplateResponse(request=request, name="admin/analytics.html", context=ctx)


# ==========================================
# 8. NOTIFICATIONS
# ==========================================
@router.get("/notifications", response_class=HTMLResponse)
async def list_notifications(request: Request, user: dict = Depends(require_super_admin_web)):
    ctx = await get_admin_common_ctx(request, user, "notifications")
    notifs = await notifications_collection.find({}).sort("created_at", -1).to_list(100)
    for n in notifs:
        n["_id"] = str(n["_id"])
    ctx["notifications"] = notifs
    return templates.TemplateResponse(request=request, name="admin/notifications.html", context=ctx)


@router.post("/notifications/mark-read")
async def mark_notifications_read(request: Request, user: dict = Depends(require_super_admin_web)):
    await notifications_collection.update_many({}, {"$set": {"read": True}})
    return RedirectResponse(url="/admin/notifications", status_code=303)


# ==========================================
# 9. ACTIVITY LOGS
# ==========================================
@router.get("/activity-logs", response_class=HTMLResponse)
async def list_activity_logs(request: Request, user: dict = Depends(require_super_admin_web)):
    ctx = await get_admin_common_ctx(request, user, "logs")
    logs = await activity_logs_collection.find({}).sort("created_at", -1).to_list(100)
    for l in logs:
        l["_id"] = str(l["_id"])
    ctx["logs"] = logs
    return templates.TemplateResponse(request=request, name="admin/activity_logs.html", context=ctx)


# ==========================================
# 10. SETTINGS & SECURITY
# ==========================================
@router.get("/settings", response_class=HTMLResponse)
async def admin_settings_page(request: Request, msg: str = "", status: str = "success", user: dict = Depends(require_super_admin_web)):
    ctx = await get_admin_common_ctx(request, user, "settings")
    settings = await settings_collection.find_one({})
    ctx["settings"] = settings
    ctx["msg"] = msg
    ctx["msg_status"] = status
    
    active_sessions = await sessions_collection.find({}).sort("created_at", -1).to_list(100)
    for s in active_sessions:
        s["_id"] = str(s["_id"])
        # get username
        if s.get("user_id"):
            u = await users_collection.find_one({"_id": ObjectId(s["user_id"])})
            s["username"] = u["username"] if u else "Unknown"
        else:
            s["username"] = "Session User"
    ctx["active_sessions"] = active_sessions
    
    from app.models.user import ALL_PERMISSIONS, WRITER_PERMISSIONS
    ctx["permissions_list"] = ALL_PERMISSIONS
    ctx["writer_perms"] = WRITER_PERMISSIONS
    
    return templates.TemplateResponse(request=request, name="admin/settings.html", context=ctx)


@router.post("/settings")
async def update_settings(
    request: Request,
    site_name: str = Form(...),
    site_description: str = Form(""),
    session_timeout_minutes: int = Form(1440),
    user: dict = Depends(require_super_admin_web)
):
    update_doc = {
        "site_name": site_name.strip(),
        "site_description": site_description.strip(),
        "session_timeout_minutes": session_timeout_minutes,
        "updated_at": datetime.utcnow(),
    }
    await settings_collection.update_one({}, {"$set": update_doc}, upsert=True)
    await log_activity(user, "SETTINGS_UPDATED", "Updated channel general settings", request=request)
    return RedirectResponse(url="/admin/settings?msg=System+settings+saved.", status_code=303)


@router.post("/settings/profile-photo")
async def admin_upload_profile_photo(
    request: Request,
    photo_file: UploadFile = File(...),
    user: dict = Depends(require_super_admin_web),
):
    avatar_url = await save_profile_photo(photo_file)
    user_id = str(user["_id"])
    await users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": {"avatar_url": avatar_url}})
    await articles_collection.update_many({"author_id": user_id}, {"$set": {"author_avatar": avatar_url}})
    await log_activity(user, "PROFILE_PHOTO_UPLOADED", "Super Admin uploaded a profile photo", request=request)
    return JSONResponse({"success": True, "url": avatar_url, "filename": avatar_url.rsplit("/", 1)[-1]})


@router.post("/settings/profile-photo/remove")
async def admin_remove_profile_photo(request: Request, user: dict = Depends(require_super_admin_web)):
    user_id = str(user["_id"])
    default_avatar = "/static/images/default_avatar.png"
    await users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": {"avatar_url": default_avatar}})
    await articles_collection.update_many({"author_id": user_id}, {"$set": {"author_avatar": default_avatar}})
    await log_activity(user, "PROFILE_PHOTO_REMOVED", "Super Admin removed the profile photo", request=request)
    return JSONResponse({"success": True, "url": default_avatar})


@router.post("/settings/force-logout")
async def force_logout_session(request: Request, token: str = Form(...), user: dict = Depends(require_super_admin_web)):
    await sessions_collection.delete_many({"token": token})
    await log_activity(user, "FORCE_LOGOUT", "Super Admin forced logout of user session", request=request)
    return RedirectResponse(url="/admin/settings?msg=User+session+terminated.", status_code=303)
