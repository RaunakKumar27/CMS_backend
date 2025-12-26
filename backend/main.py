from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from backend.api.v1.router import api_router
from backend.admin.routes import router as admin_router
from backend.services.content_service import get_content
from backend.core.database import content_collection

app = FastAPI()

# Routers
app.include_router(api_router, prefix="/api/v1")
app.include_router(admin_router)

# Templates & static files
templates = Jinja2Templates(directory="backend/templates")
app.mount("/static", StaticFiles(directory="backend/static"), name="static")

# Favicon (avoid 404)
@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

# HOME PAGE
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    contents = await content_collection.find().to_list(100)
    for c in contents:
        c["_id"] = str(c["_id"])

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "contents": contents,
        },
    )

# VIEW CONTENT
@app.get("/content/{content_id}", response_class=HTMLResponse)
async def view_content(content_id: str, request: Request):
    content = await get_content(content_id)

    return templates.TemplateResponse(
        content["template"],
        {
            "request": request,
            "content": content,
        }
    )
