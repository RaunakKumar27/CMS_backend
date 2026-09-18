from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class MediaItem(BaseModel):
    filename: str
    original_name: str
    file_url: str
    file_type: str # "image", "video", "document"
    mime_type: str
    file_size: int
    uploaded_by_id: str
    uploaded_by_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class MediaResponse(MediaItem):
    id: str = Field(alias="_id")

    class Config:
        populate_by_name = True
