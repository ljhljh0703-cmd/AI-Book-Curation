##AI Book Curation##

도서 서지 데이터 기반 사용자 맞춤형 도서 큐레이션 서비스입니다.
본 프로젝트는 약 10만 건의 도서 서지 데이터를 기반으로 사용자의 자연어 질의, 대화 이력, 선호 장르, 행동 로그, 위치 정보를 종합하여 개인화 도서 추천을 제공하는 것을 목표로 합니다.
핵심 기능

자체 회원가입/로그인
Google / Kakao  소셜 로그인
회원별 추가 프로필 입력
자연어 질의 기반 도서 추천
대화 히스토리 기반 사용자 프로파일링
좋아요, 읽은 책, 북마크, 관심없음 등 행동 로그 기반 개인화
도서관정보나루 API 연동
사용자 위치 기반 근처 도서관 조회
libCode + isbn13 기반 소장/대출 가능 여부 확인
Retrieval 평가: Hit Rate@K, NDCG@K
Generation 평가: LLM Judge, 테스트 회원/페르소나 기반 평가

기술 스택



영역
기술




Frontend
React, Vite


Backend
Java 21, Spring Boot, Spring Security, JPA


AI Server
Python, FastAPI


Database
PostgreSQL, PostGIS


Vector DB
ChromaDB 또는 Qdrant


LLM
HCX 계열 API


Infra
Docker, NAS, Cloudflare



모노레포 구조
book-curation/
├─ apps/
│  ├─ backend/              # Spring Boot Java 21 API 서버
│  ├─ frontend/             # React/Vite 프론트엔드
│  └─ ai-server/            # FastAPI 기반 RAG/LLM 서버
│
├─ packages/
│  ├─ prompts/              # LLM 프롬프트 템플릿
│  └─ shared-contracts/     # API 계약, JSON Schema, 예시 응답
│
├─ database/
│  ├─ ddl/                  # 초기 DDL
│  ├─ migrations/           # Flyway/Liquibase 사용 시 마이그레이션
│  └─ seed/                 # 테스트 회원, 샘플 데이터
│
├─ infra/
│  ├─ docker/               # Docker Compose, nginx, DB 참고 설정
│  └─ scripts/              # 배포, 백업, 데이터 적재 스크립트
│
├─ docs/
│  ├─ architecture.md
│  ├─ api-spec.md
│  ├─ database.md
│  ├─ rag-pipeline.md
│  ├─ evaluation.md
│  └─ meeting-notes/
│
├─ data/
│  └─ samples/              # 공개 가능한 샘플 데이터만 저장
│
├─ .gitignore
├─ .env.example
└─ README.md
브랜치 전략
기본 브랜치



브랜치
역할




main
발표/배포 가능한 안정 버전


dev
팀원 작업이 모이는 통합 개발 브랜치


feature/*
기능 개발 브랜치


fix/*
버그 수정 브랜치


docs/*
문서 작업 브랜치


infra/*
인프라/배포 작업 브랜치



작업 흐름
feature/* → Pull Request → dev → 통합 테스트 → main
예시 브랜치명
feature/backend-auth
feature/backend-library-sync
feature/backend-user-profile
feature/frontend-auth
feature/frontend-chat-ui
feature/frontend-recommendation-card
feature/ai-rag-pipeline
feature/ai-embedding
feature/infra-docker
feature/evaluation-metrics
docs/api-spec
팀원 역할 예시
Backend 담당

Spring Boot API 서버
자체 로그인/회원가입
소셜 로그인
사용자 프로필
도서관정보나루 API 연동
PostgreSQL/PostGIS 연동

Frontend 담당

React 로그인/회원가입 화면
추가 프로필 입력 화면
챗봇 UI
추천 결과 카드
좋아요/읽은 책/즐겨찾는 도서관 UI

AI/RAG 담당

도서 데이터 정제
임베딩 생성
VectorDB 구축
질의 분석
추천 후보 검색/리랭킹
HCX LLM 응답 생성

Infra/Evaluation 담당

Docker Compose
DB DDL/마이그레이션 관리
도서관 데이터 적재 스크립트
Hit Rate@K, NDCG@K
LLM Judge
발표자료/문서 정리

Git 작업 규칙

main, dev 브랜치에는 직접 push하지 않는다.
모든 작업은 feature/*, fix/*, docs/*, infra/* 브랜치에서 진행한다.
Pull Request 대상은 기본적으로 dev로 한다.
API Key, DB Password, 원본 데이터셋은 절대 Git에 커밋하지 않는다.
환경변수는 .env.example에 변수명만 공유한다.
DB 변경사항은 database/ddl 또는 database/migrations에 SQL로 남긴다.
회의/결정사항은 docs/meeting-notes에 기록한다.
기능 PR에는 테스트 방법 또는 확인 SQL을 함께 작성한다.

보안 규칙
Git에 올리면 안 되는 것:

.env
application-local.yml
application-secret.yml
DB 비밀번호
도서관정보나루 API Key
HCX/NCP API Key
Google/Kakao Client Secret
원본 도서 데이터셋
대량 데이터 파일
개인 사용자 데이터

공유 가능한 것:

.env.example
샘플 데이터
DDL
API 명세
프롬프트 템플릿
공개 가능한 결과물

로컬 개발 순서
git clone <repository-url>
cd book-curation
git checkout dev
cd apps/backend
./gradlew bootRun
Windows:
cd apps/backend
gradlew.bat bootRun
환경변수 예시
.env.example을 참고해 각자 로컬 환경에 맞게 설정합니다.
Spring Boot는 기본적으로 .env를 자동으로 읽지 않으므로 IntelliJ Run Configuration 또는 OS 환경변수에 등록하는 방식을 권장합니다.
현재 DB 기준

DB: book_curation
Schema: book
PostgreSQL + PostGIS 사용
도서관 위치 계산은 GEOGRAPHY(POINT, 4326) 사용
좌표 순서: ST_MakePoint(longitude, latitude)
