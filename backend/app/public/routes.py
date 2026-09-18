from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from bson import ObjectId
from app.core.database import (
    articles_collection,
    categories_collection,
    ensure_database_available,
    settings_collection,
    users_collection,
    web_stories_collection,
)
from app.core.auth import get_current_user_from_request
from app.core.templates import templates

router = APIRouter(tags=["Public Media Website"])

async def get_common_public_context(request: Request):
    """Retrieves common context data like active categories, system settings, and current user."""
    await ensure_database_available()
    categories = await categories_collection.find({"is_active": True}).sort("order", 1).to_list(100)
    for c in categories:
        c["_id"] = str(c["_id"])
        
    settings = await settings_collection.find_one({})
    if not settings:
        settings = {"site_name": "DO Record", "breaking_news_active": False}
        
    current_user = await get_current_user_from_request(request)
    breaking_articles = await articles_collection.find({
        "status": "published",
        "is_breaking": True,
    }).sort("published_at", -1).limit(10).to_list(10)
    for article in breaking_articles:
        article["_id"] = str(article["_id"])
    return {
        "request": request,
        "categories": categories,
        "settings": settings,
        "current_user": current_user,
        "breaking_articles": breaking_articles,
    }


# ==========================================
# HOMEPAGE
# ==========================================
@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    ctx = await get_common_public_context(request)
    ctx["current_page"] = "home"
    
    # 1. Hero Article (Either explicitly pinned in settings or highest featured/newest)
    hero_article = None
    settings = ctx.get("settings", {})
    if settings.get("hero_article_id"):
        try:
            hero_article = await articles_collection.find_one({
                "_id": ObjectId(settings["hero_article_id"]),
                "status": "published"
            })
        except Exception:
            pass
            
    if not hero_article:
        hero_article = await articles_collection.find_one({"status": "published", "is_featured": True}, sort=[("published_at", -1)])
    if not hero_article:
        hero_article = await articles_collection.find_one({"status": "published"}, sort=[("published_at", -1)])
        
    if hero_article:
        hero_article["_id"] = str(hero_article["_id"])
    ctx["hero_article"] = hero_article
    
    # 2. Latest Published Articles (excluding hero)
    hero_id = hero_article["_id"] if hero_article else None
    query = {"status": "published"}
    if hero_id:
        query["_id"] = {"$ne": ObjectId(hero_id)}
        
    latest_articles = await articles_collection.find(query).sort("published_at", -1).to_list(12)
    for a in latest_articles:
        a["_id"] = str(a["_id"])
    ctx["latest_articles"] = latest_articles
    
    # 3. Trending Articles (by views_count)
    trending = await articles_collection.find({"status": "published"}).sort("views_count", -1).to_list(6)
    for t in trending:
        t["_id"] = str(t["_id"])
    ctx["trending_articles"] = trending

    # 4. Web Stories (chosen in the CMS; newest stories appear first)
    web_stories = await web_stories_collection.find({"status": "published"}).sort("published_at", -1).to_list(12)
    for story in web_stories:
        story["_id"] = str(story["_id"])
    ctx["web_stories"] = web_stories

    # 5. Category Sections
    category_sections = []
    for cat in ctx["categories"][:5]:
        cat_articles = await articles_collection.find({
            "category_id": cat["_id"],
            "status": "published"
        }).sort("published_at", -1).to_list(4)
        
        for ca in cat_articles:
            ca["_id"] = str(ca["_id"])
            
        category_sections.append({
            "category": cat,
            "articles": cat_articles
        })
    ctx["category_sections"] = category_sections
    
    return templates.TemplateResponse(request=request, name="public/home.html", context=ctx)


# ==========================================
# WEB STORIES ARCHIVE
# ==========================================
@router.get("/stories", response_class=HTMLResponse)
async def stories_page(request: Request):
    ctx = await get_common_public_context(request)
    ctx["current_page"] = "stories"
    stories = await articles_collection.find({
        "status": "published",
        "is_web_story": True,
    }).sort("published_at", -1).to_list(60)
    for story in stories:
        story["_id"] = str(story["_id"])
    ctx["stories"] = stories
    return templates.TemplateResponse(request=request, name="public/stories.html", context=ctx)


# ==========================================
# ARTICLE DETAIL PAGE
# ==========================================
@router.get("/article/{slug}", response_class=HTMLResponse)
async def article_detail(slug: str, request: Request):
    ctx = await get_common_public_context(request)
    
    article = await articles_collection.find_one({"slug": slug})
    if not article or article.get("status") != "published":
        # Allow writers/admins to preview non-published articles
        current_user = ctx.get("current_user")
        if not current_user or (article and current_user.get("role") == "writer" and str(current_user["_id"]) != article.get("author_id")):
            raise HTTPException(status_code=404, detail="Article not found or not published.")
            
    if not article:
        raise HTTPException(status_code=404, detail="Article not found.")
        
    article_id = article["_id"]
    article["_id"] = str(article["_id"])
    
    # Increment View Count (atomic)
    await articles_collection.update_one({"_id": article_id}, {"$inc": {"views_count": 1}})
    article["views_count"] = article.get("views_count", 0) + 1
    
    ctx["article"] = article
    
    # Related Articles in same category
    related = await articles_collection.find({
        "category_id": article["category_id"],
        "status": "published",
        "_id": {"$ne": article_id}
    }).sort("published_at", -1).to_list(4)
    for r in related:
        r["_id"] = str(r["_id"])
    ctx["related_articles"] = related
    
    # Trending sidebar
    trending = await articles_collection.find({"status": "published"}).sort("views_count", -1).to_list(5)
    for t in trending:
        t["_id"] = str(t["_id"])
    ctx["trending_articles"] = trending
    
    return templates.TemplateResponse(request=request, name="public/article_detail.html", context=ctx)


