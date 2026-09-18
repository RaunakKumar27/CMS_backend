from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class ActivityLogCreate(BaseModel):
    user_id: str
    username: str
    action: str # e.g. "ARTICLE_CREATED", "USER_LOGIN", "ARTICLE_PUBLISHED"
    target: str # e.g. "Article: Breaking News", "User: writer1"
    details: Optional[str] = ""
    ip_address: Optional[str] = ""
    user_agent: Optional[str] = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ActivityLogResponse(ActivityLogCreate):
    id: str = Field(alias="_id")

    class Config:
        populate_by_name = True

class SystemSettings(BaseModel):
    site_name: str = "DO Record"
    site_description: str = "Premier Digital Media & News Channel"
    breaking_news_text: str = "WELCOME TO DO RECORD: Delivering Instant, Unbiased, In-Depth News Coverage 24/7."
    breaking_news_active: bool = True
    hero_article_id: Optional[str] = None
    featured_category_ids: list = []
    allow_comments: bool = True
    require_2fa: bool = False
    session_timeout_minutes: int = 1440
