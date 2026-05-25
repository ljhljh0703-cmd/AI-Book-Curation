from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PayloadSchemaType, PointStruct, VectorParams

from app.core.config import settings
from app.services.clients.kure_client import KureClient


class BookKureQdrantIndexer:
    """
    KURE-v1 임베딩으로 Qdrant 컬렉션을 생성/인덱싱하는 클래스입니다.

    기존 CLOVA 기반 books 컬렉션은 건드리지 않고,
    기본적으로 books_kure 컬렉션에 별도 인덱싱합니다.

    CLOVA BookQdrantIndexer 구조를 참고해 다음을 반영합니다.
    - collection 존재 확인 후 없을 때만 생성
    - payload index 생성
    - 첫 벡터 샘플 탐색으로 vector dimension 확인
    - embedding 실패 시 해당 도서만 skip
    - batch 단위 upsert
    - 동일 ISBN 기반 deterministic UUID 생성
    """

    DEFAULT_COLLECTION_NAME = "books_kure"
    DEFAULT_VECTOR_SIZE = 1024
    DEFAULT_MAX_INTRO_LENGTH = 1200
    DEFAULT_BATCH_SIZE = 64
    DEFAULT_EMBED_WORKERS = 1
    EMBEDDING_MODEL_NAME = "nlpai-lab/KURE-v1"

    def __init__(self) -> None:
        self.qdrant_url = getattr(settings, "QDRANT_URL", "http://qdrant:6333")
        self.qdrant_api_key = getattr(settings, "QDRANT_API_KEY", "")
        self.collection_name = getattr(
            settings,
            "KURE_QDRANT_COLLECTION",
            self.DEFAULT_COLLECTION_NAME,
        )
        self.max_intro_length = int(
            getattr(settings, "MAX_INTRO_LENGTH", self.DEFAULT_MAX_INTRO_LENGTH)
        )
        self.embed_workers = int(
            getattr(settings, "EMBED_WORKERS", self.DEFAULT_EMBED_WORKERS)
        )

        if self.qdrant_api_key:
            self.client = QdrantClient(
                url=self.qdrant_url,
                api_key=self.qdrant_api_key,
            )
        else:
            self.client = QdrantClient(url=self.qdrant_url)

        self.embedder = KureClient()

    @staticmethod
    def _join_list(value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value if item is not None)
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _load_books(json_path: str) -> List[Dict[str, Any]]:
        path = Path(json_path).resolve()

        if not path.exists():
            raise FileNotFoundError(f"JSON file not found: {json_path}")

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for key in ["books", "items", "data"]:
                value = data.get(key)
                if isinstance(value, list):
                    return value

        raise ValueError("지원하지 않는 JSON 구조입니다. list 또는 books/items/data 배열이 필요합니다.")

    @staticmethod
    def _chunk(items: List[Dict[str, Any]], size: int):
        size = max(1, int(size))
        for index in range(0, len(items), size):
            yield items[index:index + size]

    @staticmethod
    def _get_best_intro(book: Dict[str, Any]) -> str:
        """
        검색 품질을 위해 가장 설명력이 좋은 소개 문구를 선택합니다.

        우선순위:
        1. book_intro
        2. simple_intro
        3. description
        4. pub_review
        5. book_index
        """
        for key in ["book_intro", "simple_intro", "description", "pub_review", "book_index"]:
            value = book.get(key)
            if value:
                text = str(value).strip()
                if text:
                    return text
        return ""

    def make_document_text(self, book: Dict[str, Any]) -> str:
        """
        KURE 임베딩에 넣을 도서 문서를 생성합니다.

        CLOVA 인덱서와 유사한 필드 구성을 유지하되,
        KURE 검색 품질을 위해 목차/출판사 리뷰/저자 소개도 포함합니다.
        """
        title = (book.get("title") or "").strip()
        author = (book.get("author") or "").strip()
        publisher = (book.get("publisher") or "").strip()
        publish_date = (book.get("publish_date") or "").strip()
        page = book.get("page")
        price = book.get("price")

        categories = book.get("categories") or book.get("cate_depth1") or []
        cate_depth1 = book.get("cate_depth1") or []
        kcid = book.get("kcid") or []

        category_text = self._join_list(categories)
        cate_depth1_text = self._join_list(cate_depth1)
        kcid_text = self._join_list(kcid)

        intro = self._get_best_intro(book)[: self.max_intro_length]
        book_index = str(book.get("book_index") or "").strip()[: self.max_intro_length]
        pub_review = str(book.get("pub_review") or "").strip()[: self.max_intro_length]
        author_intro = str(book.get("author_intro") or "").strip()[: self.max_intro_length]

        lines = [
            f"제목: {title}",
            f"저자: {author}",
            f"출판사: {publisher}",
            f"출간일: {publish_date}",
            f"카테고리: {category_text or cate_depth1_text}",
            f"KCID: {kcid_text}",
        ]

        if page is not None:
            lines.append(f"페이지수: {page}")

        if price is not None:
            lines.append(f"가격: {price}")

        if intro:
            lines.append(f"소개: {intro}")

        if book_index:
            lines.append(f"목차: {book_index}")

        if pub_review:
            lines.append(f"출판사 리뷰: {pub_review}")

        if author_intro:
            lines.append(f"저자 소개: {author_intro}")

        return "\n".join(line for line in lines if line and not line.endswith(": ")).strip()

    def ensure_collection(self, vector_size: int) -> None:
        """
        컬렉션이 없으면 생성하고, 있으면 그대로 사용합니다.
        """
        exists = self.client.collection_exists(self.collection_name)

        if exists:
            print(f"[KURE INDEX INFO] Collection already exists: {self.collection_name}")
            self.ensure_payload_indexes()
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )

        print(
            "[KURE INDEX INFO] Collection created: "
            f"{self.collection_name} (dim={vector_size})"
        )
        self.ensure_payload_indexes()

    def recreate_collection(self, vector_size: int = DEFAULT_VECTOR_SIZE) -> None:
        """
        컬렉션을 강제로 재생성합니다.

        기존 books 컬렉션이 아니라 self.collection_name만 대상으로 합니다.
        """
        print(f"[KURE INDEX INFO] Recreate collection: {self.collection_name}")

        self.client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )

        print(
            "[KURE INDEX INFO] Collection recreated: "
            f"{self.collection_name} (dim={vector_size})"
        )
        self.ensure_payload_indexes()

    def ensure_payload_indexes(self) -> None:
        """
        ISBN exact match, 제목/저자 text match, 장르 필터 검색을 위해 payload index를 생성합니다.

        이미 존재하는 index이거나 Qdrant 버전/권한 문제로 실패해도
        색인 전체가 중단되지 않도록 경고만 출력하고 계속 진행합니다.
        """
        payload_indexes = [
            ("isbn", PayloadSchemaType.KEYWORD),
            ("title", PayloadSchemaType.TEXT),
            ("author", PayloadSchemaType.TEXT),
            ("publisher", PayloadSchemaType.TEXT),
            ("categories", PayloadSchemaType.KEYWORD),
            ("cate_depth1", PayloadSchemaType.KEYWORD),
            ("kcid", PayloadSchemaType.KEYWORD),
            ("embedding_model", PayloadSchemaType.KEYWORD),
        ]

        for field_name, schema in payload_indexes:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=schema,
                    wait=False,
                )
                print(f"[KURE INDEX INFO] Payload index ensured: {field_name} ({schema})")
            except Exception as exc:
                print(
                    "[KURE INDEX WARN] Payload index skipped: "
                    f"field={field_name}, reason={exc}"
                )

    @staticmethod
    def make_point_id(book: Dict[str, Any], index: int | None = None) -> str:
        """
        Qdrant point id를 UUID 문자열로 생성합니다.

        ISBN이 있으면 ISBN 기반으로 고정 UUID를 만들고,
        ISBN이 없으면 index 기반 UUID를 만듭니다.
        """
        isbn = str(book.get("isbn") or "").strip()

        if isbn:
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"kure-book:{isbn}"))

        if index is not None:
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"kure-book-index:{index}"))

        return str(uuid.uuid4())

    def make_payload(self, book: Dict[str, Any], doc_text: str) -> Dict[str, Any]:
        ori_cover_s = book.get("ori_cover_s")
        cover_url = book.get("cover_url") or ori_cover_s or book.get("cover")

        categories = book.get("categories") or book.get("cate_depth1") or []
        cate_depth1 = book.get("cate_depth1") or []
        kcid = book.get("kcid") or []

        return {
            "isbn": book.get("isbn"),
            "title": book.get("title"),
            "author": book.get("author"),
            "publisher": book.get("publisher"),
            "publish_date": book.get("publish_date"),
            "page": book.get("page"),
            "price": book.get("price"),
            "format": book.get("format"),
            "book_format": book.get("book_format") or book.get("bookFormat"),
            "media_type": book.get("media_type") or book.get("mediaType"),
            "content_format": book.get("content_format") or book.get("contentFormat"),
            "is_audio_book": book.get("is_audio_book") or book.get("isAudioBook") or book.get("audiobook"),
            "is_ebook": book.get("is_ebook") or book.get("isEbook") or book.get("ebook"),

            "simple_intro": book.get("simple_intro"),
            "book_intro": book.get("book_intro"),
            "description": book.get("description") or self._get_best_intro(book),

            "categories": categories,
            "cate_depth1": cate_depth1,
            "kcid": kcid,

            "ori_cover_s": ori_cover_s,
            "cover_url": cover_url,
            "cover": cover_url,
            "cover_source": "json_ori_cover_s" if ori_cover_s else None,

            "author_intro": book.get("author_intro"),
            "book_index": book.get("book_index"),
            "pub_review": book.get("pub_review"),

            "document": doc_text,
            "embedding_model": self.EMBEDDING_MODEL_NAME,
        }

    def _find_first_vector(self, books: List[Dict[str, Any]]) -> Optional[list[float]]:
        """
        첫 번째 책 임베딩이 실패해도 즉시 중단하지 않고,
        앞쪽 샘플에서 성공 벡터를 찾아 vector dimension을 결정합니다.
        """
        for index, book in enumerate(books[:20], start=1):
            doc_text = self.make_document_text(book)
            vector = self.embedder.embedding(doc_text)

            if vector is not None:
                print(f"[KURE INDEX INFO] First vector resolved from sample index={index}")
                return vector

        return None

    def index_books(
        self,
        json_path: str,
        batch_size: int = DEFAULT_BATCH_SIZE,
        recreate: bool = False,
    ) -> None:
        books = self._load_books(json_path)
        total_books = len(books)

        print(f"[KURE INDEX INFO] Loaded {total_books} books")

        if not books:
            print("[KURE INDEX WARN] No books found")
            return

        first_vector = self._find_first_vector(books)

        if first_vector is None:
            print("[KURE INDEX ERROR] Could not create an embedding vector. Check KURE model/runtime and retry.")
            return

        vector_size = len(first_vector)

        if recreate:
            self.recreate_collection(vector_size=vector_size)
        else:
            self.ensure_collection(vector_size=vector_size)

        total_indexed = 0
        total_skipped = 0

        batch_size = max(1, int(batch_size))

        for batch_index, batch_books in enumerate(self._chunk(books, batch_size), start=1):
            texts = [self.make_document_text(book) for book in batch_books]
            vectors = self.embedder.embedding_many(
                texts,
                max_workers=self.embed_workers,
            )

            points: List[PointStruct] = []

            for offset, (book, doc_text, vector) in enumerate(zip(batch_books, texts, vectors)):
                global_index = ((batch_index - 1) * batch_size) + offset

                if vector is None:
                    total_skipped += 1
                    print(
                        "[KURE INDEX WARN] Skip book because embedding failed. "
                        f"index={global_index}, isbn={book.get('isbn')}, title={book.get('title')}"
                    )
                    continue

                if len(vector) != vector_size:
                    total_skipped += 1
                    print(
                        "[KURE INDEX WARN] Skip book because vector dimension mismatch. "
                        f"index={global_index}, expected={vector_size}, actual={len(vector)}, "
                        f"isbn={book.get('isbn')}, title={book.get('title')}"
                    )
                    continue

                point_id = self.make_point_id(book=book, index=global_index)
                payload = self.make_payload(book=book, doc_text=doc_text)

                points.append(
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=payload,
                    )
                )

            if not points:
                print(f"[KURE INDEX WARN] Skip empty batch {batch_index}. All embeddings failed.")
                continue

            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=False,
            )

            total_indexed += len(points)

            print(
                "[KURE INDEX INFO] Upserted batch "
                f"{batch_index} / size={len(points)} / "
                f"indexed_total={total_indexed} / skipped_total={total_skipped}"
            )

        print(
            "[KURE INDEX DONE] "
            f"collection={self.collection_name}, "
            f"indexed_total={total_indexed}, "
            f"skipped_total={total_skipped}"
        )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 -m app.services.indexing.qdrant_kure_indexer <json_path> [--recreate]")
        sys.exit(1)

    json_path_arg = sys.argv[1]
    recreate_arg = "--recreate" in sys.argv

    indexer = BookKureQdrantIndexer()
    indexer.index_books(
        json_path=json_path_arg,
        recreate=recreate_arg,
    )