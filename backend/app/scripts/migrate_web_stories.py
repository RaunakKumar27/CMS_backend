"""Create Web Story indexes. Run once from backend/: python -m app.scripts.migrate_web_stories"""
import asyncio
from app.core.database import web_stories_collection, story_events_collection


async def main():
    await web_stories_collection.create_index("slug", unique=True)
    await web_stories_collection.create_index([("status", 1), ("published_at", -1)])
    await web_stories_collection.create_index([("category_id", 1), ("status", 1), ("published_at", -1)])
    await web_stories_collection.create_index([("author_id", 1), ("updated_at", -1)])
    await story_events_collection.create_index([("story_id", 1), ("created_at", -1)])
    print("Web Story indexes created.")


if __name__ == "__main__":
    asyncio.run(main())
