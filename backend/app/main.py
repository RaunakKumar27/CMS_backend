import os
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pymongo.errors import PyMongoError

import mimetypes

mimetypes.add_type("image/svg+xml", ".svg")

from app.public.routes import router as public_router, home_page
from app.auth.routes import router as auth_router
from app.admin.routes import router as admin_router
from app.writer.routes import router as writer_router
from app.web_stories.routes import admin_router as web_stories_admin_router, writer_router as web_stories_writer_router, public_router as web_stories_public_router
from app.api.v1.router import api_router
from app.core.templates import templates
from app.core.config import settings
from app.core.database import (
    DatabaseConfigurationError,
    DatabaseUnavailableError,
    close_database,
    verify_database_connection,
)

app = FastAPI(
    title="DO Record CMS API",
    description="Backend API for DO Record Media Channel CMS",
    version="1.0.0",
)

# Dynamic resolution of static files & uploads directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(BASE_DIR, "static")
if not os.path.exists(static_dir):
    static_dir = os.path.join(os.path.dirname(BASE_DIR), "static")

uploads_dir = os.path.join(static_dir, "uploads")
os.makedirs(uploads_dir, exist_ok=True)


@app.get("/static/images/default_avatar.png")
async def default_avatar():
    return FileResponse(
        os.path.join(static_dir, "assets", "dorecord-logo.svg"),
        media_type="image/svg+xml",
    )


app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
async def verify_mongodb_on_startup():
    if not settings.VERIFY_DATABASE_ON_STARTUP:
        raise RuntimeError("VERIFY_DATABASE_ON_STARTUP must remain enabled")
    await verify_database_connection()


@app.on_event("shutdown")
async def close_mongodb_on_shutdown():
    await close_database()

# Favicon
@app.get("/favicon.ico")
async def favicon():
    favicon_path = os.path.join(static_dir, "assets", "dorecord-logo.svg")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/svg+xml")
    return Response(status_code=204)

# Health Check Endpoint
@app.get("/health")
async def health_check():
    if not await verify_database_connection():
        raise HTTPException(status_code=503, detail="Database health check failed")
    return {
        "status": "ok",
        "service": "DO Record CMS API"
    }

# Root Endpoint (Supports both API JSON checks & HTML news homepage)
@app.get("/")
async def root_endpoint(request: Request):
    accept_header = request.headers.get("accept", "")
    if "text/html" not in accept_header and "application/json" in accept_header:
        return {
            "message": "DO Record CMS API is running",
            "status": "ok"
        }
    return await home_page(request)

# Routers
app.include_router(public_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(writer_router)
app.include_router(web_stories_admin_router)
app.include_router(web_stories_writer_router)
app.include_router(web_stories_public_router)
app.include_router(api_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api")


# Exception Handlers
@app.exception_handler(StarletteHTTPException)
async def custom_404_handler(request: Request, exc):
    if exc.status_code != 404:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return HTMLResponse(
                content="""
                <!doctype html>
                <html lang="en">
                    <head><meta charset="utf-8"><title>404 - Page Not Found</title></head>
                    <body>
                        <main style="max-width: 42rem; margin: 10vh auto; padding: 2rem; font-family: sans-serif; text-align: center;">
                            <h1>404</h1>
                            <h2>Story or Page Not Found</h2>
                            <p>The news article, category, or CMS route you requested does not exist or has been archived.</p>
                            <a href="/">Return to Homepage</a>
                        </main>
                    </body>
                </html>
                """,
                status_code=404,
    )


@app.exception_handler(DatabaseConfigurationError)
@app.exception_handler(DatabaseUnavailableError)
@app.exception_handler(PyMongoError)
async def database_error_handler(request: Request, exc: Exception):
    if isinstance(exc, PyMongoError):
        from app.core.database import _log_connection_failure
        _log_connection_failure(exc)
    return HTMLResponse(
                content="""
                <!doctype html>
                <html lang="en">
                    <head><meta charset="utf-8"><title>DO Record - Database unavailable</title></head>
                    <body>
                        <main style="max-width: 42rem; margin: 10vh auto; padding: 2rem; font-family: sans-serif;">
                            <h1>Database connection unavailable.</h1>
                            <p>Please check MongoDB configuration and connectivity.</p>
                        </main>
                    </body>
                </html>
                """,
                status_code=503,
    )
