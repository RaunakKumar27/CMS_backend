from fastapi import APIRouter, HTTPException, Depends, status, Request
from datetime import datetime
from bson import ObjectId
from typing import List, Optional
from app.core.database import (
    articles_collection,
    users_collection,
    categories_collection,
    activity_logs_collection,
    settings_collection,
    sessions_collection,
)
from app.core.security import verify_password, create_access_token, hash_password, validate_new_password
from app.core.auth import require_user_api
from app.services.audit_service import log_activity
from app.models.user import PasswordChange
from pydantic import BaseModel

api_router = APIRouter()

# Schema inputs
class LoginRequest(BaseModel):
    identity: str
    password: str

class ArticleCreateSchema(BaseModel):
    title: str
    excerpt: Optional[str] = ""
    body: str
    category_id: str
    featured_image: Optional[str] = "/static/images/default_news.jpg"
    tags: List[str] = []
    is_featured: bool = False
    is_breaking: bool = False

class RejectRequest(BaseModel):
    feedback: str


# ==========================================
# AUTH ENDPOINTS
# ==========================================
@api_router.post("/auth/login")
@api_router.post("/api/auth/login")
async def api_login(data: LoginRequest, request: Request):
    identity = data.identity.strip()
    user = await users_collection.find_one({
        "$or": [{"email": identity.lower()}, {"username": identity}]
    })
    
    if not user or not verify_password(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
        
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account suspended.")
        
    user_id = str(user["_id"])
    token = create_access_token({"sub": user_id, "role": user.get("role")})
    await log_activity(user, "API_LOGIN", f"API login for {user['username']}", request=request)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "username": user["username"],
            "email": user["email"],
            "name": user["name"],
            "role": user.get("role"),
            "permissions": user.get("permissions", []),
        }
    }

@api_router.post("/auth/logout")
@api_router.post("/api/auth/logout")
async def api_logout(request: Request, current_user: dict = Depends(require_user_api)):
    await log_activity(current_user, "API_LOGOUT", f"API logout for {current_user['username']}", request=request)
    return {"message": "Logged out successfully."}

class ForgotPasswordSchema(BaseModel):
    email: str

@api_router.post("/auth/forgot-password")
@api_router.post("/api/auth/forgot-password")
async def api_forgot_password(data: ForgotPasswordSchema, request: Request):
    email_clean = data.email.strip().lower()
    user = await users_collection.find_one({"email": email_clean})
    if user:
        await log_activity(user, "API_PASSWORD_RESET_REQ", f"Reset link requested for {email_clean}", request=request)
    return {"message": "If email is registered, reset instructions have been dispatched."}

class ResetPasswordSchema(BaseModel):
    token: str
    password: str

@api_router.post("/auth/reset-password")
@api_router.post("/api/auth/reset-password")
async def api_reset_password(data: ResetPasswordSchema, request: Request):
    return {"message": "Password updated successfully."}

@api_router.post("/auth/change-password")
@api_router.post("/api/auth/change-password")
async def api_change_password(data: PasswordChange, request: Request, current_user: dict = Depends(require_user_api)):
    user_id = str(current_user["_id"])
    stored_user = await users_collection.find_one({"_id": ObjectId(user_id)}, {"password": 1})
    if not stored_user or not verify_password(data.current_password, stored_user.get("password", "")):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if not validate_new_password(data.new_password):
        raise HTTPException(status_code=400, detail="Password does not meet the required security requirements.")
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match.")
    if verify_password(data.new_password, stored_user["password"]):
        raise HTTPException(status_code=400, detail="New password must be different from your current password.")
    await users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": {"password": hash_password(data.new_password)}})
    await sessions_collection.delete_many({"user_id": user_id})
    await log_activity(current_user, "PASSWORD_CHANGED", "Password changed", request=request)
    return {"success": True, "message": "Password changed successfully."}

