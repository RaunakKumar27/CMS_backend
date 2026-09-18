from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class ArticleCreate(BaseModel):
    title: str
    slug: Optional[str] = None
    excerpt: Optional[str] = ""
    body: str
    featured_image: Optional[str] = "/static/images/default_news.jpg"
    category_id: str
    tags: List[str] = []
    is_featured: bool = False
    is_breaking: bool = False
    is_web_story: bool = False
    web_story_template: Optional[str] = None
    seo_title: Optional[str] = ""
    seo_description: Optional[str] = ""
    seo_keywords: Optional[str] = ""
    status: str = "draft" # "draft" or "pending"

class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    body: Optional[str] = None
    featured_image: Optional[str] = None
    category_id: Optional[str] = None
    tags: Optional[List[str]] = None
    is_featured: Optional[bool] = None
    is_breaking: Optional[bool] = None
    is_web_story: Optional[bool] = None
    web_story_template: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_keywords: Optional[str] = None
    status: Optional[str] = None
    rejection_feedback: Optional[str] = None
    scheduled_at: Optional[datetime] = None

class ArticleReject(BaseModel):
    feedback: str

class ArticleResponse(BaseModel):
    id: str = Field(alias="_id")
    title: str
    slug: str
    excerpt: str
    body: str
    featured_image: str
    category_id: str
    category_name: str
    tags: List[str]
    author_id: str
    author_name: str
    author_avatar: str
    status: str
    is_featured: bool
    is_breaking: bool
    is_web_story: bool = False
    web_story_template: Optional[str] = None
    views_count: int = 0
    rejection_feedback: Optional[str] = ""
    seo_title: Optional[str] = ""
    seo_description: Optional[str] = ""
    seo_keywords: Optional[str] = ""
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
