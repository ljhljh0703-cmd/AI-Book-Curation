from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReviewPreferenceAnalysisRequest(BaseModel):
    user_id: str
    book_id: int
    review_id: Optional[str] = None
    rating: float
    review_content: str
    book_metadata: Dict[str, Any] = Field(default_factory=dict)


class ReviewPreferenceAnalysisResponse(BaseModel):
    overall_sentiment: str = "neutral"
    sentiment_score: float = 0.0
    confidence: float = 0.0
    liked_aspects: List[str] = Field(default_factory=list)
    disliked_aspects: List[str] = Field(default_factory=list)
    preference_terms: List[str] = Field(default_factory=list)
    avoid_terms: List[str] = Field(default_factory=list)
    preferred_mood: List[str] = Field(default_factory=list)
    avoid_mood: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    analysis_status: str = "SUCCEEDED"
    analysis_error_message: Optional[str] = None


class UserPreferenceProfileVectorizeRequest(BaseModel):
    user_id: str
    profile_version: int = 1
    profile_text: str
    embedding_model: Optional[str] = "KURE"


class UserPreferenceProfileVectorizeResponse(BaseModel):
    user_id: str
    profile_version: int
    collection_name: Optional[str] = None
    point_id: Optional[str] = None
    embedding_model: str = "KURE"
    embedding_dimension: int = 0
    build_status: str = "FAILED"
    error_message: Optional[str] = None
