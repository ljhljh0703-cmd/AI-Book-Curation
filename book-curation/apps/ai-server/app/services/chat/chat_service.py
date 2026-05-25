from __future__ import annotations

from datetime import datetime, timezone
from contextlib import nullcontext
import copy
from time import perf_counter
from typing import Any, Dict, List
from uuid import uuid4

from app.core.config import settings
from app.services.recommendation.candidate_audience_classifier import CandidateAudienceClassifier
from app.services.recommendation.candidate_filter import CandidateFilter
from app.services.intent.chat_intent_classifier import ChatIntent, ChatIntentClassifier
from app.services.clients.clova_client import ClovaClient
from app.services.common.stage_timer import StageTimer
from app.services.context.conversation_context import ConversationContext
from app.services.context.reference_resolver import ReferenceResolver, ResolvedReferenceContext
from app.services.context.multiturn_intent_context import MultiturnIntentContextResolver
from app.services.context.profile_context import ProfileContextBuilder
from app.services.recommendation.multiturn_recommendation_policy import MultiturnRecommendationPolicy, PreviousRecommendationScope
from app.services.recommendation.profile_reranker import ProfileReranker
from app.services.intent.query_intent_parser import QueryIntent, QueryIntentParser
from app.services.intent.query_variant_builder import QueryVariantBuilder
from app.services.intent.reading_mode_policy import ReadingModePolicy
from app.services.intent.query_personalization_router import PersonalizationDecision, PersonalizationMode, QueryPersonalizationRouter
from app.services.retrieval.qdrant_kure_search import BookKureQdrantSearcher
from app.services.retrieval.qdrant_search import BookQdrantSearcher
from app.services.recommendation.recommendation_guardrails import RecommendationGuardrails
from app.services.recommendation.recommendation_policy import RecommendationPolicy
from app.services.recommendation.recommendation_prompt_builder import RecommendationPromptBuilder
from app.services.recommendation.recommendation_reason_jobs import recommendation_reason_jobs
from app.services.recommendation.anonymous_candidate_selector import AnonymousCandidateSelector
from app.services.recommendation.score_fusion_service import ScoreFusionService
from app.services.reranking.rerank_service import RerankService
from app.services.reranking.single_result_selector import prioritize_single_result_by_reranker
from app.services.recommendation.recommendation_pipeline import (
    PersonalizationProvider,
    RecommendationPipeline,
    RecommendationPipelineConfig,
    RerankerProvider,
    SequenceProvider,
)
from app.services.ranking.ranking_router import RankingModelRouter


