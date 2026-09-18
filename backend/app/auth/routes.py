from fastapi import APIRouter, Request, Form, Response, UploadFile, File, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from datetime import datetime, timedelta
from typing import Optional
from bson import ObjectId
from app.core.database import (
    users_collection,
    sessions_collection,
    password_resets_collection,
    writer_applications_collection,
    activation_tokens_collection,
)
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    generate_random_token,
    validate_new_password,
)
from app.core.auth import get_current_user_from_request, require_user_web
from app.services.audit_service import log_activity
from app.services.upload_service import save_profile_photo
from app.core.templates import templates

router = APIRouter(tags=["Authentication & Registration"])


def _account_redirect(user: dict, message: str, error: bool = True) -> RedirectResponse:
    destination = "/admin/settings" if user.get("role") == "super_admin" else "/writer/profile"
    status_value = "error" if error else "success"
    return RedirectResponse(
        url=f"{destination}?msg={message}&status={status_value}",
        status_code=303,
    )


@router.get("/account/change-password")
async def change_password_page(user: dict = Depends(require_user_web)):
    destination = "/admin/settings" if user.get("role") == "super_admin" else "/writer/profile"
    return RedirectResponse(url=destination, status_code=302)


@router.post("/account/change-password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: dict = Depends(require_user_web),
):
    user_id = str(user["_id"])
    stored_user = await users_collection.find_one({"_id": ObjectId(user_id)}, {"password": 1, "username": 1, "role": 1})
    if not stored_user or not verify_password(current_password, stored_user.get("password", "")):
        return _account_redirect(user, "Current+password+is+incorrect.")
    if not validate_new_password(new_password):
        return _account_redirect(user, "Password+does+not+meet+the+required+security+requirements.")
    if new_password != confirm_password:
        return _account_redirect(user, "New+passwords+do+not+match.")
    if verify_password(new_password, stored_user["password"]):
        return _account_redirect(user, "New+password+must+be+different+from+your+current+password.")

    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"password": hash_password(new_password)}},
    )
    await sessions_collection.delete_many({"user_id": user_id})
    await log_activity(user, "PASSWORD_CHANGED", "Password changed", request=request)
    response = RedirectResponse(url="/login?msg=Password+changed+successfully.+Please+login+again.", status_code=303)
    response.delete_cookie("access_token")
    return response

# ==========================================
# PUBLIC WRITER REGISTRATION (/become-a-writer)
# ==========================================
@router.get("/become-a-writer", response_class=HTMLResponse)
@router.get("/register/writer", response_class=HTMLResponse)
async def writer_registration_page(request: Request):
    from app.public.routes import get_common_public_context
    ctx = await get_common_public_context(request)
    ctx["form_data"] = None
    ctx["error"] = None
    return templates.TemplateResponse(request=request, name="public/register.html", context=ctx)


