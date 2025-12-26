from fastapi import APIRouter, Request, Form, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from bson import ObjectId
from backend.core.templates import templates
from backend.models.content import ContentCreate, ContentUpdate
from backend.services.content_service import (
    create_content,
    get_content,
    update_content,
)
from backend.core.database import content_collection

router = APIRouter(prefix="/admin", tags=["Admin"])


# =====================================================
# DASHBOARD
# =====================================================

@router.get("/dashboard")
async def dashboard(request: Request):
    count = await content_collection.count_documents({})
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
        }
    )

# =====================================================
# LIST CONTENT (VIEW ALL) ✅
# =====================================================

@router.get("/content")
async def list_content(request: Request):
    contents = await content_collection.find().to_list(100)
    for c in contents:
        c["_id"] = str(c["_id"])

    return templates.TemplateResponse(
        "admin/content_list.html",
        {
            "request": request,
            "contents": contents
        }
    )

# =====================================================
# CREATE CONTENT
# =====================================================

@router.get("/content/new")
def new_content_form(request: Request):
    return templates.TemplateResponse(
        "admin/content_form.html",
        {
            "request": request,
            "content": None,
            "action": "/admin/content"
        }
    )


@router.post("/content")
async def create_content_admin(
    title: str = Form(...),
    body: str = Form(...),
    author: str = Form(...),
    tags: str = Form(""),
    template: str = Form("page.html"),
):
    data = ContentCreate(
        title=title,
        body=body,
        author=author,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        template=template,
    )

    await create_content(data)
    return RedirectResponse("/admin/content", status_code=303)

# =====================================================
# EDIT / UPDATE CONTENT
# =====================================================

@router.get("/content/{content_id}/edit")
async def edit_content_form(request: Request, content_id: str):
    content = await get_content(content_id)

    return templates.TemplateResponse(
        "admin/content_form.html",
        {
            "request": request,
            "content": content,
            "action": f"/admin/content/{content_id}"
        }
    )


@router.post("/content/{content_id}")
async def update_content_admin(
    content_id: str,
    title: str = Form(...),
    body: str = Form(...),
    author: str = Form(...),
    tags: str = Form(""),
    template: str = Form("page.html"),
):
    data = ContentUpdate(
        title=title,
        body=body,
        author=author,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        template=template,
    )

    await update_content(content_id, data)
    return RedirectResponse("/admin/content", status_code=303)

# =====================================================
# DELETE CONTENT
# =====================================================

@router.post("/content/{content_id}/delete")
async def delete_content_admin(content_id: str):
    await content_collection.delete_one(
        {"_id": ObjectId(content_id)}
    )
    return RedirectResponse("/admin/content", status_code=303)