class BookChatService:
    """도서 추천 채팅 use-case를 조율하는 service layer입니다.

    프롬프트, 키워드 정책, 후보 필터링, 프로필 텍스트 변환은 별도 모듈에서 관리하고,
    이 클래스는 요청 흐름을 조립하는 역할만 담당합니다.
    """

    def __init__(self) -> None:
        self.clova_retriever = BookQdrantSearcher()
        self.clova_hybrid_retriever: BookQdrantSearcher | None = None
        self.kure_retriever: BookKureQdrantSearcher | None = None
        self.kure_hybrid_retriever: BookKureQdrantSearcher | None = None
        # 기존 내부 메서드 호환을 위해 기본 retriever는 CLOVA로 유지합니다.
        self.retriever = self.clova_retriever
        self.clova = ClovaClient()
        self.policy = RecommendationPolicy()
        self.context = ConversationContext()
        self.profile_context = ProfileContextBuilder()
        self.prompt_builder = RecommendationPromptBuilder(self.profile_context)
        self.intent_classifier = ChatIntentClassifier(self.clova)
        self.audience_classifier = CandidateAudienceClassifier(self.clova)
        self.candidate_filter = CandidateFilter(self.policy)
        self.multiturn_policy = MultiturnRecommendationPolicy(self.context)
        self.multiturn_intent_context = MultiturnIntentContextResolver(self.context)
        self.reference_resolver = ReferenceResolver(self.context)
        self.guardrails = RecommendationGuardrails()
        self.reranker = ProfileReranker()
        self.personalization_router = QueryPersonalizationRouter()
        self.query_parser = QueryIntentParser()
        self.query_variant_builder = QueryVariantBuilder()
        self.pipeline_config = self._build_pipeline_config()
        self.pipeline = RecommendationPipeline(self.pipeline_config)
        # 수정 포인트: 관리자 rankingModel 설정값을 실제 후보 축소 stage에 연결하는 router입니다.
        # LightFM artifact가 없거나 매핑이 맞지 않으면 기존 RULE_BASED 흐름으로 fallback합니다.
        self.ranking_router = RankingModelRouter()
        self.anonymous_selector = AnonymousCandidateSelector()
        self.rerank_service = RerankService()
        self.score_fusion = ScoreFusionService()

    def recommend(
        self,
        query: str,
        personalized: bool = False,
        history: List[Dict[str, Any]] | None = None,
        user_id: str | None = None,
        guest: bool = False,
        guest_session_id: str | None = None,
        guest_room_id: str | None = None,
        user_profile: Dict[str, Any] | None = None,
        guest_profile: Dict[str, Any] | None = None,
        embedding_model: str | None = None,
        ranking_model: str | None = None,
        recommendation_strategy: str | None = None,
        personalization_model: str | None = None,
        reranker_provider: str | None = None,
        bm25_enabled: bool = False,
        request_id: str | None = None,
        audience_label_map: Dict[str, Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """채팅 추천 요청의 전체 흐름을 수행합니다."""
        user_profile = user_profile or {}
        guest_profile = guest_profile or {}
        audience_label_map = audience_label_map or {}
        embedding_model = self._normalize_embedding_model(embedding_model)
        recommendation_strategy = self._normalize_recommendation_strategy(recommendation_strategy)
        personalization_model = self._normalize_personalization_model(personalization_model or ranking_model)
        ranking_model = personalization_model
        reranker_provider = self._normalize_reranker_provider(reranker_provider)
        bm25_enabled = bool(bm25_enabled)
        request_id = request_id or str(uuid4())
        stage_timer = StageTimer()

        # 최신 소스 기준으로 guest_profile은 저장/리랭킹에 사용하지 않고,
        # 로그인 personalized=true일 때 user_profile만 개인화에 적용합니다.
        active_profile = user_profile if not guest else {}
        profile_enabled = bool(not guest and personalized and active_profile)
        _ = guest_session_id, guest_room_id, guest_profile

        # 수정 포인트: 후속 질문 해석은 최근 3턴만 사용합니다.
        # 오래된 대화/온보딩 profile이 현재 참조형 질문을 덮어쓰지 않게 합니다.
        original_history = self.context.recent_turn_messages(history or [], turn_limit=3)
        original_history_text = self.context.make_structured_history_text(original_history, turn_limit=3)

        classifier_profile_context = self.profile_context.make_intent_profile_text(
            profile=active_profile,
            guest=guest,
        ) if profile_enabled else ""
        with stage_timer.measure("intent_classification"):
            intent = self.intent_classifier.classify(
                query=query,
                history=original_history,
                history_text=original_history_text,
                profile_context=classifier_profile_context,
            )

        if profile_enabled:
            active_profile = self._profile_with_recommendation_context(active_profile, intent)

        force_service_with_history = self.policy.is_recommendation_explanation_request(query)
        effective_history = original_history if intent.requires_history or force_service_with_history else []
        query_type = "service" if force_service_with_history else intent.query_type

        previous_scope = self.multiturn_policy.resolve(
            intent=intent,
            history=original_history,
        )
        if previous_scope.has_previous_signal and not effective_history:
            effective_history = original_history

        if query_type == "unsupported":
            response = self._with_mode_metadata(
                response=self._unsupported_response(query),
                guest=guest,
                personalized=personalized,
                profile_applied=profile_enabled,
                intent=intent,
                embedding_model=embedding_model,
                ranking_model=ranking_model,
                recommendation_strategy=recommendation_strategy,
                personalization_model=personalization_model,
                reranker_provider=reranker_provider,
                bm25_enabled=bm25_enabled,
                request_id=request_id,
            )
            return self._attach_timing_metadata(response=response, stage_timer=stage_timer, request_id=request_id)

        if query_type == "service":
            response = self._answer_service_query(
                query=query,
                history=effective_history,
                profile=active_profile if profile_enabled else None,
                guest=guest,
                personalized=personalized,
                profile_applied=profile_enabled,
                intent=intent,
                embedding_model=embedding_model,
                ranking_model=ranking_model,
                recommendation_strategy=recommendation_strategy,
                personalization_model=personalization_model,
                reranker_provider=reranker_provider,
                bm25_enabled=bm25_enabled,
                request_id=request_id,
                stage_timer=stage_timer,
            )
            return self._attach_timing_metadata(response=response, stage_timer=stage_timer, request_id=request_id)

        # 수정 포인트: 현재 질의가 명시적으로 requires_history로 분류되지 않아도
        # 추천 질의에서는 최근 구조화 history를 전달합니다. 내부 resolver가 안전한 경우에만
        # 이전 소비 상황/청취 모드를 승계하므로, 새 조건을 덮어쓰지 않습니다.
        recommendation_history = original_history or effective_history

        response = self._answer_recommendation_query(
            query=query,
            personalized=personalized,
            history=recommendation_history,
            active_profile=active_profile,
            profile_enabled=profile_enabled,
            previous_scope=previous_scope,
            guest=guest,
            intent=intent,
            user_id=user_id,
            embedding_model=embedding_model,
            ranking_model=ranking_model,
            recommendation_strategy=recommendation_strategy,
            personalization_model=personalization_model,
            reranker_provider=reranker_provider,
            bm25_enabled=bm25_enabled,
            request_id=request_id,
            stage_timer=stage_timer,
            audience_label_map=audience_label_map,
        )
        return self._attach_timing_metadata(response=response, stage_timer=stage_timer, request_id=request_id)

    def _answer_service_query(
        self,
        query: str,
        history: List[Dict[str, Any]],
        profile: Dict[str, Any] | None,
        guest: bool,
        personalized: bool,
        profile_applied: bool,
        intent: ChatIntent,
        embedding_model: str = "CLOVA",
        ranking_model: str = "LIGHTFM",
        recommendation_strategy: str = "AUTO_HYBRID",
        personalization_model: str = "LIGHTFM",
        reranker_provider: str = "NONE",
        bm25_enabled: bool = False,
        request_id: str | None = None,
        stage_timer: StageTimer | None = None,
        audience_label_map: Dict[str, Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        user_prompt = self.prompt_builder.build_general_user_prompt(
            query=query,
            history=history,
        )

        if profile_applied:
            user_prompt = self.prompt_builder.attach_profile_to_prompt(
                user_prompt=user_prompt,
                profile=profile,
                guest=guest,
            )

        with (stage_timer.measure("service_answer_llm") if stage_timer is not None else nullcontext()):
            answer = self.clova.chat_completion(
                system_prompt=self.prompt_builder.general_system_prompt(),
                user_prompt=user_prompt,
            )

        return self._with_mode_metadata(
            response={
                "query": query,
                "answer": answer,
                "ori_cover_s": None,
                "cover_url": None,
                "cover": None,
                "candidates": [],
            },
            guest=guest,
            personalized=personalized,
            profile_applied=profile_applied,
            intent=intent,
            embedding_model=embedding_model,
            ranking_model=ranking_model,
            recommendation_strategy=recommendation_strategy,
            personalization_model=personalization_model,
            reranker_provider=reranker_provider,
            bm25_enabled=bm25_enabled,
            request_id=request_id,
        )

    def _answer_recommendation_query(
        self,
        query: str,
        personalized: bool,
        history: List[Dict[str, Any]],
        active_profile: Dict[str, Any],
        profile_enabled: bool,
        previous_scope: PreviousRecommendationScope,
        guest: bool,
        intent: ChatIntent,
        user_id: str | None = None,
        embedding_model: str = "CLOVA",
        ranking_model: str = "LIGHTFM",
        recommendation_strategy: str = "AUTO_HYBRID",
        personalization_model: str = "LIGHTFM",
        reranker_provider: str = "NONE",
        bm25_enabled: bool = False,
        request_id: str | None = None,
        stage_timer: StageTimer | None = None,
        audience_label_map: Dict[str, Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        stage_started_at = perf_counter()
        with (stage_timer.measure("query_intent_parse") if stage_timer is not None else nullcontext()):
            query_intent = self.query_parser.parse(query, chat_intent=intent)

        with (stage_timer.measure("multiturn_intent_context") if stage_timer is not None else nullcontext()):
            inherited_context = self.multiturn_intent_context.resolve(
                history=history,
                current_intent=query_intent,
            )
            if inherited_context.applied:
                query_intent = self.multiturn_intent_context.apply(
                    current_intent=query_intent,
                    inheritance=inherited_context,
                )
                print(
                    f"[MULTITURN INTENT CONTEXT][{request_id or '-'}] "
                    f"applied=True source={inherited_context.source} "
                    f"reading_mode={inherited_context.inherited_reading_mode} "
                    f"audience_group={inherited_context.inherited_requested_audience_group} "
                    f"reason={inherited_context.reason}"
                )

        with (stage_timer.measure("multiturn_reference_resolve") if stage_timer is not None else nullcontext()):
            reference_context = self.reference_resolver.resolve(
                query=query,
                history=history,
                intent=intent,
                query_intent=query_intent,
            )
        audience_requested = self._has_requested_audience(query_intent=query_intent, intent=intent)
        final_recommendation_limit = self._resolve_final_recommendation_limit(query_intent)

        retriever = self._resolve_retriever(embedding_model, bm25_enabled=bm25_enabled)
        with (stage_timer.measure("personalization_decision") if stage_timer is not None else nullcontext()):
            personalization_decision = self.personalization_router.decide(
                query=query,
                profile=active_profile,
                profile_enabled=profile_enabled,
                query_intent=query_intent,
                chat_intent=intent,
                context_reference_detected=reference_context.requires_context_priority,
            )
        profile_search_signal_available = (
            self.profile_context.has_positive_search_signal(profile=active_profile, guest=guest)
            if profile_enabled
            else False
        )

        with (stage_timer.measure("search_query_build") if stage_timer is not None else nullcontext()):
            query_search_query = self._build_search_query(
                query=query,
                history=history,
                intent=intent,
                profile=active_profile,
                profile_enabled=profile_enabled,
                guest=guest,
                personalization_decision=personalization_decision,
                retriever=retriever,
                query_intent=query_intent,
                profile_query=False,
                reference_context=reference_context,
            )
            profile_search_query = self._build_search_query(
                query=query,
                history=history,
                intent=intent,
                profile=active_profile,
                profile_enabled=profile_enabled,
                guest=guest,
                personalization_decision=personalization_decision,
                retriever=retriever,
                query_intent=query_intent,
                profile_query=True,
                reference_context=reference_context,
            )
            profile_query_seed = "" if (
                profile_enabled
                and personalization_decision.mode == PersonalizationMode.PROFILE_FIRST
                and query_intent.broad_recommendation
            ) else query_search_query
            profile_search_queries = (
                self.profile_context.build_diverse_profile_search_queries(
                    query=profile_query_seed,
                    profile=active_profile,
                    guest=guest,
                    max_queries=6,
                )
                if profile_enabled and profile_search_signal_available
                else []
            )

        search_limit = self.pipeline_config.qdrant_candidate_limit

        with (stage_timer.measure("qdrant_search") if stage_timer is not None else nullcontext()):
            candidates = self._search_candidates_by_personalization_mode(
                query_search_query=query_search_query,
                profile_search_query=profile_search_query,
                profile_search_queries=profile_search_queries,
                search_limit=search_limit,
                decision=personalization_decision,
                retriever=retriever,
                query_intent=query_intent,
                profile_search_signal_available=profile_search_signal_available,
                final_recommendation_limit=final_recommendation_limit,
            )
        effective_embedding_model = embedding_model
        retrieval_metadata = dict(getattr(retriever, "last_retrieval_metadata", {}) or {})
        print(
            f"[RETRIEVAL STRATEGY][{request_id or '-'}] "
            f"bm25_enabled={bm25_enabled} requested={retrieval_metadata.get('requested_strategy')} "
            f"used={retrieval_metadata.get('used_strategy')} fallback={retrieval_metadata.get('fallback', False)} "
            f"collection={retrieval_metadata.get('collection')}"
        )
        if bm25_enabled and not candidates:
            print(
                f"[RETRIEVAL FALLBACK][{request_id or '-'}] "
                "reason=empty_hybrid_candidates used_strategy=dense_lookup"
            )
            retriever = self._resolve_retriever(embedding_model, bm25_enabled=False)
            with (stage_timer.measure("qdrant_hybrid_empty_fallback_search") if stage_timer is not None else nullcontext()):
                candidates = self._search_candidates_by_personalization_mode(
                    query_search_query=query_search_query,
                    profile_search_query=profile_search_query,
                    profile_search_queries=profile_search_queries,
                    search_limit=search_limit,
                    decision=personalization_decision,
                    retriever=retriever,
                    query_intent=query_intent,
                    profile_search_signal_available=profile_search_signal_available,
                    final_recommendation_limit=final_recommendation_limit,
                )
            retrieval_metadata = {
                "requested_strategy": "dense_bm25_rrf",
                "used_strategy": "dense_lookup",
                "fallback": True,
                "fallback_reason": "empty_hybrid_candidates",
                "collection": getattr(retriever, "collection_name", None),
            }
        if not retrieval_metadata:
            retrieval_metadata = dict(getattr(retriever, "last_retrieval_metadata", {}) or {})
        if not candidates and embedding_model == "KURE" and bool(settings.KURE_FALLBACK_TO_CLOVA):
            print("[KURE FALLBACK] no KURE candidates. retrying with CLOVA retriever")
            retriever = self.clova_retriever
            effective_embedding_model = "CLOVA"
            retrieval_metadata = {
                "requested_strategy": "dense_bm25_rrf" if bm25_enabled else "dense_lookup",
                "used_strategy": "dense_lookup",
                "fallback": True,
                "fallback_reason": "kure_empty_candidates",
                "collection": getattr(retriever, "collection_name", None),
            }
            with (stage_timer.measure("qdrant_fallback_search") if stage_timer is not None else nullcontext()):
                candidates = self._search_candidates_by_personalization_mode(
                    query_search_query=query_search_query,
                    profile_search_query=profile_search_query,
                    profile_search_queries=profile_search_queries,
                    search_limit=search_limit,
                    decision=personalization_decision,
                    retriever=retriever,
                    query_intent=query_intent,
                    profile_search_signal_available=profile_search_signal_available,
                    final_recommendation_limit=final_recommendation_limit,
                )

        self._log_candidate_stage(request_id, "qdrant_search", candidates, stage_started_at)

        if not candidates:
            return self._recommendation_empty(
                query,
                guest,
                personalized,
                profile_enabled,
                intent,
                personalization_decision,
                query_intent=query_intent,
                embedding_model=effective_embedding_model,
                ranking_model=ranking_model,
                recommendation_strategy=recommendation_strategy,
                personalization_model=personalization_model,
                reranker_provider=reranker_provider,
                bm25_enabled=bm25_enabled,
                retrieval_metadata=retrieval_metadata,
                request_id=request_id,
            )

        with (stage_timer.measure("qdrant_prepare") if stage_timer is not None else nullcontext()):
            candidates = self.pipeline.prepare_qdrant_candidates(candidates)
        self._log_candidate_stage(request_id, "prepared", candidates, stage_started_at)
        with (stage_timer.measure("candidate_dedupe") if stage_timer is not None else nullcontext()):
            candidates = self.candidate_filter.dedupe_candidates(candidates)
        self._log_candidate_stage(request_id, "deduped", candidates, stage_started_at)
        baseline_candidates = list(candidates)
        with (stage_timer.measure("candidate_filters") if stage_timer is not None else nullcontext()):
            candidates = self._apply_candidate_filters(
                query=query,
                search_query=(
                    query_search_query
                    if personalization_decision.mode != PersonalizationMode.PROFILE_FIRST
                    else profile_search_query
                ),
                candidates=candidates,
                previous_scope=previous_scope,
                query_intent=query_intent,
                profile=active_profile if profile_enabled else {},
                request_id=request_id,
                reference_context=reference_context,
                min_remaining=final_recommendation_limit,
            )
        self._log_candidate_stage(request_id, "candidate_filters", candidates, stage_started_at)
        if query_intent.general_recommendation and len(candidates) < final_recommendation_limit:
            candidates = self._recover_general_recommendation_candidates(
                filtered_candidates=candidates,
                baseline_candidates=baseline_candidates,
                query=query,
                previous_scope=previous_scope,
                profile=active_profile if profile_enabled else {},
                query_intent=query_intent,
                request_id=request_id,
                min_needed=final_recommendation_limit,
            )
            self._log_candidate_stage(request_id, "general_recovery", candidates, stage_started_at)
        if not candidates:
            return self._recommendation_empty(
                query,
                guest,
                personalized,
                profile_enabled,
                intent,
                personalization_decision,
                query_intent=query_intent,
                embedding_model=effective_embedding_model,
                ranking_model=ranking_model,
                recommendation_strategy=recommendation_strategy,
                personalization_model=personalization_model,
                reranker_provider=reranker_provider,
                bm25_enabled=bm25_enabled,
                retrieval_metadata=retrieval_metadata,
                request_id=request_id,
            )

        with (stage_timer.measure("rule_stage") if stage_timer is not None else nullcontext()):
            candidates = self.pipeline.apply_rule_stage(candidates)
        self._log_candidate_stage(request_id, "rule_stage", candidates, stage_started_at)

        if profile_enabled or audience_requested:
            audience_profile = (
                active_profile
                if profile_enabled
                else self._audience_request_profile(query_intent=query_intent, intent=intent)
            )
            should_attach_audience_labels = bool(
                audience_requested
                or audience_label_map
                or bool(getattr(settings, "AUDIENCE_LABEL_ENABLE_FOR_PROFILE_RERANK", False))
            )

            if should_attach_audience_labels:
                with (stage_timer.measure("audience_label") if stage_timer is not None else nullcontext()):
                    candidates = self.audience_classifier.attach_labels(
                        candidates=candidates,
                        user_profile=audience_profile,
                        requested_audience_group=query_intent.requested_audience_group,
                        requested_education_stage=query_intent.requested_education_stage,
                        request_id=request_id,
                        audience_label_map=audience_label_map or {},
                    )
                self._log_candidate_stage(request_id, "audience_label", candidates, stage_started_at)
            else:
                print(
                    f"[AUDIENCE LABEL SKIPPED][{request_id or '-'}] "
                    "reason=no_ready_db_label_and_no_explicit_audience_request"
                )

            if profile_enabled:
                negative_terms = self.profile_context.extract_negative_profile_terms(
                    profile=active_profile,
                    guest=guest,
                )
                candidates = self.candidate_filter.filter_disliked_candidates_by_profile(
                    candidates=candidates,
                    negative_terms=negative_terms,
                )

            with (
                stage_timer.measure("profile_rerank" if profile_enabled else "audience_rerank")
                if stage_timer is not None
                else nullcontext()
            ):
                candidates = self.reranker.rerank(
                    candidates=candidates,
                    profile=audience_profile,
                    personalized=True,
                    mode=personalization_decision.mode.value if profile_enabled else "QUERY_FIRST",
                )
            self._log_candidate_stage(
                request_id,
                "profile_rerank" if profile_enabled else "audience_rerank",
                candidates,
                stage_started_at,
            )

        # 수정 포인트: ranking router는 RULE_BASED에서도 공통 stage/timing을 위해 항상 호출합니다.
        # 다만 user_id는 로그인 사용자에게만 존재하므로, 누락/공백이면 None으로 정규화해
        # LIGHTFM 미사용 또는 비로그인 요청에서 NameError/불필요한 예외가 발생하지 않게 합니다.
        safe_user_id = user_id.strip() if isinstance(user_id, str) and user_id.strip() else None

        with (stage_timer.measure("model_ranking_stage") if stage_timer is not None else nullcontext()):
            model_ranking_result = self.ranking_router.rerank(
                recommendation_strategy=recommendation_strategy,
                personalization_model=personalization_model,
                ranking_model=ranking_model,
                user_id=safe_user_id,
                candidates=candidates,
                limit=self.pipeline_config.personalization_candidate_limit,
                request_id=request_id,
            )
        ranking_stage_metadata = model_ranking_result.as_metadata()
        if model_ranking_result.applied:
            candidates = model_ranking_result.candidates
            self._log_candidate_stage(request_id, f"{ranking_model.lower()}_ranking_stage", candidates, stage_started_at)
        else:
            if model_ranking_result.fallback:
                print(
                    f"[RANKING MODEL FALLBACK][{request_id or '-'}] "
                    f"requested={ranking_model} applied={model_ranking_result.applied_model} "
                    f"reason={model_ranking_result.fallback_reason}"
                )
            with (stage_timer.measure("personalization_stage") if stage_timer is not None else nullcontext()):
                if guest or personalization_model == "NONE" or recommendation_strategy == "RULE_BASED_ONLY":
                    candidates = self.anonymous_selector.select(
                        candidates,
                        limit=self.pipeline_config.personalization_candidate_limit,
                    )
                else:
                    candidates = self.pipeline.apply_personalization_stage(candidates, enabled=profile_enabled)
            self._log_candidate_stage(request_id, "personalization_stage", candidates, stage_started_at)

        with (stage_timer.measure("external_rerank_stage") if stage_timer is not None else nullcontext()):
            rerank_query = self._resolve_external_rerank_query(
                original_query=query,
                query_search_query=query_search_query,
                query_intent=query_intent,
                reference_context=reference_context,
            )
            rerank_result = self.rerank_service.rerank(
                provider=reranker_provider,
                query=rerank_query,
                candidates=candidates,
                user_profile=active_profile if profile_enabled else {},
                guest=guest,
                request_id=request_id,
            )
            candidates = rerank_result.candidates
        rerank_stage_metadata = rerank_result.as_metadata()
        # 수정 포인트: GTE reranker의 primary/fallback 실행시간을 운영 로그에서 바로 확인할 수 있게
        # 추천 파이프라인 로그와 별도로 전용 summary 로그를 남깁니다.
        self._log_reranker_stage(request_id=request_id, metadata=rerank_stage_metadata)
        if rerank_result.fallback:
            print(
                f"[RERANKER FALLBACK][{request_id or '-'}] "
                f"provider={rerank_result.provider} reason={rerank_result.fallback_reason}"
            )
        self._log_candidate_stage(request_id, "external_rerank_stage", candidates, stage_started_at)

        with (stage_timer.measure("score_fusion_stage") if stage_timer is not None else nullcontext()):
            candidates = self.score_fusion.fuse(
                candidates=candidates,
                guest=guest,
                personalization_available=bool(model_ranking_result.applied),
                reranker_available=bool(rerank_result.applied),
            )

        # 수정 포인트: 사용자가 "한 권만"처럼 최종 1권을 명시했고 외부 reranker가 적용된 경우,
        # diversity/fusion 보정으로 1등이 뒤집히지 않도록 rerankerScore 기준 1순위를 최종 후보로 고정합니다.
        if final_recommendation_limit == 1 and rerank_result.applied:
            candidates = prioritize_single_result_by_reranker(candidates, request_id=request_id)

        with (stage_timer.measure("final_stage") if stage_timer is not None else nullcontext()):
            candidates = self.pipeline.apply_final_reranker_stage(candidates, final_limit=final_recommendation_limit)
        self._log_candidate_stage(request_id, "final_stage", candidates, stage_started_at)

        recommend_count = min(final_recommendation_limit, len(candidates))
        top_candidates = candidates[:recommend_count]
        recommended_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        for rank, candidate in enumerate(top_candidates, start=1):
            candidate["rank"] = rank
            candidate["recommended_at"] = candidate.get("recommended_at") or recommended_at

        reason_status = "COMPLETED"
        reason_error_message = None
        if self._should_generate_reasons_async():
            with (stage_timer.measure("reason_enqueue") if stage_timer is not None else nullcontext()):
                answer = self._make_pending_recommendation_answer(top_candidates)
                self._mark_recommendation_reasons_pending(top_candidates)
                # 수정 포인트: 비로그인 추천 이유를 후보별 LLM 호출로 처리하면
                # 카드 5권 기준으로 CLOVA 호출이 5배 증가하고 429/쿨다운이 쉽게 발생합니다.
                # 로그인 경로와 동일하게 최종 후보 전체를 한 번의 batch prompt로 생성해
                # 요청 폭증 없이 정상 추천 이유를 만들도록 합니다.
                queued_request_id = recommendation_reason_jobs.submit(
                    request_id=request_id,
                    candidates=top_candidates,
                    generator=lambda: self._make_reasoned_recommendation_result(
                        query=query,
                        candidates=top_candidates,
                        personalization_mode=personalization_decision.mode.value,
                        request_id=request_id,
                    ),
                )
            reason_status = "PENDING" if queued_request_id else "SKIPPED"
            reason_error_message = None if queued_request_id else "missing request_id"
            print(
                f"[RECOMMENDATION REASON][{request_id or '-'}] "
                f"mode=ASYNC_BATCH status={reason_status} candidate_count={len(top_candidates)}"
            )
        else:
            with (stage_timer.measure("reason_generation") if stage_timer is not None else nullcontext()):
                answer = self._make_reasoned_recommendation_answer(
                    query=query,
                    candidates=top_candidates,
                    personalization_mode=personalization_decision.mode.value,
                    request_id=request_id,
                )
            answer = self.policy.renumber_recommendation_answer(answer)
        top_book = top_candidates[0]
        ori_cover_s = top_book.get("ori_cover_s")
        cover_url = top_book.get("cover_url") or ori_cover_s or top_book.get("cover")
        return self._with_mode_metadata(
            response={
                "query": query,
                "answer": answer,
                "ori_cover_s": ori_cover_s,
                "cover_url": cover_url,
                "cover": cover_url,
                "candidates": top_candidates,
                "recommendation_reason_status": reason_status,
                "recommendation_reason_error_message": reason_error_message,
            },
            guest=guest,
            personalized=personalized,
            profile_applied=profile_enabled,
            intent=intent,
            personalization_decision=personalization_decision,
            query_intent=query_intent,
            embedding_model=effective_embedding_model,
            ranking_model=ranking_model,
            recommendation_strategy=recommendation_strategy,
            personalization_model=personalization_model,
            reranker_provider=reranker_provider,
            bm25_enabled=bm25_enabled,
            retrieval_metadata=retrieval_metadata,
            request_id=request_id,
            ranking_stage_metadata=ranking_stage_metadata,
            rerank_stage_metadata=rerank_stage_metadata,
            reference_context=reference_context,
            final_recommendation_limit=final_recommendation_limit,
        )

    def _build_search_query(
        self,
        query: str,
        history: List[Dict[str, Any]],
        intent: ChatIntent,
        profile: Dict[str, Any],
        profile_enabled: bool,
        guest: bool,
        personalization_decision: PersonalizationDecision,
        retriever: BookQdrantSearcher | BookKureQdrantSearcher,
        query_intent: QueryIntent | None = None,
        profile_query: bool = False,
        reference_context: ResolvedReferenceContext | None = None,
    ) -> str:
        if reference_context is not None and reference_context.seed_query and not profile_query:
            # 수정 포인트: "두 번째 책과 비슷한 책" 같은 질의는 현재 query 표면형보다
            # 직전 추천 카드의 title/author/category/description을 retrieval seed로 먼저 사용합니다.
            search_query = self.policy.normalize_search_query(reference_context.seed_query)
        elif retriever.is_precise_lookup_query(query):
            search_query = query.strip()
        elif query_intent is not None and query_intent.retrieval_query:
            search_query = self.policy.normalize_search_query(query_intent.retrieval_query)
        else:
            search_query = self.policy.normalize_search_query(query)

        if intent.requires_history and intent.query_type == "recommend":
            history_hint = self.context.make_history_search_hint(history)
            if history_hint:
                search_query = f"{search_query} {history_hint}".strip()

        if not profile_enabled:
            return search_query

        if personalization_decision.mode == PersonalizationMode.QUERY_FIRST:
            return search_query

        if personalization_decision.mode == PersonalizationMode.PROFILE_FIRST:
            # 수정 포인트: broad로 분류되더라도 사용자가 현재 질의에 주제/장르를 붙여 쓴 경우가 있습니다.
            # 검색어를 비우면 "판타지소설 추천" 같은 질의가 프로필/일반 후보로만 흐르므로 원 질의 검색어는 유지합니다.
            return self.profile_context.build_profile_focused_search_query(
                query=search_query,
                profile=profile,
                guest=guest,
            )

        if personalization_decision.mode == PersonalizationMode.HYBRID and profile_query:
            return self.profile_context.build_profile_focused_search_query(
                query=search_query,
                profile=profile,
                guest=guest,
            )

        return search_query


    @staticmethod
    def _resolve_external_rerank_query(
        *,
        original_query: str,
        query_search_query: str,
        query_intent: QueryIntent,
        reference_context: ResolvedReferenceContext | None = None,
    ) -> str:
        if reference_context is not None and reference_context.seed_query:
            return reference_context.seed_query

        # 수정 포인트: 외부 reranker에는 retrieval용 검색어보다 reranker 전용 정규화 query를 먼저 전달합니다.
        # QueryIntentParser가 이미 소비 상황 contamination check를 통과한 값만 채우므로,
        # topic query와 consumption context를 여기서 다시 섞지 않고 안전한 fallback 순서만 적용합니다.
        for candidate_query in [
            getattr(query_intent, "reranker_query", None),
            getattr(query_intent, "retrieval_query", None),
            query_search_query,
            original_query,
        ]:
            text = str(candidate_query or "").strip()
            if text:
                return text
        return original_query

    def _search_candidates_by_personalization_mode(
        self,
        query_search_query: str,
        profile_search_query: str,
        profile_search_queries: List[str] | None,
        search_limit: int,
        decision: PersonalizationDecision,
        retriever: BookQdrantSearcher | BookKureQdrantSearcher,
        query_intent: QueryIntent,
        profile_search_signal_available: bool = True,
        final_recommendation_limit: int | None = None,
    ) -> List[Dict[str, Any]]:
        query_search_query = str(query_search_query or "").strip()
        profile_search_query = str(profile_search_query or "").strip()
        profile_search_queries = [
            str(value or "").strip()
            for value in (profile_search_queries or [])
            if str(value or "").strip()
        ]

        if query_intent.is_precise_lookup:
            return retriever.search_by_intent(query_intent=query_intent, limit=search_limit)

        if decision.mode == PersonalizationMode.HYBRID and profile_search_query != query_search_query:
            query_limit = max(10, int(search_limit * 0.6))
            query_candidates = self._search_query_variants(retriever, query_search_query, query_limit, query_intent) if query_search_query else []
            query_candidates = self._merge_listening_mode_candidates(
                retriever=retriever,
                base_candidates=query_candidates,
                query_intent=query_intent,
                query=query_search_query,
                search_limit=query_limit,
            )
            profile_queries = profile_search_queries or ([profile_search_query] if profile_search_signal_available and profile_search_query else [])
            remaining_limit = max(10, search_limit - query_limit)
            per_profile_limit = max(5, int(remaining_limit / max(len(profile_queries), 1)))
            profile_candidates: List[Dict[str, Any]] = []
            for profile_query in profile_queries:
                profile_candidates.extend(retriever.search(query=profile_query, limit=per_profile_limit))
            merged_candidates = self._merge_candidates(query_candidates, profile_candidates)
            return self._augment_broad_recommendation_candidates(
                candidates=merged_candidates,
                retriever=retriever,
                query_intent=query_intent,
                search_limit=search_limit,
                min_needed=final_recommendation_limit,
            )

        if decision.mode == PersonalizationMode.PROFILE_FIRST:
            profile_queries = profile_search_queries or ([profile_search_query] if profile_search_signal_available and profile_search_query else [])
            if not profile_queries:
                print(
                    "[PROFILE SEARCH SKIPPED] "
                    f"reason=no_positive_profile_search_signal broad={query_intent.broad_recommendation}"
                )
                if query_search_query:
                    query_candidates = self._search_query_variants(retriever, query_search_query, search_limit, query_intent)
                    query_candidates = self._merge_listening_mode_candidates(
                        retriever=retriever,
                        base_candidates=query_candidates,
                        query_intent=query_intent,
                        query=query_search_query,
                        search_limit=search_limit,
                    )
                    if query_candidates:
                        return self._augment_broad_recommendation_candidates(
                            candidates=query_candidates,
                            retriever=retriever,
                            query_intent=query_intent,
                            search_limit=search_limit,
                            min_needed=final_recommendation_limit,
                        )
                if query_intent.broad_recommendation:
                    return self._general_candidates(retriever=retriever, search_limit=search_limit)
                return []

            if len(profile_queries) > 1:
                per_profile_limit = max(8, int(search_limit / len(profile_queries)))
                profile_candidates: List[Dict[str, Any]] = []
                for profile_query in profile_queries:
                    profile_candidates.extend(retriever.search(query=profile_query, limit=per_profile_limit))
                merged_candidates = self._merge_candidates([], profile_candidates)
                merged_candidates = self._merge_listening_mode_candidates(
                    retriever=retriever,
                    base_candidates=merged_candidates,
                    query_intent=query_intent,
                    query=query_search_query,
                    search_limit=search_limit,
                )
                return self._augment_broad_recommendation_candidates(
                    candidates=merged_candidates,
                    retriever=retriever,
                    query_intent=query_intent,
                    search_limit=search_limit,
                    min_needed=final_recommendation_limit,
                )

            profile_candidates = retriever.search(query=profile_queries[0], limit=search_limit)
            profile_candidates = self._merge_listening_mode_candidates(
                retriever=retriever,
                base_candidates=profile_candidates,
                query_intent=query_intent,
                query=query_search_query,
                search_limit=search_limit,
            )
            return self._augment_broad_recommendation_candidates(
                candidates=profile_candidates,
                retriever=retriever,
                query_intent=query_intent,
                search_limit=search_limit,
                min_needed=final_recommendation_limit,
            )

        query_candidates = self._search_query_variants(retriever, query_search_query, search_limit, query_intent) if query_search_query else []
        query_candidates = self._merge_listening_mode_candidates(
            retriever=retriever,
            base_candidates=query_candidates,
            query_intent=query_intent,
            query=query_search_query,
            search_limit=search_limit,
        )
        return self._augment_broad_recommendation_candidates(
            candidates=query_candidates,
            retriever=retriever,
            query_intent=query_intent,
            search_limit=search_limit,
            min_needed=final_recommendation_limit,
        )

    def _merge_listening_mode_candidates(
        self,
        *,
        retriever: BookQdrantSearcher | BookKureQdrantSearcher,
        base_candidates: List[Dict[str, Any]],
        query_intent: QueryIntent,
        query: str,
        search_limit: int,
    ) -> List[Dict[str, Any]]:
        mode = str(getattr(query_intent, "reading_mode", ReadingModePolicy.MODE_UNKNOWN) or "").strip().upper()
        if mode != ReadingModePolicy.MODE_LISTENING_FRIENDLY:
            return base_candidates

        search_listening_mode = getattr(retriever, "search_listening_mode", None)
        if not callable(search_listening_mode):
            return base_candidates

        # 수정 포인트: LISTENING_FRIENDLY는 형식 요구가 강한 질의입니다.
        # 원문 질의의 활동명(운전/산책 등)이나 난이도 표현이 검색어로 재주입되지 않도록
        # source-format 후보 검색에는 정규화된 오디오북 seed만 사용합니다.
        listening_query = ReadingModePolicy.listening_format_query()
        try:
            listening_candidates = search_listening_mode(query=listening_query, limit=search_limit)
        except Exception as exc:
            print(f"[LISTENING FORMAT SEARCH FAILED] error={exc}")
            return []

        if not listening_candidates:
            print(
                f"[LISTENING FORMAT SEARCH] base={len(base_candidates or [])} "
                f"listening=0 query={listening_query!r} action=return_empty"
            )
            return []

        print(
            f"[LISTENING FORMAT SEARCH] base={len(base_candidates or [])} "
            f"listening={len(listening_candidates)} query={listening_query!r} action=audio_only"
        )
        return listening_candidates[:search_limit]

    def _search_query_variants(
        self,
        retriever: BookQdrantSearcher | BookKureQdrantSearcher,
        query: str,
        limit: int,
        query_intent: QueryIntent,
    ) -> List[Dict[str, Any]]:
        variants = self._build_query_variants(query=query, query_intent=query_intent)
        if not variants:
            return []
        if len(variants) == 1:
            return retriever.search(query=variants[0], limit=limit)

        per_variant_limit = max(8, int(limit / len(variants)))
        merged: List[Dict[str, Any]] = []
        for variant in variants:
            merged.extend(retriever.search(query=variant, limit=per_variant_limit))
        merged_candidates = self._merge_candidates([], merged)
        print(
            f"[QUERY VARIANT SEARCH] variants={len(variants)} "
            f"merged={len(merged_candidates)} primary={variants[0]!r}"
        )
        return merged_candidates[:limit]

    def _build_query_variants(self, query: str, query_intent: QueryIntent) -> List[str]:
        # 수정 포인트: "판타지소설"처럼 붙여 쓴 한국어 복합명사는 소스 코드에
        # 자연어 치환표를 박지 않고, 일반적인 Hangul compound spacing variant를 생성해 검색합니다.
        # 기존 title-only guardrail은 그대로 유지되어 제목 echo만 맞는 후보가 다시 상위로 올라오지 않게 합니다.
        variant_result = self.query_variant_builder.build(
            query=query,
            query_intent=query_intent,
            limit=6,
        )
        return variant_result.variants

    @staticmethod
    def _general_candidates(
        *,
        retriever: BookQdrantSearcher | BookKureQdrantSearcher,
        search_limit: int,
    ) -> List[Dict[str, Any]]:
        general_search = getattr(retriever, "search_general", None)
        if not callable(general_search):
            return []
        try:
            return general_search(limit=search_limit)
        except Exception as exc:
            print(f"[GENERAL RECOMMENDATION SEARCH SKIPPED] error={exc}")
            return []

    def _augment_broad_recommendation_candidates(
        self,
        *,
        candidates: List[Dict[str, Any]],
        retriever: BookQdrantSearcher | BookKureQdrantSearcher,
        query_intent: QueryIntent,
        search_limit: int,
        min_needed: int | None = None,
    ) -> List[Dict[str, Any]]:
        if not query_intent.broad_recommendation:
            return candidates
        required_count = max(1, int(min_needed or self.pipeline_config.final_recommendation_limit))
        if len(candidates) >= required_count:
            return candidates

        general_search = getattr(retriever, "search_general", None)
        if not callable(general_search):
            return candidates

        try:
            fallback_candidates = general_search(limit=search_limit)
        except Exception as exc:
            print(f"[GENERAL RECOMMENDATION AUGMENT SKIPPED] error={exc}")
            return candidates

        if not fallback_candidates:
            return candidates

        merged = self._merge_candidates(candidates, fallback_candidates)
        print(
            f"[GENERAL RECOMMENDATION AUGMENT] "
            f"primary={len(candidates)} fallback={len(fallback_candidates)} merged={len(merged)}"
        )
        return merged[:search_limit]

    @staticmethod
    def _merge_candidates(
        primary_candidates: List[Dict[str, Any]],
        secondary_candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen = set()

        for candidate in [*primary_candidates, *secondary_candidates]:
            isbn = str(candidate.get("isbn") or candidate.get("isbn13") or "").strip().lower()
            title = str(candidate.get("title") or "").strip().lower()
            author = str(candidate.get("author") or "").strip().lower()
            key = isbn or f"{title}|{author}"
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(candidate)

        return merged

    @staticmethod
    def _resolve_search_limit(
        previous_scope: PreviousRecommendationScope,
        profile_enabled: bool,
        guest: bool,
    ) -> int:
        if profile_enabled:
            search_limit = max(int(settings.TOP_K), 80)
        elif guest:
            search_limit = max(int(settings.TOP_K), int(settings.GUEST_TOP_K), 30)
        else:
            search_limit = max(int(settings.TOP_K), 50)

        previous_count = len(previous_scope.hard_books) + len(previous_scope.soft_books) if previous_scope else 0
        if previous_count:
            upper_bound = 80 if profile_enabled else 50
            search_limit = min(
                upper_bound,
                max(
                    search_limit,
                    int(settings.TOP_K) + previous_count + 6,
                ),
            )

        return search_limit

    def _apply_candidate_filters(
        self,
        query: str,
        search_query: str,
        candidates: List[Dict[str, Any]],
        previous_scope: PreviousRecommendationScope,
        query_intent: QueryIntent,
        profile: Dict[str, Any] | None = None,
        request_id: str | None = None,
        reference_context: ResolvedReferenceContext | None = None,
        min_remaining: int | None = None,
    ) -> List[Dict[str, Any]]:
        _ = search_query
        candidates = self.candidate_filter.filter_candidates_by_intent(
            query_intent=query_intent,
            candidates=candidates,
        )

        if previous_scope.mode == "HARD_RECENT" and previous_scope.hard_books and candidates:
            candidates = self.candidate_filter.exclude_previous_recommendations(
                candidates=candidates,
                previous_books=previous_scope.hard_books,
            )

        if previous_scope.mode == "SOFT_DECAY" and previous_scope.soft_books and candidates:
            candidates = self.candidate_filter.apply_previous_recommendation_penalty(
                candidates=candidates,
                previous_books=previous_scope.soft_books,
            )

        if reference_context is not None and reference_context.exclude_candidates and candidates:
            # 수정 포인트: "방금 추천한 책은 제외" 같은 후속 질문은 최근 추천 카드 metadata 기준으로 제외합니다.
            candidates = self.candidate_filter.exclude_previous_recommendations(
                candidates=candidates,
                previous_books=reference_context.exclude_candidates,
            )

        gate_result = self.guardrails.apply_relevance_gate(
            candidates=candidates,
            query_intent=query_intent,
            min_remaining=min_remaining or self.pipeline_config.final_recommendation_limit,
        )
        if gate_result.mode != "NONE":
            print(
                f"[RECOMMENDATION GUARDRAIL][{request_id or '-'}] "
                f"mode={gate_result.mode} rules={gate_result.applied_rules} "
                f"excluded={gate_result.excluded_count} penalized={gate_result.penalized_count}"
            )
        return gate_result.candidates

    def _recover_general_recommendation_candidates(
        self,
        filtered_candidates: List[Dict[str, Any]],
        baseline_candidates: List[Dict[str, Any]],
        query: str,
        previous_scope: PreviousRecommendationScope,
        profile: Dict[str, Any] | None,
        query_intent: QueryIntent | None = None,
        request_id: str | None = None,
        min_needed: int | None = None,
    ) -> List[Dict[str, Any]]:
        needed = min_needed or self.pipeline_config.final_recommendation_limit
        if len(filtered_candidates) >= needed:
            return filtered_candidates
        merged = self.candidate_filter.dedupe_candidates([*filtered_candidates, *baseline_candidates])
        if previous_scope.mode == "SOFT_DECAY" and previous_scope.soft_books:
            merged = self.candidate_filter.apply_previous_recommendation_penalty(merged, previous_scope.soft_books)
        recovery_intent = query_intent or QueryIntent(raw_query=query, general_recommendation=True, retrieval_query=query)
        gate_result = self.guardrails.apply_relevance_gate(
            candidates=merged,
            query_intent=recovery_intent,
            min_remaining=needed,
        )
        print(
            f"[RECOMMENDATION RECOVERY][{request_id or '-'}] "
            f"before={len(filtered_candidates)} baseline={len(baseline_candidates)} after={len(gate_result.candidates)} mode={gate_result.mode}"
        )
        return gate_result.candidates

    @staticmethod
    def _attach_timing_metadata(
        *,
        response: Dict[str, Any],
        stage_timer: StageTimer,
        request_id: str | None = None,
    ) -> Dict[str, Any]:
        timings = stage_timer.snapshot()
        pipeline_metadata = dict(response.get("pipeline") or {})
        reranker_stage = dict(pipeline_metadata.get("rerankerStage") or {})
        if reranker_stage:
            # 수정 포인트: StageTimer가 측정한 external_rerank_stage_ms 외에도 provider 내부에서 수집한
            # primary/fallback 세부 latency를 timings metadata와 로그에 같이 노출합니다.
            rerank_total_ms = int(reranker_stage.get("totalLatencyMs") or reranker_stage.get("latencyMs") or 0)
            timings["external_rerank_total_ms"] = rerank_total_ms
            timings["gte_rerank_total_ms"] = rerank_total_ms
            timings["gte_rerank_primary_ms"] = int(reranker_stage.get("primaryLatencyMs") or 0)
            timings["gte_rerank_fallback_ms"] = int(reranker_stage.get("fallbackLatencyMs") or 0)
            timings["gte_rerank_input_count"] = int(reranker_stage.get("inputCount") or 0)
            timings["gte_rerank_output_count"] = int(reranker_stage.get("outputCount") or 0)
        # 수정 포인트: 운영 로그에서 병목이 바로 보이도록 Qdrant/embedding/GTE/reason/total 명칭을 표준화해 같이 노출합니다.
        timings["qdrant_search_time_ms"] = int(timings.get("qdrant_search_ms") or timings.get("qdrant_fallback_search_ms") or 0)
        timings["candidate_filter_time_ms"] = int(
            timings.get("candidate_filters_ms")
            or timings.get("candidate_dedupe_ms")
            or timings.get("qdrant_prepare_ms")
            or 0
        )
        timings["reranker_time_ms"] = int(timings.get("external_rerank_stage_ms") or timings.get("gte_rerank_stage_ms") or timings.get("gte_rerank_total_ms") or 0)
        timings["reason_generation_time_ms"] = int(
            timings.get("reason_generation_ms")
            or timings.get("recommendation_reason_ms")
            or timings.get("reason_enqueue_ms")
            or 0
        )
        timings["total_recommendation_time_ms"] = int(timings.get("total_ms") or 0)
        pipeline_metadata["timings"] = timings
        response["pipeline"] = pipeline_metadata
        response["timings"] = timings
        print(f"[RECOMMENDATION TIMINGS][{request_id or '-'}] {timings}")
        return response

    @staticmethod
    def _log_reranker_stage(*, request_id: str | None, metadata: Dict[str, Any] | None) -> None:
        data = dict(metadata or {})
        print(
            f"[RECOMMENDATION RERANKER TIMINGS][{request_id or '-'}] "
            f"provider={data.get('provider')} applied={data.get('applied')} fallback={data.get('fallback')} "
            f"endpoint_role={data.get('endpointRole') or '-'} reason={data.get('fallbackReason') or '-'} "
            f"total_ms={int(data.get('totalLatencyMs') or data.get('latencyMs') or 0)} "
            f"primary_ms={int(data.get('primaryLatencyMs') or 0)} "
            f"fallback_ms={int(data.get('fallbackLatencyMs') or 0)} "
            f"input_count={int(data.get('inputCount') or 0)} output_count={int(data.get('outputCount') or 0)}"
        )

    @staticmethod
    def _log_candidate_stage(
        request_id: str | None,
        stage: str,
        candidates: List[Dict[str, Any]] | None,
        started_at: float | None = None,
    ) -> None:
        elapsed_ms = int((perf_counter() - started_at) * 1000) if started_at is not None else None
        elapsed_part = f" elapsed_since_request_start_ms={elapsed_ms}" if elapsed_ms is not None else ""
        print(
            f"[RECOMMENDATION PIPELINE][{request_id or '-'}] "
            f"stage={stage} candidate_count={len(candidates or [])}{elapsed_part}"
        )

    @staticmethod
    def _should_generate_reasons_async() -> bool:
        provider = str(settings.RECOMMENDATION_REASON_PROVIDER or "LLM").strip().upper()
        return provider == "LLM" and bool(getattr(settings, "RECOMMENDATION_REASON_ASYNC_ENABLED", True))

    def _make_pending_recommendation_answer(self, candidates: List[Dict[str, Any]]) -> str:
        return self.prompt_builder.make_pending_recommendation_answer(candidates)

    def _mark_recommendation_reasons_pending(self, candidates: List[Dict[str, Any]]) -> None:
        pending_reason = self.prompt_builder.make_pending_recommendation_reason()
        for candidate in candidates:
            candidate["recommendation_reason"] = pending_reason
            candidate["recommendation_reason_source"] = "PENDING"
            candidate["recommendation_reason_status"] = "PENDING"

    def _make_reasoned_recommendation_result(
        self,
        *,
        query: str,
        candidates: List[Dict[str, Any]],
        personalization_mode: str,
        request_id: str | None = None,
    ) -> Dict[str, Any]:
        reason_candidates = copy.deepcopy(candidates or [])
        answer = self._make_reasoned_recommendation_answer(
            query=query,
            candidates=reason_candidates,
            personalization_mode=personalization_mode,
            request_id=request_id,
        )
        answer = self.policy.renumber_recommendation_answer(answer)
        for candidate in reason_candidates:
            candidate["recommendation_reason_status"] = "COMPLETED"
            if not candidate.get("recommendation_reason_source"):
                candidate["recommendation_reason_source"] = "FALLBACK"
        return {"answer": answer, "candidates": reason_candidates}

    def _make_single_candidate_reason_result(
        self,
        *,
        query: str,
        candidate: Dict[str, Any],
        index: int,
        current_candidates: List[Dict[str, Any]],
        personalization_mode: str,
        request_id: str | None = None,
    ) -> Dict[str, Any]:
        _ = current_candidates
        reason_candidate = copy.deepcopy(candidate or {})
        reason_candidate["recommendation_reason_status"] = "PENDING"
        single_candidate = [reason_candidate]
        self._make_reasoned_recommendation_answer(
            query=query,
            candidates=single_candidate,
            personalization_mode=personalization_mode,
            request_id=f"{request_id or '-'}:{index + 1}",
        )
        next_candidate = single_candidate[0]
        next_candidate["recommendation_reason_status"] = "COMPLETED"
        if not next_candidate.get("recommendation_reason_source"):
            next_candidate["recommendation_reason_source"] = "FALLBACK"
        return {"candidate": next_candidate}

    def _compose_incremental_recommendation_answer(self, candidates: List[Dict[str, Any]]) -> str:
        blocks: List[str] = []
        pending_reason = self.prompt_builder.make_pending_recommendation_reason()
        for idx, book in enumerate(candidates or [], start=1):
            title = str(book.get("title") or "제목 정보 없음").strip()
            author = str(book.get("author") or "저자 정보 없음").strip()
            reason = str(book.get("recommendation_reason") or "").strip() or pending_reason
            blocks.append(
                f"{idx}. {title}\n\n"
                f"저자: {author}\n"
                f"추천 이유: {reason}"
            )
        return "\n\n".join(blocks)

    def _make_reasoned_recommendation_answer(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        personalization_mode: str,
        request_id: str | None = None,
    ) -> str:
        provider = str(settings.RECOMMENDATION_REASON_PROVIDER or "LLM").strip().upper()
        started_at = perf_counter()

        if provider != "LLM":
            answer = self.prompt_builder.make_recommendation_answer_from_reason_schema(
                llm_response="",
                candidates=candidates,
                personalization_mode=personalization_mode,
            )
            print(
                f"[RECOMMENDATION REASON][{request_id or '-'}] "
                f"provider=FALLBACK valid_count=0 total_count={len(candidates)} "
                f"elapsed_ms={int((perf_counter() - started_at) * 1000)}"
            )
            return answer

        llm_response = ""
        try:
            llm_response = self.clova.chat_completion(
                system_prompt=self.prompt_builder.reason_generation_system_prompt(),
                user_prompt=self.prompt_builder.build_recommendation_reason_user_prompt(
                    query=query,
                    candidates=candidates,
                    personalization_mode=personalization_mode,
                ),
            )
        except Exception as exc:
            print(f"[RECOMMENDATION REASON][{request_id or '-'}] provider=LLM error={exc}")

        valid_count = 0
        try:
            valid_count = self.prompt_builder.count_valid_reason_schema(
                llm_response=llm_response,
                candidates=candidates,
            )
        except Exception:
            valid_count = 0

        answer = self.prompt_builder.make_recommendation_answer_from_reason_schema(
            llm_response=llm_response,
            candidates=candidates,
            personalization_mode=personalization_mode,
        )
        print(
            f"[RECOMMENDATION REASON][{request_id or '-'}] "
            f"provider=LLM valid_count={valid_count} total_count={len(candidates)} "
            f"elapsed_ms={int((perf_counter() - started_at) * 1000)}"
        )
        return answer

    def _make_llm_recommendation_answer(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        history: List[Dict[str, Any]] | None = None,
        profile: Dict[str, Any] | None = None,
        guest: bool = False,
        personalization_mode: str = "DISABLED",
    ) -> str:
        user_prompt = self.prompt_builder.build_recommendation_user_prompt(
            query=query,
            candidates=candidates,
            history=history,
            personalization_mode=personalization_mode,
        )

        _ = profile, guest

        try:
            answer = self.clova.chat_completion(
                system_prompt=self.prompt_builder.recommendation_system_prompt(),
                user_prompt=user_prompt,
            )
        except Exception:
            return ""

        if not self.policy.is_valid_recommendation_answer(answer=answer, candidates=candidates):
            return ""

        if self.prompt_builder.is_low_quality_recommendation_answer(
            answer=answer,
            query=query,
            personalization_mode=personalization_mode,
        ):
            return ""

        return answer

    def _resolve_previous_recommendations(
        self,
        query: str,
        query_type: str,
        history: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        if not self.policy.should_exclude_previous_recommendations(
            query=query,
            query_type=query_type,
            history=history,
        ):
            return []
        return self.context.extract_previous_recommended_books(history)

    def _recommendation_empty(
        self,
        query: str,
        guest: bool,
        personalized: bool,
        profile_applied: bool,
        intent: ChatIntent,
        personalization_decision: PersonalizationDecision | None = None,
        query_intent: QueryIntent | None = None,
        embedding_model: str = "CLOVA",
        ranking_model: str = "LIGHTFM",
        recommendation_strategy: str = "AUTO_HYBRID",
        personalization_model: str = "LIGHTFM",
        reranker_provider: str = "NONE",
        bm25_enabled: bool = False,
        retrieval_metadata: Dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> Dict[str, Any]:
        return self._with_mode_metadata(
            response=self._empty_recommendation_response(query),
            guest=guest,
            personalized=personalized,
            profile_applied=profile_applied,
            intent=intent,
            personalization_decision=personalization_decision,
            query_intent=query_intent,
            embedding_model=embedding_model,
            ranking_model=ranking_model,
            recommendation_strategy=recommendation_strategy,
            personalization_model=personalization_model,
            reranker_provider=reranker_provider,
            bm25_enabled=bm25_enabled,
            retrieval_metadata=retrieval_metadata,
            request_id=request_id,
        )

    @staticmethod
    def _profile_with_recommendation_context(profile: Dict[str, Any], intent: ChatIntent) -> Dict[str, Any]:
        enriched_profile = dict(profile or {})
        demographic_profile = enriched_profile.get("demographicProfile") or enriched_profile.get("demographic_profile")
        if isinstance(demographic_profile, dict):
            age_group = (
                demographic_profile.get("userAgeGroup")
                or demographic_profile.get("user_age_group")
                or demographic_profile.get("ageGroup")
                or demographic_profile.get("age_group")
            )
            if age_group:
                enriched_profile.setdefault("userAgeGroup", age_group)
                enriched_profile.setdefault("user_age_group", age_group)
                enriched_profile.setdefault("ageGroup", age_group)
                enriched_profile.setdefault("age_group", age_group)
            age_group_source = demographic_profile.get("ageGroupSource") or demographic_profile.get("age_group_source")
            if age_group_source:
                enriched_profile.setdefault("ageGroupSource", age_group_source)
                enriched_profile.setdefault("age_group_source", age_group_source)
        purpose_profile: Dict[str, Any] = {}
        if intent.recommendation_purpose_summary:
            purpose_profile["summary"] = intent.recommendation_purpose_summary
        if intent.recommendation_requested_purpose:
            purpose_profile["requested_purpose"] = intent.recommendation_requested_purpose
        if intent.recommendation_purpose_positive_terms:
            purpose_profile["positive_terms"] = intent.recommendation_purpose_positive_terms
        if intent.recommendation_purpose_negative_terms:
            purpose_profile["negative_terms"] = intent.recommendation_purpose_negative_terms
        if intent.recommendation_audience_terms:
            purpose_profile["audience_terms"] = intent.recommendation_audience_terms
        if getattr(intent, "recommendation_consumption_context", None):
            purpose_profile["consumption_context"] = intent.recommendation_consumption_context
        if getattr(intent, "recommendation_reading_mode", "UNKNOWN") != "UNKNOWN":
            purpose_profile["reading_mode"] = intent.recommendation_reading_mode
        if getattr(intent, "recommendation_consumption_positive_terms", None):
            purpose_profile["consumption_positive_terms"] = intent.recommendation_consumption_positive_terms
        if getattr(intent, "recommendation_consumption_negative_terms", None):
            purpose_profile["consumption_negative_terms"] = intent.recommendation_consumption_negative_terms
        if intent.recommendation_requested_audience:
            purpose_profile["requested_audience"] = intent.recommendation_requested_audience
        if getattr(intent, "recommendation_requested_audience_group", "UNKNOWN") != "UNKNOWN":
            purpose_profile["requested_audience_group"] = intent.recommendation_requested_audience_group
        if getattr(intent, "recommendation_requested_education_stage", "UNKNOWN") != "UNKNOWN":
            purpose_profile["requested_education_stage"] = intent.recommendation_requested_education_stage
        if getattr(intent, "recommendation_target_reader", "UNKNOWN") != "UNKNOWN":
            purpose_profile["target_reader"] = intent.recommendation_target_reader
        if intent.recommendation_purpose_weight > 0:
            purpose_profile["weight_hint"] = intent.recommendation_purpose_weight
        if purpose_profile:
            enriched_profile["readingPurposeProfile"] = purpose_profile

        review_profile: Dict[str, Any] = {}
        if intent.recommendation_review_signal_available:
            review_profile["signal_available"] = True
        if intent.recommendation_high_rating_positive_terms:
            review_profile["high_rating_positive_terms"] = intent.recommendation_high_rating_positive_terms
        if intent.recommendation_low_rating_negative_terms:
            review_profile["low_rating_negative_terms"] = intent.recommendation_low_rating_negative_terms
        if intent.recommendation_liked_aspects:
            review_profile["liked_aspects"] = intent.recommendation_liked_aspects
        if intent.recommendation_disliked_aspects:
            review_profile["disliked_aspects"] = intent.recommendation_disliked_aspects
        if intent.recommendation_preferred_mood:
            review_profile["preferred_mood"] = intent.recommendation_preferred_mood
        if intent.recommendation_avoid_mood:
            review_profile["avoid_mood"] = intent.recommendation_avoid_mood
        if intent.recommendation_strong_positive_books:
            review_profile["strong_positive_books"] = intent.recommendation_strong_positive_books
        if intent.recommendation_strong_negative_books:
            review_profile["strong_negative_books"] = intent.recommendation_strong_negative_books
        if review_profile:
            enriched_profile["reviewRatingPreferenceProfile"] = review_profile
        return enriched_profile

    @staticmethod
    def _has_requested_audience(query_intent: QueryIntent, intent: ChatIntent) -> bool:
        requested_audience_group = str(
            getattr(query_intent, "requested_audience_group", None)
            or getattr(intent, "recommendation_requested_audience_group", None)
            or ""
        ).strip().upper()
        requested_education_stage = str(
            getattr(query_intent, "requested_education_stage", None)
            or getattr(intent, "recommendation_requested_education_stage", None)
            or ""
        ).strip().upper()
        requested_audience_text = str(
            getattr(intent, "recommendation_requested_audience", None)
            or ""
        ).strip()

        return bool(
            requested_audience_group not in {"", "UNKNOWN", "ANY"}
            or requested_education_stage not in {"", "UNKNOWN"}
            or requested_audience_text
        )

    @staticmethod
    def _audience_request_profile(query_intent: QueryIntent, intent: ChatIntent) -> Dict[str, Any]:
        profile = BookChatService._profile_with_recommendation_context({}, intent)
        purpose_profile = profile.get("readingPurposeProfile")
        if not isinstance(purpose_profile, dict):
            purpose_profile = {}

        requested_audience_group = str(
            getattr(query_intent, "requested_audience_group", None)
            or getattr(intent, "recommendation_requested_audience_group", None)
            or "UNKNOWN"
        ).strip().upper()
        requested_education_stage = str(
            getattr(query_intent, "requested_education_stage", None)
            or getattr(intent, "recommendation_requested_education_stage", None)
            or "UNKNOWN"
        ).strip().upper()
        requested_audience = str(
            getattr(intent, "recommendation_requested_audience", None)
            or ""
        ).strip()
        target_reader = str(
            getattr(intent, "recommendation_target_reader", None)
            or "UNKNOWN"
        ).strip().upper()

        if requested_audience_group and requested_audience_group != "UNKNOWN":
            purpose_profile["requested_audience_group"] = requested_audience_group
        if requested_education_stage and requested_education_stage != "UNKNOWN":
            purpose_profile["requested_education_stage"] = requested_education_stage
        if requested_audience:
            purpose_profile["requested_audience"] = requested_audience
        if target_reader and target_reader != "UNKNOWN":
            purpose_profile["target_reader"] = target_reader

        if purpose_profile:
            profile["readingPurposeProfile"] = purpose_profile

        return profile


    def _resolve_final_recommendation_limit(self, query_intent: QueryIntent | None) -> int:
        configured_limit = max(1, int(self.pipeline_config.final_recommendation_limit))
        requested_count = getattr(query_intent, "requested_recommendation_count", None) if query_intent is not None else None
        try:
            requested_count_int = int(requested_count)
        except (TypeError, ValueError):
            return configured_limit
        if requested_count_int <= 0:
            return configured_limit
        # 수정 포인트: 사용자가 "한 권만/두 개만"처럼 더 적은 추천 수를 요구하면 최종 카드 수를 줄입니다.
        # 운영 기본 상한은 FINAL_RECOMMEND_COUNT로 유지해 과도한 응답을 막습니다.
        return max(1, min(configured_limit, requested_count_int))

    @staticmethod
    def _build_pipeline_config() -> RecommendationPipelineConfig:
        def safe_provider(enum_type, value: str, default):
            try:
                return enum_type(str(value or default.value).strip().upper())
            except ValueError:
                return default

        return RecommendationPipelineConfig(
            qdrant_candidate_limit=max(1, int(getattr(settings, "RECOMMENDATION_CANDIDATE_LIMIT", settings.QDRANT_CANDIDATE_LIMIT))),
            rule_candidate_limit=max(1, int(settings.RULE_CANDIDATE_LIMIT)),
            personalization_candidate_limit=max(1, int(settings.PERSONALIZATION_CANDIDATE_LIMIT)),
            final_recommendation_limit=max(1, int(settings.FINAL_RECOMMEND_COUNT)),
            personalization_provider=safe_provider(
                PersonalizationProvider,
                settings.PERSONALIZATION_PROVIDER,
                PersonalizationProvider.PROFILE_VECTOR,
            ),
            sequence_provider=safe_provider(SequenceProvider, settings.SEQUENCE_PROVIDER, SequenceProvider.NONE),
            reranker_provider=safe_provider(RerankerProvider, settings.RERANKER_PROVIDER, RerankerProvider.NONE),
        )

    def _resolve_retriever(self, embedding_model: str, *, bm25_enabled: bool = False) -> BookQdrantSearcher | BookKureQdrantSearcher:
        if embedding_model == "KURE":
            if bm25_enabled:
                if self.kure_hybrid_retriever is None:
                    self.kure_hybrid_retriever = BookKureQdrantSearcher(
                        collection_name=getattr(settings, "QDRANT_KURE_HYBRID_COLLECTION", "books_kure_hybrid"),
                        hybrid_enabled=True,
                        fallback_collection_name=getattr(settings, "QDRANT_KURE_COLLECTION", "books_kure"),
                    )
                return self.kure_hybrid_retriever
            if self.kure_retriever is None:
                self.kure_retriever = BookKureQdrantSearcher()
            return self.kure_retriever
        if bm25_enabled:
            if self.clova_hybrid_retriever is None:
                self.clova_hybrid_retriever = BookQdrantSearcher(
                    collection_name=getattr(settings, "QDRANT_HYBRID_COLLECTION", "books_hybrid"),
                    hybrid_enabled=True,
                    fallback_collection_name=getattr(settings, "QDRANT_COLLECTION", "books"),
                )
            return self.clova_hybrid_retriever
        return self.clova_retriever

    @staticmethod
    def _normalize_embedding_model(value: str | None) -> str:
        normalized = (value or "CLOVA").strip().upper()
        if normalized not in {"CLOVA", "KURE"}:
            print(f"[MODEL SETTING FALLBACK] unsupported embedding_model={value!r} → CLOVA")
            return "CLOVA"
        return normalized

    @staticmethod
    def _normalize_ranking_model(value: str | None) -> str:
        return BookChatService._normalize_personalization_model(value)

    @staticmethod
    def _normalize_recommendation_strategy(value: str | None) -> str:
        normalized = (value or "AUTO_HYBRID").strip().upper()
        if normalized not in {"AUTO_HYBRID", "RULE_BASED_ONLY"}:
            print(f"[MODEL SETTING FALLBACK] unsupported recommendation_strategy={value!r} → AUTO_HYBRID")
            return "AUTO_HYBRID"
        return normalized

    @staticmethod
    def _normalize_personalization_model(value: str | None) -> str:
        normalized = (value or "LIGHTFM").strip().upper()
        if normalized == "RULE_BASED":
            return "NONE"
        if normalized not in {"NONE", "LIGHTFM", "SASREC", "BERT4REC"}:
            print(f"[MODEL SETTING FALLBACK] unsupported personalization_model={value!r} → LIGHTFM")
            return "LIGHTFM"
        return normalized

    @staticmethod
    def _normalize_reranker_provider(value: str | None) -> str:
        normalized = (value or "NONE").strip().upper()
        if normalized not in {"NONE", "GTE_MULTILINGUAL", "HCX_RERANKER", "CLOVA_RERANKER"}:
            print(f"[MODEL SETTING FALLBACK] unsupported reranker_provider={value!r} → NONE")
            return "NONE"
        if normalized == "CLOVA_RERANKER":
            return "HCX_RERANKER"
        return normalized

    @staticmethod
    def _unsupported_response(query: str) -> Dict[str, Any]:
        return {
            "query": query,
            "answer": "죄송합니다. 저는 도서 추천과 독서 관련 질문에만 답변드릴 수 있습니다.",
            "ori_cover_s": None,
            "cover_url": None,
            "cover": None,
            "candidates": [],
        }

    @staticmethod
    def _empty_recommendation_response(query: str) -> Dict[str, Any]:
        return {
            "query": query,
            "answer": "죄송합니다. 현재 조건에 맞는 도서를 찾지 못했습니다.",
            "ori_cover_s": None,
            "cover_url": None,
            "cover": None,
            "candidates": [],
        }

    def _with_mode_metadata(
        self,
        response: Dict[str, Any],
        guest: bool,
        personalized: bool,
        profile_applied: bool,
        intent: ChatIntent,
        personalization_decision: PersonalizationDecision | None = None,
        query_intent: QueryIntent | None = None,
        embedding_model: str = "CLOVA",
        ranking_model: str = "LIGHTFM",
        recommendation_strategy: str = "AUTO_HYBRID",
        personalization_model: str = "LIGHTFM",
        reranker_provider: str = "NONE",
        bm25_enabled: bool = False,
        retrieval_metadata: Dict[str, Any] | None = None,
        request_id: str | None = None,
        ranking_stage_metadata: Dict[str, Any] | None = None,
        rerank_stage_metadata: Dict[str, Any] | None = None,
        reference_context: ResolvedReferenceContext | None = None,
        final_recommendation_limit: int | None = None,
    ) -> Dict[str, Any]:
        pipeline_metadata = self.pipeline_config.as_metadata()
        if ranking_stage_metadata is not None:
            pipeline_metadata["rankingModelStage"] = ranking_stage_metadata
        if rerank_stage_metadata is not None:
            pipeline_metadata["rerankerStage"] = rerank_stage_metadata
        if retrieval_metadata is not None:
            pipeline_metadata["retrievalStage"] = retrieval_metadata
        if reference_context is not None:
            pipeline_metadata["multiturnContext"] = reference_context.metadata()
        if final_recommendation_limit is not None:
            pipeline_metadata["requestedFinalRecommendationLimit"] = final_recommendation_limit
            response["final_recommendation_limit"] = final_recommendation_limit
        if response.get("recommendation_reason_status"):
            pipeline_metadata["recommendationReasonStatus"] = response.get("recommendation_reason_status")
            pipeline_metadata["recommendationReasonAsync"] = bool(
                response.get("recommendation_reason_status") == "PENDING"
            )

        response.update({
            "request_id": request_id,
            "guest": guest,
            "personalized": personalized,
            "profile_applied": profile_applied,
            "intent": intent.name,
            "intent_source": intent.source,
            "requires_history": intent.requires_history,
            "embedding_model": embedding_model,
            "ranking_model": ranking_model,
            "recommendation_strategy": recommendation_strategy,
            "personalization_model": personalization_model,
            "personalization_provider": personalization_model,
            "sequence_provider": self.pipeline_config.sequence_provider.value,
            "reranker_provider": reranker_provider,
            "bm25_enabled": bool(bm25_enabled),
            "retrieval_strategy": (retrieval_metadata or {}).get("used_strategy"),
            "retrieval_fallback": bool((retrieval_metadata or {}).get("fallback", False)),
            "retrieval_fallback_reason": (retrieval_metadata or {}).get("fallback_reason"),
            "ranking_model_applied": bool((ranking_stage_metadata or {}).get("applied", False)),
            "ranking_model_fallback": bool((ranking_stage_metadata or {}).get("fallback", False)),
            "ranking_model_fallback_reason": (ranking_stage_metadata or {}).get("fallbackReason"),
            "ranking_model_applied_model": (ranking_stage_metadata or {}).get("appliedModel"),
            "ranking_artifact_version": (ranking_stage_metadata or {}).get("artifactVersion"),
            "pipeline": pipeline_metadata,
        })
        response.update(intent.recommendation_metadata())
        if query_intent is not None:
            response.update(query_intent.metadata())
        if personalization_decision is not None:
            response.update(self.personalization_router.build_decision_metadata(personalization_decision))
        else:
            response.update({
                "personalization_mode": PersonalizationMode.DISABLED.value,
                "personalization_query_score": 0.0,
                "personalization_profile_score": 0.0,
                "personalization_reason": "recommendation personalization routing was not used",
                "personalization_source": "not_used",
            })
        return response