@router.post("/become-a-writer")
@router.post("/register/writer")
async def process_writer_registration(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    city: str = Form(""),
    country: str = Form(""),
    bio: str = Form(...),
    areas_of_interest: str = Form(...),
    writing_experience: str = Form(""),
    portfolio_url: str = Form(""),
    linkedin_url: str = Form(""),
    password: str = Form(...),
    confirm_password: str = Form(...),
    photo_file: Optional[UploadFile] = File(None),
):
    from app.public.routes import get_common_public_context
    ctx = await get_common_public_context(request)
    email_clean = email.strip().lower()
    form_data = {
        "full_name": full_name, "email": email, "phone": phone, "city": city,
        "country": country, "bio": bio, "areas_of_interest": areas_of_interest,
        "writing_experience": writing_experience, "portfolio_url": portfolio_url,
        "linkedin_url": linkedin_url
    }
    ctx["form_data"] = form_data
    
    # 1. Duplicate email check across active users and existing applications
    existing_user = await users_collection.find_one({"email": email_clean})
    if existing_user:
        ctx["error"] = "An account with this email address already exists. Please login."
        return templates.TemplateResponse(request=request, name="public/register.html", context=ctx)
        
    existing_app = await writer_applications_collection.find_one({"email": email_clean, "status": {"$in": ["PENDING", "UNDER_REVIEW"]}})
    if existing_app:
        ctx["error"] = "A Writer application for this email address is already under review."
        return templates.TemplateResponse(request=request, name="public/register.html", context=ctx)

    if password != confirm_password:
        ctx["error"] = "Passwords do not match."
        return templates.TemplateResponse(request=request, name="public/register.html", context=ctx)

    if len(password) < 8:
        ctx["error"] = "Password must be at least 8 characters long."
        return templates.TemplateResponse(request=request, name="public/register.html", context=ctx)

    # 2. Upload Profile Photo if provided
    avatar_url = "/static/images/default_avatar.png"
    if photo_file and photo_file.filename:
        try:
            avatar_url = await save_profile_photo(photo_file)
        except HTTPException as e:
            ctx["error"] = e.detail
            return templates.TemplateResponse(request=request, name="public/register.html", context=ctx)

    # 3. Create Writer Application Document
    app_doc = {
        "full_name": full_name.strip(),
        "email": email_clean,
        "phone": phone.strip(),
        "city": city.strip(),
        "country": country.strip(),
        "bio": bio.strip(),
        "areas_of_interest": areas_of_interest.strip(),
        "writing_experience": writing_experience.strip(),
        "portfolio_url": portfolio_url.strip(),
        "linkedin_url": linkedin_url.strip(),
        "avatar_url": avatar_url,
        "password": hash_password(password),
        "status": "PENDING",
        "admin_notes": "",
        "applicant_feedback": "",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    await writer_applications_collection.insert_one(app_doc)
    await log_activity({"username": email_clean, "role": "applicant"}, "WRITER_APPLICATION_SUBMITTED", f"Submitted application for {full_name.strip()}", request=request)
    
    return templates.TemplateResponse(request=request, name="public/register_success.html", context=ctx)



# ==========================================
# ACCOUNT ACTIVATION FOR APPROVED WRITERS
# ==========================================
@router.get("/activate-account", response_class=HTMLResponse)
async def activate_account_page(request: Request, token: str = ""):
    token_doc = await activation_tokens_collection.find_one({"token": token, "used": False})
    if not token_doc or token_doc.get("expires_at", datetime.utcnow()) < datetime.utcnow():
        return templates.TemplateResponse(request=request, name="auth/activate_account.html", context={"request": request, "invalid": True, "error": "This activation link is invalid or has expired."})
        
    applicant = await writer_applications_collection.find_one({"_id": ObjectId(token_doc["application_id"])})
    if not applicant:
        return templates.TemplateResponse(request=request, name="auth/activate_account.html", context={"request": request, "invalid": True, "error": "Applicant profile not found."})
        
    return templates.TemplateResponse(request=request, name="auth/activate_account.html", context={"request": request, "token": token, "applicant": applicant, "invalid": False})


@router.post("/activate-account")
async def process_account_activation(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    if password != confirm_password:
        return templates.TemplateResponse(request=request, name="auth/activate_account.html", context={"request": request, "token": token, "error": "Passwords do not match."})
        
    if len(password) < 8:
        return templates.TemplateResponse(request=request, name="auth/activate_account.html", context={"request": request, "token": token, "error": "Password must be at least 8 characters long."})
        
    token_doc = await activation_tokens_collection.find_one({"token": token, "used": False})
    if not token_doc or token_doc.get("expires_at", datetime.utcnow()) < datetime.utcnow():
        return templates.TemplateResponse(request=request, name="auth/activate_account.html", context={"request": request, "invalid": True, "error": "Activation token invalid or expired."})
        
    applicant = await writer_applications_collection.find_one({"_id": ObjectId(token_doc["application_id"])})
    if not applicant:
        raise HTTPException(status_code=404, detail="Application record not found.")
        
    # Mark token used
    await activation_tokens_collection.update_one({"_id": token_doc["_id"]}, {"$set": {"used": True}})
    
    # Create or activate user
    from app.models.user import WRITER_PERMISSIONS
    username_base = applicant["email"].split("@")[0]
    user_doc = {
        "username": username_base,
        "email": applicant["email"],
        "password": hash_password(password),
        "name": applicant["full_name"],
        "role": "writer",
        "bio": applicant.get("bio", ""),
        "avatar_url": applicant.get("avatar_url", "/static/images/default_avatar.png"),
        "social_linkedin": applicant.get("linkedin_url", ""),
        "is_active": True,
        "permissions": WRITER_PERMISSIONS,
        "created_at": datetime.utcnow(),
        "last_login": datetime.utcnow(),
    }
    
    await users_collection.update_one(
        {"email": applicant["email"]},
        {"$set": user_doc},
        upsert=True
    )
    
    await writer_applications_collection.update_one(
        {"_id": applicant["_id"]},
        {"$set": {"status": "APPROVED", "updated_at": datetime.utcnow()}}
    )
    
    await log_activity(user_doc, "ACCOUNT_ACTIVATED", f"Writer account activated for {applicant['email']}", request=request)
    return RedirectResponse(url="/login?msg=Account+activated+successfully.+You+may+now+sign+in.", status_code=303)


# ==========================================
# FIRST-RUN SETUP WIZARD
# ==========================================
@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    admin_exists = await users_collection.find_one({"role": "super_admin"})
    if admin_exists:
        return templates.TemplateResponse(request=request, name="auth/setup_disabled.html", context={"request": request, "message": "System setup is already completed."}, status_code=403)
    return templates.TemplateResponse(request=request, name="auth/setup.html", context={"request": request})

@router.post("/setup")
async def process_setup(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    name: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    admin_exists = await users_collection.find_one({"role": "super_admin"})
    if admin_exists:
        raise HTTPException(status_code=403, detail="Setup already completed.")
        
    if password != confirm_password:
        return templates.TemplateResponse(request=request, name="auth/setup.html", context={"request": request, "error": "Passwords do not match.", "username": username, "email": email, "name": name})
        
    if len(password) < 8:
        return templates.TemplateResponse(request=request, name="auth/setup.html", context={"request": request, "error": "Password must be at least 8 characters long.", "username": username, "email": email, "name": name})
        
    from app.models.user import ALL_PERMISSIONS
    admin_user = {
        "username": username.strip(),
        "email": email.strip().lower(),
        "password": hash_password(password),
        "name": name.strip(),
        "role": "super_admin",
        "bio": "Lead System Administrator",
        "avatar_url": "/static/images/default_avatar.png",
        "is_active": True,
        "permissions": ALL_PERMISSIONS,
        "created_at": datetime.utcnow(),
        "last_login": datetime.utcnow(),
    }
    
    await users_collection.insert_one(admin_user)
    await log_activity(admin_user, "SYSTEM_INITIALIZED", "First-Run Setup Completed", request=request)
    return RedirectResponse(url="/login?msg=Setup+completed.+Please+login.", status_code=303)


# ==========================================
# LOGIN WITH PENDING APPLICATION CHECK
# ==========================================
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "", msg: str = "", error: str = ""):
    current_user = await get_current_user_from_request(request)
    if current_user:
        if current_user.get("role") == "super_admin":
            return RedirectResponse(url="/admin", status_code=302)
        return RedirectResponse(url="/writer", status_code=302)
        
    return templates.TemplateResponse(request=request, name="auth/login.html", context={"request": request, "next": next, "msg": msg, "error": error})

@router.post("/login")
async def process_login(
    request: Request,
    response: Response,
    identity: str = Form(...), # Email or Username
    password: str = Form(...),
    remember_me: bool = Form(False),
    next: str = Form(""),
):
    identity_clean = identity.strip()
    user = await users_collection.find_one({
        "$or": [
            {"email": identity_clean.lower()},
            {"username": identity_clean}
        ]
    })
    
    # Check if login credentials fail: Check if email is associated with a Writer Application!
    if not user or not verify_password(password, user["password"]):
        # Check writer applications
        app_record = await writer_applications_collection.find_one({
            "email": identity_clean.lower()
        })
        
        if app_record:
            app_status = app_record.get("status", "PENDING")
            if app_status in ["PENDING", "UNDER_REVIEW"]:
                return templates.TemplateResponse(request=request, name="auth/login.html", context={
                        "request": request,
                        "error": "Your Writer application is currently under review by the DO Record administration team. Please wait for approval.",
                        "identity": identity
                    }, status_code=403)
            elif app_status == "REJECTED":
                feedback = app_record.get("applicant_feedback", "Application was not approved.")
                return templates.TemplateResponse(request=request, name="auth/login.html", context={
                        "request": request,
                        "error": f"Your Writer application was not approved. Feedback: {feedback}",
                        "identity": identity
                    }, status_code=403)

        await log_activity({"username": identity_clean, "role": "unknown"}, "LOGIN_FAILED", f"Failed attempt for {identity_clean}", request=request)
        return templates.TemplateResponse(request=request, name="auth/login.html", context={"request": request, "error": "Invalid email/username or password.", "identity": identity, "next": next}, status_code=401)
        
    if not user.get("is_active", True):
        return templates.TemplateResponse(request=request, name="auth/login.html", context={"request": request, "error": "Your account has been suspended or deactivated. Contact Super Admin.", "identity": identity}, status_code=403)
        
    # Create session & token
    user_id = str(user["_id"])
    token_expires = timedelta(days=14) if remember_me else timedelta(hours=12)
    access_token = create_access_token({"sub": user_id, "role": user.get("role")}, expires_delta=token_expires)
    
    session_doc = {
        "user_id": user_id,
        "token": access_token,
        "user_agent": request.headers.get("user-agent", "Unknown"),
        "ip_address": request.client.host if request.client else "127.0.0.1",
        "created_at": datetime.utcnow(),
        "last_active": datetime.utcnow()
    }
    await sessions_collection.insert_one(session_doc)
    
    await users_collection.update_one({"_id": user["_id"]}, {"$set": {"last_login": datetime.utcnow()}})
    await log_activity(user, "USER_LOGIN", f"User {user['username']} logged in successfully", request=request)
    
    target_url = next if next and next.startswith("/") else ("/admin" if user.get("role") == "super_admin" else "/writer")
    resp = RedirectResponse(url=target_url, status_code=303)
    resp.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=14 * 24 * 3600 if remember_me else 12 * 3600,
        samesite="lax",
    )
    return resp


# ==========================================
# LOGOUT
# ==========================================
@router.get("/logout")
@router.post("/logout")
async def logout(request: Request):
    user = await get_current_user_from_request(request)
    token = request.cookies.get("access_token")
    if token:
        await sessions_collection.delete_many({"token": token})
    if user:
        await log_activity(user, "USER_LOGOUT", f"User {user['username']} logged out", request=request)
        
    resp = RedirectResponse(url="/login?msg=You+have+been+logged+out.", status_code=303)
    resp.delete_cookie("access_token")
    return resp


# ==========================================
# FORGOT & RESET PASSWORD
# ==========================================
@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(request=request, name="auth/forgot_password.html", context={"request": request})

@router.post("/forgot-password")
async def process_forgot_password(request: Request, email: str = Form(...)):
    email_clean = email.strip().lower()
    user = await users_collection.find_one({"email": email_clean})
    
    reset_token = generate_random_token()
    if user:
        await password_resets_collection.insert_one({
            "user_id": str(user["_id"]),
            "email": email_clean,
            "token": reset_token,
            "expires_at": datetime.utcnow() + timedelta(minutes=30),
            "used": False,
            "created_at": datetime.utcnow()
        })
        await log_activity(user, "PASSWORD_RESET_REQUESTED", f"Reset token generated for {email_clean}", request=request)
        
    demo_reset_url = f"/reset-password?token={reset_token}" if user else None
    return templates.TemplateResponse(request=request, name="auth/forgot_password_success.html", context={"request": request, "email": email_clean, "demo_reset_url": demo_reset_url})

@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str = ""):
    reset_doc = await password_resets_collection.find_one({"token": token, "used": False})
    if not reset_doc or reset_doc["expires_at"] < datetime.utcnow():
        return templates.TemplateResponse(request=request, name="auth/reset_password.html", context={"request": request, "error": "Invalid or expired password reset link.", "invalid": True})
    return templates.TemplateResponse(request=request, name="auth/reset_password.html", context={"request": request, "token": token})

@router.post("/reset-password")
async def process_reset_password(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    if password != confirm_password:
        return templates.TemplateResponse(request=request, name="auth/reset_password.html", context={"request": request, "token": token, "error": "Passwords do not match."})
        
    if len(password) < 8:
        return templates.TemplateResponse(request=request, name="auth/reset_password.html", context={"request": request, "token": token, "error": "Password must be at least 8 characters long."})
        
    reset_doc = await password_resets_collection.find_one({"token": token, "used": False})
    if not reset_doc or reset_doc["expires_at"] < datetime.utcnow():
        return templates.TemplateResponse(request=request, name="auth/reset_password.html", context={"request": request, "error": "Invalid or expired token.", "invalid": True})
        
    user_id = reset_doc["user_id"]
    new_hash = hash_password(password)
    await users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": {"password": new_hash}})
    await password_resets_collection.update_one({"_id": reset_doc["_id"]}, {"$set": {"used": True}})
    
    await sessions_collection.delete_many({"user_id": user_id})
    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if user:
        await log_activity(user, "PASSWORD_RESET_COMPLETED", "Password successfully reset via token", request=request)
        
    return RedirectResponse(url="/login?msg=Password+updated+successfully.+Please+login.", status_code=303)