# ==========================================
# CATEGORY PAGE
# ==========================================
@router.get("/category/{slug}", response_class=HTMLResponse)
async def category_page(slug: str, request: Request):
    ctx = await get_common_public_context(request)
    
    category = await categories_collection.find_one({"slug": slug})
    if not category:
        raise HTTPException(status_code=404, detail="Category not found.")
    category["_id"] = str(category["_id"])
    ctx["category"] = category
    
    articles = await articles_collection.find({
        "category_id": category["_id"],
        "status": "published"
    }).sort("published_at", -1).to_list(50)
    for a in articles:
        a["_id"] = str(a["_id"])
    ctx["articles"] = articles
    
    return templates.TemplateResponse(request=request, name="public/category_page.html", context=ctx)


# ==========================================
# TRENDING PAGE
# ==========================================
@router.get("/trending", response_class=HTMLResponse)
async def trending_page(request: Request, page: int = 1):
    ctx = await get_common_public_context(request)
    ctx["current_page"] = "trending"

    page_size = 12
    current_page = max(page, 1)
    total_articles = await articles_collection.count_documents({"status": "published"})
    total_pages = max((total_articles + page_size - 1) // page_size, 1)
    current_page = min(current_page, total_pages)
    articles = await articles_collection.find({"status": "published"}).sort(
        [("views_count", -1), ("published_at", -1)]
    ).skip((current_page - 1) * page_size).limit(page_size).to_list(page_size)
    for a in articles:
        a["_id"] = str(a["_id"])
    ctx["page"] = current_page
    ctx["total_pages"] = total_pages
    ctx["total_articles"] = total_articles
    ctx["articles"] = articles
    
    return templates.TemplateResponse(request=request, name="public/trending.html", context=ctx)


# ==========================================
# GLOBAL SEARCH
# ==========================================
@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = ""):
    ctx = await get_common_public_context(request)
    query_str = q.strip()
    ctx["search_query"] = query_str
    
    if not query_str:
        ctx["articles"] = []
        return templates.TemplateResponse(request=request, name="public/search_results.html", context=ctx)
        
    regex_pattern = {"$regex": query_str, "$options": "i"}
    mongo_query = {
        "status": "published",
        "$or": [
            {"title": regex_pattern},
            {"excerpt": regex_pattern},
            {"body": regex_pattern},
            {"category_name": regex_pattern},
            {"author_name": regex_pattern},
            {"tags": regex_pattern},
        ]
    }
    
    articles = await articles_collection.find(mongo_query).sort("published_at", -1).to_list(50)
    for a in articles:
        a["_id"] = str(a["_id"])
    ctx["articles"] = articles
    
    return templates.TemplateResponse(request=request, name="public/search_results.html", context=ctx)


# ==========================================
# STATIC PAGES (ABOUT, CONTACT, PRIVACY, TERMS)
# ==========================================
@router.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    ctx = await get_common_public_context(request)
    ctx["title"] = "About DO Record"
    ctx["content_body"] = """
    <p><strong>DO Record</strong> is a leading independent digital news organization dedicated to fast, accurate, and impactful journalism. Founded in 2026, our newsroom operates round-the-clock to cover global developments, political reforms, emerging technology, and financial markets.</p>
    <h3>Our Mission</h3>
    <p>To empower global citizens with verified truth, objective reporting, and critical investigative insight. We adhere strictly to high editorial integrity and non-partisan news standards.</p>
    """
    return templates.TemplateResponse(request=request, name="public/static_page.html", context=ctx)

@router.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request):
    ctx = await get_common_public_context(request)
    ctx["title"] = "Editorial Desk & Contact"
    ctx["content_body"] = """
    <p>Have a news tip, press release, or editorial feedback? Reach out directly to the DO Record newsroom desk.</p>
    <div style="background:#f1f5f9; padding:1.5rem; border-radius:8px; margin:1.5rem 0;">
      <p><strong>Newsroom Hotline:</strong> +91 22 8888 2026</p>
      <p><strong>Editorial Email:</strong> desk@dorecord.com</p>
      <p><strong>Press Releases:</strong> press@dorecord.com</p>
      <p><strong>Headquarters:</strong> Media Center Tower, Floor 14, Financial Hub, Mumbai 400051</p>
    </div>
    """
    return templates.TemplateResponse(request=request, name="public/static_page.html", context=ctx)

@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    ctx = await get_common_public_context(request)
    ctx["title"] = "Privacy Policy"
    ctx["content_body"] = "<p>DO Record values reader privacy. We do not sell personal data or track readers across third-party networks. Standard analytics cookies are used solely for measuring article popularity and system performance.</p>"
    return templates.TemplateResponse(request=request, name="public/static_page.html", context=ctx)

@router.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    ctx = await get_common_public_context(request)
    ctx["title"] = "Terms of Service"
    ctx["content_body"] = "<p>All news articles, original videos, graphic media, and reports published on DO Record are protected by international copyright laws. Reproduction without prior written authorization from DO Record Editorial Management is strictly prohibited.</p>"
    return templates.TemplateResponse(request=request, name="public/static_page.html", context=ctx)
