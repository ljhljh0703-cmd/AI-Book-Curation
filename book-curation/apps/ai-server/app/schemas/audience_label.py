from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AudienceLabelBook(BaseModel):
    isbn: str
    title: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    publish_date: Optional[str] = None
    page: Optional[int] = None
    description: Optional[str] = None
    simple_intro: Optional[str] = None
    book_intro: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    cate_depth1: List[str] = Field(default_factory=list)
    kcid: List[str] = Field(default_factory=list)
    author_intro: Optional[str] = None
    book_index: Optional[str] = None
    pub_review: Optional[str] = None


class AudienceLabelBatchRequest(BaseModel):
    books: List[AudienceLabelBook] = Field(default_factory=list)


class AudienceLabelResult(BaseModel):
    isbn: str
    status: str = "FAILED"
    audience_group: str = "UNKNOWN"
    audience_min_age: Optional[int] = None
    audience_max_age: Optional[int] = None
    difficulty_level: str = "UNKNOWN"
    confidence: float = 0.0
    reason: Optional[str] = None
    error_message: Optional[str] = None


class AudienceLabelBatchResponse(BaseModel):
    items: List[AudienceLabelResult] = Field(default_factory=list)
