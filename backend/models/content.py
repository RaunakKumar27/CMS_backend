# from pydantic import BaseModel
# from typing import List, Optional


# class ContentCreate(BaseModel):
#     title: str
#     body: str
#     author: str
#     tags: List[str]
#     template: str


# class ContentUpdate(BaseModel):
#     title: Optional[str] = None
#     body: Optional[str] = None
#     author: Optional[str] = None
#     tags: Optional[List[str]] = None
#     template: Optional[str] = None


from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class ContentCreate(BaseModel):
    title: str
    body: str
    tags: List[str] = []
    author: str
    template: str
    

class ContentUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    author: Optional[str] = None
    tags: Optional[List[str]] = None
    template: Optional[str] = None


class ContentOut(BaseModel):
    id: str = Field(alias="_id")
    title: str
    body: str
    tags: List[str]
    author: str
    template: Optional[str]
    
    created_at: datetime