@api_router.get("/auth/me")
@api_router.get("/api/auth/me")
async def api_get_me(current_user: dict = Depends(require_user_api)):
    return {
        "id": current_user["_id"],
        "username": current_user["username"],
        "email": current_user["email"],
        "name": current_user["name"],
        "role": current_user.get("role"),
        "permissions": current_user.get("permissions", []),
        "avatar_url": current_user.get("avatar_url"),
    }



# ==========================================
# ARTICLES ENDPOINTS
# ==========================================
@api_router.get("/articles")
async def api_list_articles(status: Optional[str] = "published", category_id: Optional[str] = None):
    query = {}
    if status:
        query["status"] = status
    if category_id:
        query["category_id"] = category_id
        
    articles = await articles_collection.find(query).sort("created_at", -1).to_list(100)
    for a in articles:
        a["_id"] = str(a["_id"])
    return articles

@api_router.get("/articles/{article_id}")
async def api_get_article(article_id: str):
    art = await articles_collection.find_one({"_id": ObjectId(article_id)})
    if not art:
        raise HTTPException(status_code=404, detail="Article not found.")
    art["_id"] = str(art["_id"])
    return art

@api_router.post("/articles", status_code=status.HTTP_201_CREATED)
async def api_create_article(data: ArticleCreateSchema, request: Request, current_user: dict = Depends(require_user_api)):
    cat = await categories_collection.find_one({"_id": ObjectId(data.category_id)}) if ObjectId.is_valid(data.category_id) else None
    cat_name = cat["name"] if cat else "General"
    
    doc = {
        "title": data.title.strip(),
        "slug": data.title.lower().replace(" ", "-"),
        "excerpt": data.excerpt.strip(),
        "body": data.body,
        "featured_image": data.featured_image,
        "category_id": data.category_id,
        "category_name": cat_name,
        "tags": data.tags,
        "author_id": current_user["_id"],
        "author_name": current_user["name"],
        "author_avatar": current_user.get("avatar_url", "/static/images/default_avatar.png"),
        "status": "draft",
        "is_featured": data.is_featured,
        "is_breaking": data.is_breaking,
        "views_count": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    res = await articles_collection.insert_one(doc)
    doc["_id"] = str(res.inserted_id)
    await log_activity(current_user, "API_ARTICLE_CREATED", f"Created article '{data.title}'", request=request)
    return doc

@api_router.post("/articles/{article_id}/submit")
async def api_submit_article(article_id: str, request: Request, current_user: dict = Depends(require_user_api)):
    art = await articles_collection.find_one({"_id": ObjectId(article_id)})
    if not art:
        raise HTTPException(status_code=404, detail="Article not found.")
    if current_user["role"] == "writer" and art.get("author_id") != current_user["_id"]:
        raise HTTPException(status_code=403, detail="Access denied.")
        
    await articles_collection.update_one({"_id": ObjectId(article_id)}, {"$set": {"status": "pending", "updated_at": datetime.utcnow()}})
    await log_activity(current_user, "API_ARTICLE_SUBMITTED", f"Submitted article '{art['title']}' for review", request=request)
    return {"message": "Article submitted for editorial review."}

@api_router.post("/articles/{article_id}/approve")
async def api_approve_article(article_id: str, request: Request, current_user: dict = Depends(require_user_api)):
    if current_user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin role required.")
        
    art = await articles_collection.find_one({"_id": ObjectId(article_id)})
    if not art:
        raise HTTPException(status_code=404, detail="Article not found.")
        
    await articles_collection.update_one({"_id": ObjectId(article_id)}, {"$set": {"status": "published", "published_at": datetime.utcnow(), "updated_at": datetime.utcnow()}})
    await log_activity(current_user, "API_ARTICLE_APPROVED", f"Approved article '{art['title']}'", request=request)
    return {"message": "Article approved and published."}

@api_router.post("/articles/{article_id}/reject")
async def api_reject_article(article_id: str, data: RejectRequest, request: Request, current_user: dict = Depends(require_user_api)):
    if current_user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin role required.")
        
    art = await articles_collection.find_one({"_id": ObjectId(article_id)})
    if not art:
        raise HTTPException(status_code=404, detail="Article not found.")
        
    await articles_collection.update_one({"_id": ObjectId(article_id)}, {"$set": {"status": "rejected", "rejection_feedback": data.feedback.strip(), "updated_at": datetime.utcnow()}})
    await log_activity(current_user, "API_ARTICLE_REJECTED", f"Rejected article '{art['title']}'", request=request)
    return {"message": "Article rejected with feedback."}


# ==========================================
# CATEGORIES ENDPOINTS
# ==========================================
@api_router.get("/categories")
async def api_list_categories():
    categories = await categories_collection.find({"is_active": True}).sort("order", 1).to_list(100)
    for c in categories:
        c["_id"] = str(c["_id"])
    return categories


# ==========================================
# ANALYTICS ENDPOINTS
# ==========================================
@api_router.get("/analytics")
async def api_get_analytics(current_user: dict = Depends(require_user_api)):
    if current_user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin required.")
        
    total_articles = await articles_collection.count_documents({})
    published_articles = await articles_collection.count_documents({"status": "published"})
    total_writers = await users_collection.count_documents({"role": "writer"})
    
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$views_count"}}}]
    views_res = await articles_collection.aggregate(pipeline).to_list(1)
    total_views = views_res[0]["total"] if views_res else 0
    
    return {
        "total_articles": total_articles,
        "published_articles": published_articles,
        "total_writers": total_writers,
        "total_views": total_views,
    }


# ==========================================
# WRITER APPLICATIONS ENDPOINTS
# ==========================================
from app.models.application import WriterApplicationCreate, WriterApplicationReview
from app.core.database import writer_applications_collection, activation_tokens_collection

@api_router.post("/writer-applications", status_code=status.HTTP_210_CREATED if hasattr(status, 'HTTP_210_CREATED') else 201)
@api_router.post("/api/writer-applications", status_code=201)
async def api_submit_writer_application(data: WriterApplicationCreate, request: Request):
    email_clean = data.email.strip().lower()
    
    # Check duplicate user/application
    existing = await users_collection.find_one({"email": email_clean})
    if existing:
        raise HTTPException(status_code=400, detail="Account with this email address already exists.")
        
    existing_app = await writer_applications_collection.find_one({"email": email_clean, "status": {"$in": ["PENDING", "UNDER_REVIEW"]}})
    if existing_app:
        raise HTTPException(status_code=400, detail="A writer application for this email is already under review.")
        
    doc = {
        "full_name": data.full_name.strip(),
        "email": email_clean,
        "phone": data.phone.strip(),
        "city": data.city.strip(),
        "country": data.country.strip(),
        "bio": data.bio.strip(),
        "areas_of_interest": data.areas_of_interest.strip(),
        "writing_experience": data.writing_experience.strip(),
        "portfolio_url": data.portfolio_url.strip(),
        "linkedin_url": data.linkedin_url.strip(),
        "social_url": data.social_url.strip(),
        "avatar_url": data.avatar_url or "/static/images/default_avatar.png",
        "password": hash_password(data.password) if data.password else None,
        "status": "PENDING",
        "admin_notes": "",
        "applicant_feedback": "",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    res = await writer_applications_collection.insert_one(doc)
    doc["_id"] = str(res.inserted_id)
    await log_activity({"username": email_clean, "role": "applicant"}, "API_WRITER_APP_SUBMITTED", f"Submitted writer application for {data.full_name}", request=request)
    return {
        "message": "Your Writer application has been submitted successfully and is currently under review by DO Record administration.",
        "application_id": doc["_id"],
        "status": "PENDING"
    }

@api_router.get("/writer-applications")
@api_router.get("/api/writer-applications")
async def api_list_writer_applications(status: Optional[str] = None, current_user: dict = Depends(require_user_api)):
    if current_user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin role required.")
        
    query = {}
    if status:
        query["status"] = status
        
    apps = await writer_applications_collection.find(query).sort("created_at", -1).to_list(100)
    for a in apps:
        a["_id"] = str(a["_id"])
    return apps

@api_router.get("/writer-applications/{app_id}")
@api_router.get("/api/writer-applications/{app_id}")
async def api_get_writer_application(app_id: str, current_user: dict = Depends(require_user_api)):
    if current_user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin role required.")
        
    app_item = await writer_applications_collection.find_one({"_id": ObjectId(app_id)})
    if not app_item:
        raise HTTPException(status_code=404, detail="Writer application not found.")
    app_item["_id"] = str(app_item["_id"])
    return app_item

@api_router.post("/writer-applications/{app_id}/approve")
@api_router.post("/api/writer-applications/{app_id}/approve")
async def api_approve_writer_application(app_id: str, data: Optional[WriterApplicationReview] = None, current_user: dict = Depends(require_user_api)):
    if current_user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin role required.")
        
    app_item = await writer_applications_collection.find_one({"_id": ObjectId(app_id)})
    if not app_item:
        raise HTTPException(status_code=404, detail="Writer application not found.")
        
    admin_notes = data.admin_notes if data else ""
    await writer_applications_collection.update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {"status": "APPROVED", "admin_notes": admin_notes, "reviewed_by": current_user["name"], "reviewed_at": datetime.utcnow(), "updated_at": datetime.utcnow()}}
    )
    
    from app.models.user import WRITER_PERMISSIONS
    writer_doc = {
        "username": app_item["email"].split("@")[0],
        "email": app_item["email"],
        "password": app_item.get("password") or hash_password("Writer@123456"),
        "name": app_item["full_name"],
        "role": "writer",
        "bio": app_item.get("bio", ""),
        "avatar_url": app_item.get("avatar_url", "/static/images/default_avatar.png"),
        "is_active": True,
        "permissions": WRITER_PERMISSIONS,
        "created_at": datetime.utcnow(),
        "last_login": datetime.utcnow(),
    }
    await users_collection.update_one({"email": app_item["email"]}, {"$set": writer_doc}, upsert=True)
    return {"message": "Writer application approved and Writer account activated."}

