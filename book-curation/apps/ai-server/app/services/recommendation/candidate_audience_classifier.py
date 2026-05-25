from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from typing import Any, Dict, List, Protocol

from app.core.config import settings
from app.services.common.config_loader import load_text_resource


class ChatCompletionClient(Protocol):
    def chat_completion(self, system_prompt: str, user_prompt: str) -> str:
        ...


class CandidateAudienceClassifier:
    """Attach enum audience labels to already-retrieved candidates.

    현재 추천 runtime 경로는 backend가 PostgreSQL READY audience label을 ISBN별로 전달하고,
    이 클래스는 그 label만 후보 metadata에 붙입니다. candidate_audience_* prompt와
    _labels_from_llm은 batch/legacy fallback 검토용으로 남겨두되 추천 요청 경로에서 새 LLM 호출을 만들지 않습니다.
    The server never branches on natural-language audience words. Runtime LLM output,
    existing payload metadata, and user/request profile are reduced to enums before
    deterministic reranking uses them.
    """

    VALID_AGE_GROUPS = {"INFANT", "CHILD", "ELEMENTARY", "MIDDLE_SCHOOL", "HIGH_SCHOOL", "TEEN", "YOUNG_ADULT", "ADULT", "SENIOR", "GENERAL", "UNKNOWN"}
    VALID_EDUCATION_STAGES = {"PRESCHOOL", "ELEMENTARY", "MIDDLE", "HIGH", "COLLEGE", "GENERAL", "UNKNOWN"}
    VALID_DIFFICULTY_LEVELS = {"EASY", "NORMAL", "HARD", "INTRODUCTORY", "GENERAL", "ADVANCED", "UNKNOWN"}

    def __init__(self, llm_client: ChatCompletionClient) -> None:
        self.llm_client = llm_client
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    def attach_labels(
        self,
        *,
        candidates: List[Dict[str, Any]],
        user_profile: Dict[str, Any] | None,
        requested_audience_group: str | None,
        requested_education_stage: str | None,
        request_id: str | None = None,
        audience_label_map: Dict[str, Dict[str, Any]] | None = None,
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        output = [dict(candidate) for candidate in candidates]
        label_map = audience_label_map or {}
        matched_count = 0
        for candidate in output:
            profile = self._profile_from_label_map(candidate, label_map)
            if profile:
                candidate["audience_profile"] = profile
                matched_count += 1

        # 수정 포인트: 추천 요청 경로에서는 LLM 또는 raw_json의 임시 audience_profile을 사용하지 않습니다.
        # 관리자 배치가 PostgreSQL에 READY로 저장한 label만 ISBN으로 매칭하고, 없으면 중립 UNKNOWN으로 둡니다.
        print(
            f"[AUDIENCE LABEL][{request_id or '-'}] provider=POSTGRES_READY "
            f"matched={matched_count} missing={len(output) - matched_count}"
        )

        for candidate in output:
            # 수정 포인트: Qdrant/raw_json에서 audience_profile 키가 None으로 들어온 경우
            # dict 기본값이 적용되지 않아 FastAPI response_model 검증에서 500이 발생할 수 있습니다.
            # READY label이 매칭되지 않은 후보는 명시적으로 UNKNOWN dict로 정규화합니다.
            if not isinstance(candidate.get("audience_profile"), dict):
                candidate["audience_profile"] = self._unknown_profile(source="UNAVAILABLE")
            score_detail = dict(candidate.get("score_detail") or {})
            score_detail["audience_profile"] = candidate["audience_profile"]
            candidate["score_detail"] = score_detail
        return output


    def _profile_from_label_map(self, candidate: Dict[str, Any], label_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any] | None:
        candidate_id = self._candidate_id(candidate)
        raw = label_map.get(candidate_id) or label_map.get(str(candidate.get("isbn13") or "").strip())
        if not isinstance(raw, dict):
            return None
        profile = self._normalize_profile({**raw, "source": raw.get("source") or "POSTGRES"})
        return profile if profile.get("target_age_group") != "UNKNOWN" else None

    def _labels_from_llm(
        self,
        *,
        candidates: List[Dict[str, Any]],
        user_profile: Dict[str, Any],
        requested_audience_group: str | None,
        requested_education_stage: str | None,
        request_id: str | None,
    ) -> Dict[str, Dict[str, Any]]:
        # 수정 포인트: 이 메서드는 현재 추천 runtime에서는 호출하지 않습니다.
        # READY label이 없는 후보를 실시간 LLM으로 보강하면 latency/cost가 증가하므로,
        # 향후 batch/fallback으로 재도입할 때만 명시적으로 연결합니다.
        if not candidates:
            return {}
        payload = {
            "request_context": {
                "user_age_group": self._normalize_age_group(self._profile_age_group(user_profile)),
                "requested_audience_group": self._normalize_age_group(requested_audience_group),
                "requested_education_stage": self._normalize_education_stage(requested_education_stage),
            },
            "candidates": [self._candidate_payload(candidate) for candidate in candidates],
        }
        try:
            raw = self.llm_client.chat_completion(
                system_prompt=load_text_resource("prompts/candidate_audience_system.md"),
                user_prompt=load_text_resource("prompts/candidate_audience_user.md").replace(
                    "{{payload_json}}",
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            parsed = self._parse_json(raw)
        except Exception as exc:
            print(f"[AUDIENCE LABEL][{request_id or '-'}] provider=LLM error={exc}")
            return {}

        items = parsed.get("items") if isinstance(parsed, dict) else []
        if not isinstance(items, list):
            return {}
        labels: Dict[str, Dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("candidate_id") or "").strip()
            if not candidate_id:
                continue
            labels[candidate_id] = self._normalize_profile(
                {
                    "target_age_group": item.get("target_age_group"),
                    "education_stage": item.get("education_stage"),
                    "difficulty_level": item.get("difficulty_level"),
                    "confidence": item.get("confidence"),
                    "source": "LLM",
                }
            )
        print(f"[AUDIENCE LABEL][{request_id or '-'}] provider=LLM labeled={len(labels)} requested={len(candidates)}")
        return labels

    def _profile_from_payload(self, candidate: Dict[str, Any]) -> Dict[str, Any] | None:
        raw = (
            candidate.get("audience_profile")
            or candidate.get("audienceProfile")
            or candidate.get("audience")
            or candidate.get("targetAudience")
            or candidate.get("target_audience")
        )
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = None
        if not isinstance(raw, dict):
            return None
        profile = self._normalize_profile(raw)
        return profile if profile.get("target_age_group") != "UNKNOWN" else None

    def _normalize_profile(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "target_age_group": self._normalize_age_group(
                raw.get("target_age_group")
                or raw.get("targetAgeGroup")
                or raw.get("audience_group")
                or raw.get("audienceGroup")
                or raw.get("age_group")
                or raw.get("ageGroup")
            ),
            "education_stage": self._normalize_education_stage(
                raw.get("education_stage") or raw.get("educationStage")
            ),
            "difficulty_level": self._normalize_difficulty_level(
                raw.get("difficulty_level") or raw.get("difficultyLevel")
            ),
            "confidence": self._normalize_confidence(raw.get("confidence")),
            "audience_min_age": raw.get("audience_min_age") or raw.get("audienceMinAge"),
            "audience_max_age": raw.get("audience_max_age") or raw.get("audienceMaxAge"),
            "reason": raw.get("reason"),
            "source": str(raw.get("source") or "PAYLOAD").strip().upper()[:40],
        }

    def _candidate_payload(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "candidate_id": self._candidate_id(candidate),
            "title": self._trim(candidate.get("title"), 120),
            "author": self._trim(candidate.get("author"), 120),
            "publisher": self._trim(candidate.get("publisher"), 120),
            "categories": self._compact_list(candidate.get("categories") or candidate.get("cate_depth1") or candidate.get("kcid"), 12),
            "category_code": self._trim(candidate.get("categoryCode") or candidate.get("category_code"), 80),
            "description": self._trim(candidate.get("description") or candidate.get("simple_intro") or candidate.get("book_intro"), 500),
        }

    def _candidate_id(self, candidate: Dict[str, Any]) -> str:
        return str(candidate.get("isbn") or candidate.get("isbn13") or self._hash_text(self._candidate_identity(candidate)))

    def _candidate_identity(self, candidate: Dict[str, Any]) -> str:
        return "|".join(str(candidate.get(key) or "") for key in ["title", "author", "publisher"])

    def _cache_key(self, candidate: Dict[str, Any]) -> str:
        return self._hash_text(json.dumps(self._candidate_payload(candidate), ensure_ascii=False, sort_keys=True))

    def _put_cache(self, key: str, value: Dict[str, Any]) -> None:
        self._cache[key] = dict(value)
        self._cache.move_to_end(key)
        max_size = max(32, int(settings.AUDIENCE_LABEL_CACHE_SIZE))
        while len(self._cache) > max_size:
            self._cache.popitem(last=False)

    @staticmethod
    def _unknown_profile(source: str) -> Dict[str, Any]:
        return {
            "target_age_group": "UNKNOWN",
            "education_stage": "UNKNOWN",
            "difficulty_level": "UNKNOWN",
            "confidence": 0.0,
            "source": source,
        }

    @classmethod
    def _normalize_age_group(cls, value: Any) -> str:
        text = str(value or "UNKNOWN").strip().upper()
        return text if text in cls.VALID_AGE_GROUPS else "UNKNOWN"

    @classmethod
    def _normalize_education_stage(cls, value: Any) -> str:
        text = str(value or "UNKNOWN").strip().upper()
        return text if text in cls.VALID_EDUCATION_STAGES else "UNKNOWN"

    @classmethod
    def _normalize_difficulty_level(cls, value: Any) -> str:
        text = str(value or "UNKNOWN").strip().upper()
        return text if text in cls.VALID_DIFFICULTY_LEVELS else "UNKNOWN"

    @staticmethod
    def _normalize_confidence(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, number))

    @staticmethod
    def _profile_age_group(profile: Dict[str, Any]) -> str | None:
        demographic = profile.get("demographicProfile") or profile.get("demographic_profile")
        if isinstance(demographic, dict):
            return (
                demographic.get("userAgeGroup")
                or demographic.get("user_age_group")
                or demographic.get("ageGroup")
                or demographic.get("age_group")
            )
        return profile.get("userAgeGroup") or profile.get("user_age_group") or profile.get("ageGroup") or profile.get("age_group")

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        value = str(text or "").strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?", "", value, flags=re.IGNORECASE).strip()
            value = re.sub(r"```$", "", value).strip()
        if not value.startswith("{"):
            match = re.search(r"\{.*\}", value, flags=re.DOTALL)
            value = match.group(0) if match else value
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _trim(value: Any, limit: int) -> str | None:
        text = str(value or "").strip()
        return text[:limit] if text else None

    @classmethod
    def _compact_list(cls, value: Any, limit: int) -> List[str]:
        values = value if isinstance(value, list) else [value] if value is not None else []
        result: List[str] = []
        seen = set()
        for item in values:
            text = cls._trim(item, 80)
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _hash_text(value: str) -> str:
        return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:32]
