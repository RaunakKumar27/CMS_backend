from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime

# Available system permissions
ALL_PERMISSIONS = [
    "articles.view",
    "articles.create",
    "articles.edit",
    "articles.delete",
    "articles.publish",
    "articles.approve",
    "web_stories.view",
    "web_stories.create",
    "web_stories.edit",
    "web_stories.delete",
    "web_stories.publish",
    "web_stories.approve",
    "writers.view",
    "writers.create",
    "writers.edit",
    "writers.delete",
    "categories.manage",
    "tags.manage",
    "media.manage",
    "analytics.view",
    "settings.manage",
    "users.manage",
    "logs.view",
]

WRITER_PERMISSIONS = [
    "articles.view",
    "articles.create",
    "articles.edit",
    "web_stories.view",
    "web_stories.create",
    "web_stories.edit",
    "media.manage",
    "tags.manage",
]

class UserBase(BaseModel):
    username: str
    email: str
    name: str
    role: str = "writer" # "super_admin" or "writer"
    bio: Optional[str] = ""
    avatar_url: Optional[str] = "/static/images/default_avatar.png"
    social_twitter: Optional[str] = ""
    social_linkedin: Optional[str] = ""
    is_active: bool = True
    permissions: List[str] = []

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    social_twitter: Optional[str] = None
    social_linkedin: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    permissions: Optional[List[str]] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

class UserResponse(UserBase):
    id: str = Field(alias="_id")
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        populate_by_name = True
