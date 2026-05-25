from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    # 수정 포인트: backend/frontend는 camelCase JSON을 사용하므로 admin 평가 API도 같은 표기법으로 주고받습니다.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)



class QueryEvaluationRunRequest(CamelModel):
    cases_path: Optional[str] = None
    # 관리자 화면에서 직접 입력한 평가 질의입니다. 비어 있으면 기본 JSONL 파일을 사용합니다.
    cases_jsonl: Optional[str] = None
    # 외부 입력 경로는 사용하지 않고 service에서 QUERY_EVAL_OUTPUT_DIR 고정 경로로 처리합니다.
    out_dir: Optional[str] = None
    embedding_model: str = "KURE"
    top_k: int = Field(default=10, ge=1, le=50)
    max_corpus_docs: int = Field(default=50_000, ge=1, le=500_000)
    query_variants: List[str] = Field(
        default_factory=lambda: [
            "original",
            "llm_search_query",
            "retrieval_query",
            "retrieval_plus_genre",
            "retrieval_plus_purpose",
            "retrieval_plus_context",
            "retrieval_plus_profile",
        ]
    )
    retrieval_variants: List[str] = Field(
        default_factory=lambda: [
            "dense",
            "dense_bm25_rrf",
            "lookup_dense_bm25_rrf",
        ]
    )
    rule_variants: List[str] = Field(default_factory=lambda: ["current"])


class QueryEvaluationCommandResponse(CamelModel):
    status: str
    exit_code: int
    out_dir: str
    label_csv_path: str
    auto_summary_path: str
    labeled_summary_path: str
    raw_results_path: str
    stdout_tail: str = ""
    stderr_tail: str = ""
    message: Optional[str] = None
    # 수정 포인트: backend/local runner 비동기 평가 응답과 같은 DTO를 공유할 수 있게 선택 필드를 둡니다.
    job_id: Optional[str] = None
    log_path: Optional[str] = None


class QueryEvaluationRowsResponse(CamelModel):
    out_dir: str
    file_name: str
    columns: List[str]
    rows: List[Dict[str, Any]]
    total_rows: int
    offset: int
    limit: int


class QueryEvaluationJobListResponse(CamelModel):
    jobs: List[QueryEvaluationCommandResponse]


class QueryEvaluationLabelUpdate(CamelModel):
    row_key: str
    human_relevance_0_2: Optional[str] = Field(default=None, alias="humanRelevance02")
    human_memo: Optional[str] = None


class QueryEvaluationLabelSaveRequest(CamelModel):
    # job별 결과 폴더를 선택 저장할 수 있도록 outDir을 허용하되 service에서 jobs/<jobId>만 안전하게 해석합니다.
    out_dir: Optional[str] = None
    rows: List[QueryEvaluationLabelUpdate] = Field(default_factory=list)
    top_k: int = Field(default=10, ge=1, le=50)


class QueryEvaluationSummaryRequest(CamelModel):
    # job별 결과 폴더를 선택 요약할 수 있도록 outDir을 허용하되 service에서 jobs/<jobId>만 안전하게 해석합니다.
    out_dir: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=50)
