import json
import os
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PayloadSchemaType, PointStruct, VectorParams

from app.services.clients.clova_client import ClovaClient

load_dotenv()


class BookQdrantIndexer:
    def __init__(self) -> None:
        self.qdrant_url = os.getenv("QDRANT_URL", "http://qdrant:6333")
        self.qdrant_api_key = os.getenv("QDRANT_API_KEY", "")
        self.collection_name = os.getenv("QDRANT_COLLECTION", "books")
        self.max_intro_length = int(os.getenv("MAX_INTRO_LENGTH", "1200"))
        # 수정 포인트: 인덱싱 중 CLOVA embedding 429가 많이 발생하지 않도록 기본 병렬도를 1로 낮춥니다.
        self.embed_workers = int(os.getenv("EMBED_WORKERS", "1"))

        if self.qdrant_api_key:
            self.client = QdrantClient(
                url=self.qdrant_url,
                api_key=self.qdrant_api_key,
            )
        else:
            self.client = QdrantClient(url=self.qdrant_url)

        self.embedder = ClovaClient()

    @staticmethod
    def _join_list(value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(str(x) for x in value if x is not None)
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _get_best_intro(book: Dict[str, Any]) -> str:
        book_intro = (book.get("book_intro") or "").strip()
        simple_intro = (book.get("simple_intro") or "").strip()

        if book_intro:
            return book_intro
        if simple_intro:
            return simple_intro
        return ""

    def make_document_text(self, book: Dict[str, Any]) -> str:
        title = (book.get("title") or "").strip()
        author = (book.get("author") or "").strip()
        publisher = (book.get("publisher") or "").strip()
        publish_date = (book.get("publish_date") or "").strip()
        page = book.get("page")
        price = book.get("price")
        cate_depth1 = self._join_list(book.get("cate_depth1", []))
        kcid = self._join_list(book.get("kcid", []))
        intro = self._get_best_intro(book)[: self.max_intro_length]

        lines = [
            f"제목: {title}",
            f"저자: {author}",
            f"출판사: {publisher}",
            f"출간일: {publish_date}",
            f"카테고리: {cate_depth1}",
            f"KCID: {kcid}",
        ]

        if page is not None:
            lines.append(f"페이지수: {page}")
        if price is not None:
            lines.append(f"가격: {price}")
        if intro:
            lines.append(f"소개: {intro}")

        return "\n".join(lines).strip()

    def ensure_collection(self, vector_size: int) -> None:
        exists = self.client.collection_exists(self.collection_name)
        if exists:
            print(f"[INFO] Collection already exists: {self.collection_name}")
            self.ensure_payload_indexes()
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
        print(f"[INFO] Collection created: {self.collection_name} (dim={vector_size})")
        self.ensure_payload_indexes()

    def ensure_payload_indexes(self) -> None:
        # 수정 포인트: ISBN exact match, 제목/저자 text match, 장르 필터 검색을 위해 payload index를 생성합니다.
        # 이미 존재하는 index이거나 Qdrant 버전/권한 문제로 실패해도 색인 전체가 중단되지 않도록 경고 후 계속 진행합니다.
        payload_indexes = [
            ("isbn", PayloadSchemaType.KEYWORD),
            ("title", PayloadSchemaType.TEXT),
            ("author", PayloadSchemaType.TEXT),
            ("categories", PayloadSchemaType.KEYWORD),
            ("cate_depth1", PayloadSchemaType.KEYWORD),
            ("kcid", PayloadSchemaType.KEYWORD),
        ]

        for field_name, schema in payload_indexes:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=schema,
                    wait=False,
                )
                print(f"[INFO] Payload index ensured: {field_name} ({schema})")
            except Exception as exc:
                print(f"[WARN] Payload index skipped: field={field_name}, reason={exc}")

    @staticmethod
    def make_point_id(book: Dict[str, Any]) -> str:
        isbn = str(book.get("isbn", "")).strip()
        if isbn:
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"book:{isbn}"))
        return str(uuid.uuid4())

    def make_payload(self, book: Dict[str, Any], doc_text: str) -> Dict[str, Any]:
        cover = book.get("ori_cover_s") or None
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
            "description": self._get_best_intro(book),
            "cate_depth1": book.get("cate_depth1", []),
            "categories": book.get("cate_depth1", []),
            "kcid": book.get("kcid", []),
            "ori_cover_s": book.get("ori_cover_s"),
            "cover_url": cover,
            "cover_source": "json_ori_cover_s" if book.get("ori_cover_s") else None,
            "document": doc_text,
        }

    @staticmethod
    def load_books(json_path: str) -> List[Dict[str, Any]]:
        path = Path(json_path).resolve()
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _chunk(items: List[Dict[str, Any]], size: int):
        for i in range(0, len(items), size):
            yield items[i:i + size]

    def _find_first_vector(self, books: List[Dict[str, Any]]) -> Optional[list[float]]:
        # 수정 포인트: 첫 번째 책 임베딩이 429 등으로 실패하면 즉시 죽지 않고 뒤쪽 샘플에서 벡터 차원을 찾습니다.
        for idx, book in enumerate(books[:20], start=1):
            vector = self.embedder.embedding(self.make_document_text(book))
            if vector is not None:
                print(f"[INFO] First vector resolved from sample index={idx}")
                return vector
        return None

    def index_books(self, json_path: str, batch_size: int = 128) -> None:
        books = self.load_books(json_path)
        print(f"[INFO] Loaded {len(books)} books")

        if not books:
            print("[WARN] No books found")
            return

        first_vector = self._find_first_vector(books)
        if first_vector is None:
            print("[ERROR] Could not create an embedding vector. Check CLOVA quota/rate-limit and retry later.")
            return

        vector_size = len(first_vector)
        self.ensure_collection(vector_size)

        total_skipped = 0
        for batch_idx, batch_books in enumerate(self._chunk(books, batch_size), start=1):
            texts = [self.make_document_text(book) for book in batch_books]
            vectors = self.embedder.embedding_many(texts, max_workers=self.embed_workers)

            points: List[PointStruct] = []

            for book, doc_text, vector in zip(batch_books, texts, vectors):
                if vector is None:
                    total_skipped += 1
                    print(f"[WARN] Skip book because embedding failed. isbn={book.get('isbn')}, title={book.get('title')}")
                    continue

                point_id = self.make_point_id(book)
                payload = self.make_payload(book, doc_text)

                points.append(
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=payload,
                    )
                )

            if not points:
                print(f"[WARN] Skip empty batch {batch_idx}. All embeddings failed.")
                continue

            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=False,
            )
            print(f"[INFO] Upserted batch {batch_idx} / size={len(points)} / skipped_total={total_skipped}")

        print(f"[INFO] Indexing completed. skipped_total={total_skipped}")
        
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 -m app.services.indexing.qdrant_indexer <json_path>")
        sys.exit(1)

    json_path = sys.argv[1]

    indexer = BookQdrantIndexer()
    indexer.index_books(json_path)