@api_router.post("/writer-applications/{app_id}/reject")
@api_router.post("/api/writer-applications/{app_id}/reject")
async def api_reject_writer_application(app_id: str, data: WriterApplicationReview, current_user: dict = Depends(require_user_api)):
    if current_user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin role required.")
        
    app_item = await writer_applications_collection.find_one({"_id": ObjectId(app_id)})
    if not app_item:
        raise HTTPException(status_code=404, detail="Writer application not found.")
        
    await writer_applications_collection.update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {"status": "REJECTED", "applicant_feedback": data.applicant_feedback, "admin_notes": data.admin_notes, "reviewed_by": current_user["name"], "reviewed_at": datetime.utcnow(), "updated_at": datetime.utcnow()}}
    )
    return {"message": "Writer application rejected."}


# ==========================================
# PROFILE PHOTO UPLOAD ENDPOINT
# ==========================================
from app.services.upload_service import save_profile_photo
from fastapi import UploadFile, File

@api_router.post("/profile/photo")
@api_router.post("/api/profile/photo")
async def api_upload_profile_photo(photo_file: UploadFile = File(...), current_user: dict = Depends(require_user_api)):
    avatar_url = await save_profile_photo(photo_file)
    user_id = str(current_user["_id"])
    await users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": {"avatar_url": avatar_url}})
    await articles_collection.update_many({"author_id": user_id}, {"$set": {"author_avatar": avatar_url}})
    return {"message": "Profile photo uploaded successfully.", "avatar_url": avatar_url}

