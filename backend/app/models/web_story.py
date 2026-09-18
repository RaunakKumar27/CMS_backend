from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class StoryPage(BaseModel):
    id: str
    order: int
    image: str
    headline: str = ""
    description: str = ""
    text_position: str = "bottom"
    text_alignment: str = "left"
    text_size: str = "medium"
    overlay: bool = True
    background_position_x: int = 50
    background_position_y: int = 50
    zoom: int = 100
    duration: int = 5
    cta_text: Optional[str] = None
    cta_url: Optional[str] = None


class WebStoryCreate(BaseModel):
    title: str
    description: str = ""
    category_id: str
    tags: List[str] = []
    cover_image: str
    pages: List[StoryPage]
    related_article_id: Optional[str] = None
    seo_title: str = ""
    seo_description: str = ""


class WebStoryResponse(WebStoryCreate):
    id: str = Field(alias="_id")
    slug: str
    author_id: str
    author_name: str
    status: str
    view_count: int = 0
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
