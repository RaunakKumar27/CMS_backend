from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime

class WriterApplicationCreate(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = ""
    city: Optional[str] = ""
    country: Optional[str] = ""
    bio: str
    areas_of_interest: str
    writing_experience: Optional[str] = ""
    portfolio_url: Optional[str] = ""
    linkedin_url: Optional[str] = ""
    social_url: Optional[str] = ""
    avatar_url: Optional[str] = "/static/images/default_avatar.png"
    password: Optional[str] = None

class WriterApplicationReview(BaseModel):
    admin_notes: Optional[str] = ""
    applicant_feedback: Optional[str] = ""

class WriterApplicationResponse(BaseModel):
    id: str = Field(alias="_id")
    full_name: str
    email: str
    phone: Optional[str] = ""
    city: Optional[str] = ""
    country: Optional[str] = ""
    bio: str
    areas_of_interest: str
    writing_experience: Optional[str] = ""
    portfolio_url: Optional[str] = ""
    linkedin_url: Optional[str] = ""
    social_url: Optional[str] = ""
    avatar_url: str
    status: str = "PENDING" # "PENDING", "UNDER_REVIEW", "APPROVED", "REJECTED"
    admin_notes: Optional[str] = ""
    applicant_feedback: Optional[str] = ""
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        populate_by_name = True
