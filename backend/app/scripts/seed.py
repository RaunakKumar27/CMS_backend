import asyncio
from datetime import datetime, timedelta
import random
from app.core.database import (
    users_collection,
    categories_collection,
    tags_collection,
    articles_collection,
    settings_collection,
    notifications_collection,
    activity_logs_collection,
)
from app.core.security import hash_password
from app.models.user import ALL_PERMISSIONS, WRITER_PERMISSIONS

async def seed_database():
    print("[*] Starting DO Record CMS Database Seeding...")

    # 1. Clear existing sample data if requested or seed missing
    # Keep user setup clean
    admin_count = await users_collection.count_documents({"role": "super_admin"})
    if admin_count == 0:
        admin_user = {
            "username": "admin",
            "email": "admin@dorecord.com",
            "password": hash_password("Admin@123456"),
            "name": "Super Admin",
            "role": "super_admin",
            "bio": "Editor-in-Chief & Lead System Administrator for DO Record.",
            "avatar_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=300&q=80",
            "social_twitter": "@dorecord_admin",
            "social_linkedin": "linkedin.com/in/dorecord",
            "is_active": True,
            "permissions": ALL_PERMISSIONS,
            "created_at": datetime.utcnow() - timedelta(days=90),
            "last_login": datetime.utcnow(),
        }
        await users_collection.insert_one(admin_user)
        print("[OK] Created Super Admin: admin@dorecord.com / Admin@123456")

    # Seed Writers
    writers_seed = [
        {
            "username": "rohit_politics",
            "email": "rohit@dorecord.com",
            "password": hash_password("Writer@123456"),
            "name": "Rohit Sharma",
            "role": "writer",
            "bio": "Senior Political Editor covering national policies, parliamentary debates, and elections.",
            "avatar_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=300&q=80",
            "is_active": True,
            "permissions": WRITER_PERMISSIONS,
            "created_at": datetime.utcnow() - timedelta(days=60),
        },
        {
            "username": "priya_tech",
            "email": "priya@dorecord.com",
            "password": hash_password("Writer@123456"),
            "name": "Priya Verma",
            "role": "writer",
            "bio": "Technology & AI Correspondent writing on cybersecurity, emerging tech trends, and Silicon Valley.",
            "avatar_url": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=300&q=80",
            "is_active": True,
            "permissions": WRITER_PERMISSIONS,
            "created_at": datetime.utcnow() - timedelta(days=45),
        },
        {
            "username": "arjun_sports",
            "email": "arjun@dorecord.com",
            "password": hash_password("Writer@123456"),
            "name": "Arjun Kapoor",
            "role": "writer",
            "bio": "Chief Sports Analyst specializing in International Cricket, Football Leagues, and Olympics.",
            "avatar_url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=300&q=80",
            "is_active": True,
            "permissions": WRITER_PERMISSIONS,
            "created_at": datetime.utcnow() - timedelta(days=30),
        },
        {
            "username": "neha_world",
            "email": "neha@dorecord.com",
            "password": hash_password("Writer@123456"),
            "name": "Neha Gupta",
            "role": "writer",
            "bio": "Global Affairs Specialist reporting on international relations, diplomacy, and global economic summits.",
            "avatar_url": "https://images.unsplash.com/photo-1580489944761-15a19d654956?auto=format&fit=crop&w=300&q=80",
            "is_active": True,
            "permissions": WRITER_PERMISSIONS,
            "created_at": datetime.utcnow() - timedelta(days=20),
        },
    ]

    for w in writers_seed:
        existing = await users_collection.find_one({"username": w["username"]})
        if not existing:
            await users_collection.insert_one(w)
            print(f"[OK] Created Writer: {w['username']}")

    # Get sample writers for linking articles
    writers = await users_collection.find({"role": "writer"}).to_list(100)
    admin = await users_collection.find_one({"role": "super_admin"})

    # 2. Categories
    categories_seed = [
        {"name": "India", "slug": "india", "description": "Latest national developments, infrastructure, governance, and policy news.", "order": 1, "image_url": "https://images.unsplash.com/photo-1524492412937-b28074a5d7da?auto=format&fit=crop&w=600&q=80", "is_active": True},
        {"name": "World", "slug": "world", "description": "Global diplomacy, international summits, and geopolitical affairs.", "order": 2, "image_url": "https://images.unsplash.com/photo-1526778548025-fa2f459cd5c1?auto=format&fit=crop&w=600&q=80", "is_active": True},
        {"name": "Politics", "slug": "politics", "description": "In-depth political analysis, elections, parliamentary debates, and policy decisions.", "order": 3, "image_url": "https://images.unsplash.com/photo-1540910419892-4a36d2c3266c?auto=format&fit=crop&w=600&q=80", "is_active": True},
        {"name": "Business", "slug": "business", "description": "Stock markets, corporate earnings, economy, startups, and banking updates.", "order": 4, "image_url": "https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?auto=format&fit=crop&w=600&q=80", "is_active": True},
        {"name": "Technology", "slug": "technology", "description": "Artificial Intelligence, gadgets, software development, cybersecurity, and space exploration.", "order": 5, "image_url": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=600&q=80", "is_active": True},
        {"name": "Sports", "slug": "sports", "description": "Live scores, match analysis, tournament coverage, and athlete interviews.", "order": 6, "image_url": "https://images.unsplash.com/photo-1461896836934-ffe607ba8211?auto=format&fit=crop&w=600&q=80", "is_active": True},
        {"name": "Entertainment", "slug": "entertainment", "description": "Film reviews, box office tracking, celebrity features, and culture.", "order": 7, "image_url": "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?auto=format&fit=crop&w=600&q=80", "is_active": True},
        {"name": "Education", "slug": "education", "description": "Career guidance, exam announcements, higher education trends, and skill development.", "order": 8, "image_url": "https://images.unsplash.com/photo-1523240795612-9a054b0db644?auto=format&fit=crop&w=600&q=80", "is_active": True},
        {"name": "Lifestyle", "slug": "lifestyle", "description": "Health, wellness, travel destinations, food, and modern living.", "order": 9, "image_url": "https://images.unsplash.com/photo-1506126613408-eca07ce68773?auto=format&fit=crop&w=600&q=80", "is_active": True},
    ]

    cat_map = {}
    for cat in categories_seed:
        existing = await categories_collection.find_one({"slug": cat["slug"]})
        if not existing:
            res = await categories_collection.insert_one(cat)
            cat_map[cat["slug"]] = str(res.inserted_id)
        else:
            cat_map[cat["slug"]] = str(existing["_id"])

    print("[OK] Created Categories")

    # 3. Tags
    tags_seed = ["AI", "Elections", "Stock Market", "Cricket", "Global Trade", "Startups", "Cybersecurity", "Cinema", "Climate Change", "Space Tech", "Budget 2026", "Green Energy"]
    for tag in tags_seed:
        slug = tag.lower().replace(" ", "-")
        await tags_collection.update_one({"slug": slug}, {"$set": {"name": tag, "slug": slug}}, upsert=True)
    print("[OK] Created Tags")

    # 4. Articles
    articles_seed = [
        {
            "title": "India Unveils Next-Gen AI Computing Grid Infrastructure Project",
            "slug": "india-unveils-next-gen-ai-computing-grid-infrastructure-project",
            "excerpt": "The government has approved a multi-billion dollar initiative to establish sovereign supercomputing clusters across five major technology hubs.",
            "body": "<p>In a landmark announcement today, the Ministry of Electronics and Information Technology unveiled India's ambitious National Artificial Intelligence Grid. Designed to empower local researchers, startups, and academic institutions, the project deploys high-density GPU clusters powered by renewable energy.</p><h2>Sovereign Compute Capabilities</h2><p>Experts emphasize that securing native AI compute infrastructure is critical for national security and digital independence. Prime Minister commended the initiative, stating that 'India will not only consume AI technologies but lead the global innovation curve in ethical AI development.'</p><p>Key features of the project include:</p><ul><li>100,000+ Enterprise GPU compute capacity</li><li>Open access for verified research institutions</li><li>100% green energy powered data center corridors</li></ul>",
            "featured_image": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80",
            "category_slug": "technology",
            "tags": ["AI", "Startups", "Space Tech"],
            "writer_username": "priya_tech",
            "status": "published",
            "is_featured": True,
            "is_breaking": True,
            "views_count": 4820,
            "seo_title": "India AI Computing Grid Launched - DO Record Tech",
            "seo_description": "India launches sovereign AI supercomputing grid to boost research, startups, and green tech.",
            "seo_keywords": "AI, supercomputing, India tech, GPU clusters",
            "days_ago": 1,
        },
        {
            "title": "Global Trade Summit Reaches Breakthrough Agreement on Clean Supply Chains",
            "slug": "global-trade-summit-reaches-breakthrough-agreement-clean-supply-chains",
            "excerpt": "Representatives from over 40 nations agreed on unified carbon tracking standards for maritime shipping and heavy manufacturing exports.",
            "body": "<p>Following three days of intense negotiations in Geneva, world leaders have ratified the Green Maritime Accord. The agreement establishes mandatory zero-emission targets for international cargo routes by 2035.</p><p>Diplomats praised the coalition's ability to balance economic development with strict climate accountability metrics.</p>",
            "featured_image": "https://images.unsplash.com/photo-1521791136064-7986c2920216?auto=format&fit=crop&w=1200&q=80",
            "category_slug": "world",
            "tags": ["Global Trade", "Climate Change"],
            "writer_username": "neha_world",
            "status": "published",
            "is_featured": True,
            "is_breaking": False,
            "views_count": 3150,
            "seo_title": "Global Trade Summit Green Accord - DO Record",
            "seo_description": "40 nations sign landmark clean supply chain agreement at Geneva Trade Summit.",
            "seo_keywords": "Trade, climate change, green shipping, diplomacy",
            "days_ago": 2,
        },
        {
            "title": "High-Stakes Electoral Reform Bill Passes Key Parliamentary Committee",
            "slug": "high-stakes-electoral-reform-bill-passes-key-parliamentary-committee",
            "excerpt": "The bipartisan committee recommended mandatory digital transparency for political donations and modern voter verification protocols.",
            "body": "<p>Parliamentary proceedings reached a milestone today as committee members voted unanimously to advance the Electoral Integrity Bill. The legislation addresses campaign finance oversight and real-time disclosure mechanisms.</p>",
            "featured_image": "https://images.unsplash.com/photo-1540910419892-4a36d2c3266c?auto=format&fit=crop&w=1200&q=80",
            "category_slug": "politics",
            "tags": ["Elections", "Budget 2026"],
            "writer_username": "rohit_politics",
            "status": "published",
            "is_featured": False,
            "is_breaking": False,
            "views_count": 1890,
            "days_ago": 3,
        },
        {
            "title": "Cricket Championship Finals: Dramatic Comeback Takes Match to Final Over",
            "slug": "cricket-championship-finals-dramatic-comeback-takes-match-to-final-over",
            "excerpt": "In a nail-biting encounter, India's middle order staged a heroic recovery against formidable bowling under floodlights.",
            "body": "<p>Spectators witnessed one of the most thrilling cricket finishes of the decade as the championship match went down to the final ball. Chasing a daunting target of 312, the team delivered under immense pressure.</p>",
            "featured_image": "https://images.unsplash.com/photo-1531415074968-036ba1b575da?auto=format&fit=crop&w=1200&q=80",
            "category_slug": "sports",
            "tags": ["Cricket"],
            "writer_username": "arjun_sports",
            "status": "published",
            "is_featured": True,
            "is_breaking": False,
            "views_count": 6420,
            "days_ago": 4,
        },
        {
            "title": "Central Bank Announces Rate Cut as Inflation Cools to 3-Year Lows",
            "slug": "central-bank-announces-rate-cut-inflation-cools",
            "excerpt": "Equities surged across banking and real estate sectors following the surprise monetary policy announcement.",
            "body": "<p>Financial markets reacted positively this morning after the Monetary Policy Committee approved a 25 basis point benchmark rate reduction. Governors cited sustained moderation in headline inflation and robust industrial output numbers.</p>",
            "featured_image": "https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?auto=format&fit=crop&w=1200&q=80",
            "category_slug": "business",
            "tags": ["Stock Market", "Startups"],
            "writer_username": "rohit_politics",
            "status": "published",
            "is_featured": False,
            "is_breaking": False,
            "views_count": 2740,
            "days_ago": 5,
        },
        {
            "title": "Quantum Encryption Protocol Successfully Tested in Orbital Satellite Link",
            "slug": "quantum-encryption-protocol-tested-orbital-satellite-link",
            "excerpt": "Space scientists achieved unhackable quantum key distribution across a distance of 1,200 kilometers.",
            "body": "<p>In a giant leap for cyber defense, space research engineers confirmed successful transmission of quantum-encrypted telemetry from a low-Earth orbit satellite to ground stations.</p>",
            "featured_image": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200&q=80",
            "category_slug": "technology",
            "tags": ["Cybersecurity", "Space Tech"],
            "writer_username": "priya_tech",
            "status": "pending", # PENDING REVIEW FOR EDITORIAL TESTING
            "is_featured": False,
            "is_breaking": False,
            "views_count": 0,
            "days_ago": 0,
        },
        {
            "title": "Draft Review: Sustainable Urban Architecture Regulations for 2027",
            "slug": "draft-review-sustainable-urban-architecture-regulations-2027",
            "excerpt": "New municipal codes will mandate solar integration and rainwater harvesting for high-rise commercial developments.",
            "body": "<p>Draft notes on upcoming urban planning guidelines across major metropolitan centers...</p>",
            "featured_image": "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=80",
            "category_slug": "lifestyle",
            "tags": ["Green Energy", "Climate Change"],
            "writer_username": "neha_world",
            "status": "draft",
            "is_featured": False,
            "is_breaking": False,
            "views_count": 0,
            "days_ago": 0,
        },
        {
            "title": "Rejected Piece: Unverified Social Media Trends Report",
            "slug": "rejected-piece-unverified-social-media-trends-report",
            "excerpt": "Analysis of viral online rumors regarding consumer electronics supply delays.",
            "body": "<p>This draft contained unverified claims without corroborating source quotes.</p>",
            "featured_image": "https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?auto=format&fit=crop&w=1200&q=80",
            "category_slug": "entertainment",
            "tags": ["Cinema"],
            "writer_username": "priya_tech",
            "status": "rejected",
            "rejection_feedback": "Article lacks verified primary quotes and secondary source corroboration. Please re-interview industry reps before resubmitting.",
            "is_featured": False,
            "is_breaking": False,
            "views_count": 0,
            "days_ago": 1,
        },
    ]

    for art in articles_seed:
        existing = await articles_collection.find_one({"slug": art["slug"]})
        if not existing:
            # find writer
            writer = next((w for w in writers if w["username"] == art["writer_username"]), admin)
            cat_id = cat_map.get(art["category_slug"], list(cat_map.values())[0])
            cat_obj = await categories_collection.find_one({"_id": cat_id}) if not isinstance(cat_id, str) else None
            cat_name = art["category_slug"].capitalize()

            doc = {
                "title": art["title"],
                "slug": art["slug"],
                "excerpt": art["excerpt"],
                "body": art["body"],
                "featured_image": art["featured_image"],
                "category_id": cat_id,
                "category_name": cat_name,
                "tags": art["tags"],
                "author_id": str(writer["_id"]),
                "author_name": writer["name"],
                "author_avatar": writer.get("avatar_url", "/static/images/default_avatar.png"),
                "status": art["status"],
                "is_featured": art.get("is_featured", False),
                "is_breaking": art.get("is_breaking", False),
                "views_count": art.get("views_count", 0),
                "rejection_feedback": art.get("rejection_feedback", ""),
                "seo_title": art.get("seo_title", art["title"]),
                "seo_description": art.get("seo_description", art["excerpt"]),
                "seo_keywords": ", ".join(art["tags"]),
                "created_at": datetime.utcnow() - timedelta(days=art["days_ago"]),
                "updated_at": datetime.utcnow() - timedelta(days=art["days_ago"]),
                "published_at": datetime.utcnow() - timedelta(days=art["days_ago"]) if art["status"] == "published" else None,
            }
            await articles_collection.insert_one(doc)

    print("[OK] Created Sample Articles")

    # 5. System Settings
    hero = await articles_collection.find_one({"is_featured": True, "status": "published"})
    hero_id = str(hero["_id"]) if hero else None

    settings_doc = {
        "site_name": "DO Record",
        "site_description": "Premier Digital Media & News Channel delivering 24/7 accurate, unbiased, and breaking news.",
        "breaking_news_text": "BREAKING: India Unveils Sovereign Next-Gen AI Computing Grid Project | Global Trade Accord Finalized in Geneva",
        "breaking_news_active": True,
        "hero_article_id": hero_id,
        "featured_category_ids": list(cat_map.values())[:4],
        "allow_comments": True,
        "require_2fa": False,
        "session_timeout_minutes": 1440,
        "updated_at": datetime.utcnow(),
    }
    await settings_collection.update_one({}, {"$set": settings_doc}, upsert=True)
    print("[OK] Seeded System Settings & Homepage Configuration")

    print("[SUCCESS] DO Record CMS Database Seeding Complete!")

if __name__ == "__main__":
    asyncio.run(seed_database())
