from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class CategoryCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = ""
    image_url: Optional[str] = ""
    order: int = 0
    is_active: bool = True

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None

class TagCreate(BaseModel):
    name: str
    slug: Optional[str] = None

class TagResponse(BaseModel):
    id: str = Field(alias="_id")
    name: str
    slug: str
    count: int = 0

    class Config:
        populate_by_name = True
