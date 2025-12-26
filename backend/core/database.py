# from pymongo import MongoClient
# from app.core.config import settings

# client = MongoClient(settings.MONGO_URI)
# db = client[settings.DATABASE_NAME]

# content_collection = db["content"]

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = "mongodb://localhost:27017"

client = AsyncIOMotorClient(MONGO_URL)
db = client.cms_db
content_collection = db.contents
