import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from qdrant_client import QdrantClient

load_dotenv()


class QdrantCoverPayloadUpdater:
    def __init__(self) -> None:
        self.qdrant_url = os.getenv("QDRANT_URL", "http://localhost:16333")
        self.qdrant_api_key = os.getenv("QDRANT_API_KEY", "")
        self.collection_name = os.getenv("QDRANT_COLLECTION", "books")

        if self.qdrant_api_key:
            self.client = QdrantClient(
                url=self.qdrant_url,
                api_key=self.qdrant_api_key,
                timeout=60,
            )
        else:
            self.client = QdrantClient(
                url=self.qdrant_url,
                timeout=60,
            )

    @staticmethod
    def load_books(json_path: str) -> List[Dict[str, Any]]:
        path = Path(json_path).resolve()

        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def build_isbn_point_map(self) -> Dict[str, Any]:
        """
        Qdrant에 이미 들어있는 point들을 한 번씩만 scroll해서
        isbn -> point_id 맵을 만든다.
        """
        isbn_to_point_id: Dict[str, Any] = {}

        offset: Optional[Any] = None
        total_scanned = 0

        print("[INFO] Building ISBN -> point_id map from Qdrant...")

        while True:
            points, next_offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=1000,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )

            if not points:
                break

            for point in points:
                payload = point.payload or {}
                isbn = str(payload.get("isbn") or "").strip()

                if isbn:
                    isbn_to_point_id[isbn] = point.id

            total_scanned += len(points)

            if total_scanned % 10000 == 0:
                print(
                    f"[INFO] scanned={total_scanned}, "
                    f"isbn_map_size={len(isbn_to_point_id)}"
                )

            if next_offset is None:
                break

            offset = next_offset

        print(
            f"[INFO] ISBN map completed. "
            f"scanned={total_scanned}, isbn_map_size={len(isbn_to_point_id)}"
        )

        return isbn_to_point_id

    def update_cover_payload(self, json_path: str) -> None:
        books = self.load_books(json_path)

        print(f"[INFO] Loaded {len(books)} books")
        print(f"[INFO] Qdrant URL: {self.qdrant_url}")
        print(f"[INFO] Collection: {self.collection_name}")

        isbn_to_point_id = self.build_isbn_point_map()

        updated = 0
        skipped_no_isbn = 0
        skipped_no_cover = 0
        not_found = 0

        for idx, book in enumerate(books, start=1):
            isbn = str(book.get("isbn") or "").strip()
            ori_cover_s = str(book.get("ori_cover_s") or "").strip()

            if not isbn:
                skipped_no_isbn += 1
                continue

            if not ori_cover_s:
                skipped_no_cover += 1
                continue

            point_id = isbn_to_point_id.get(isbn)

            if point_id is None:
                not_found += 1
                continue

            self.client.set_payload(
                collection_name=self.collection_name,
                payload={
                    "ori_cover_s": ori_cover_s,
                    "cover_url": ori_cover_s,
                    "cover_source": "json_ori_cover_s",
                },
                points=[point_id],
                wait=False,
            )

            updated += 1

            if idx % 1000 == 0:
                print(
                    f"[INFO] processed={idx}, updated={updated}, "
                    f"not_found={not_found}, "
                    f"skipped_no_isbn={skipped_no_isbn}, "
                    f"skipped_no_cover={skipped_no_cover}"
                )

        print("[DONE] Payload update completed")
        print(f"[DONE] updated={updated}")
        print(f"[DONE] not_found={not_found}")
        print(f"[DONE] skipped_no_isbn={skipped_no_isbn}")
        print(f"[DONE] skipped_no_cover={skipped_no_cover}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python3 -m app.services.indexing.update_qdrant_cover_payload <json_path>"
        )
        sys.exit(1)

    json_path = sys.argv[1]

    updater = QdrantCoverPayloadUpdater()
    updater.update_cover_payload(json_path)