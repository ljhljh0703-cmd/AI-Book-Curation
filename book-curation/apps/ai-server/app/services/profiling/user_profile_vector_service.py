from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.core.config import settings
from app.schemas.preference import UserPreferenceProfileVectorizeRequest, UserPreferenceProfileVectorizeResponse
from app.services.clients.kure_client import KureClient


class UserProfileVectorService:
    DEFAULT_COLLECTION = "user_preference_profiles_kure"

    def __init__(self) -> None:
        self.collection_name = getattr(settings, "QDRANT_USER_PROFILE_COLLECTION", self.DEFAULT_COLLECTION)
        self.qdrant_url = getattr(settings, "QDRANT_URL", "http://qdrant:6333")
        self.qdrant_api_key = getattr(settings, "QDRANT_API_KEY", "")
        self.expected_dimension = int(getattr(settings, "KURE_EXPECTED_DIMENSION", 1024))
        self.embedder = KureClient()
        if self.qdrant_api_key:
            self.client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key)
        else:
            self.client = QdrantClient(url=self.qdrant_url)

    def vectorize(self, request: UserPreferenceProfileVectorizeRequest) -> UserPreferenceProfileVectorizeResponse:
        text = (request.profile_text or "").strip()
        if not text:
            return UserPreferenceProfileVectorizeResponse(
                user_id=request.user_id,
                profile_version=request.profile_version,
                collection_name=self.collection_name,
                embedding_model="KURE",
                build_status="SKIPPED",
                error_message="profile_text is empty",
            )

        vector = self.embedder.embedding(text)
        if not vector:
            return UserPreferenceProfileVectorizeResponse(
                user_id=request.user_id,
                profile_version=request.profile_version,
                collection_name=self.collection_name,
                embedding_model="KURE",
                build_status="FAILED",
                error_message="KURE embedding failed",
            )

        if len(vector) != self.expected_dimension:
            return UserPreferenceProfileVectorizeResponse(
                user_id=request.user_id,
                profile_version=request.profile_version,
                collection_name=self.collection_name,
                embedding_model="KURE",
                embedding_dimension=len(vector),
                build_status="FAILED",
                error_message=f"invalid vector dimension: {len(vector)}",
            )

        self._ensure_collection()
        point_id = self._point_id(request.user_id)
        payload: Dict[str, Any] = {
            "user_id": request.user_id,
            "profile_version": request.profile_version,
            "embedding_model": "KURE",
            "built_at": datetime.now(timezone.utc).isoformat(),
        }
        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
            wait=True,
        )
        return UserPreferenceProfileVectorizeResponse(
            user_id=request.user_id,
            profile_version=request.profile_version,
            collection_name=self.collection_name,
            point_id=point_id,
            embedding_model="KURE",
            embedding_dimension=len(vector),
            build_status="SUCCEEDED",
        )

    def _ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection_name):
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.expected_dimension, distance=Distance.COSINE),
        )

    @staticmethod
    def _point_id(user_id: str) -> str:
        # 수정 포인트: Qdrant point id는 UUID 문자열 또는 정수만 안전합니다.
        # user_id 자체가 UUID이므로 prefix를 붙이지 않고 그대로 사용합니다.
        return user_id
