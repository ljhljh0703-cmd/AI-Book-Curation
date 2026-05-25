import os
from dotenv import load_dotenv

from app.services.indexing.qdrant_indexer import BookQdrantIndexer

load_dotenv()


def main():
    json_path = os.getenv(
        "BOOKS_JSON_PATH",
        "/volume1/apps/book-data/books_sample_100000.json",
    )
    batch_size = int(os.getenv("INDEX_BATCH_SIZE", "16"))

    indexer = BookQdrantIndexer()
    indexer.index_books(
        json_path=json_path,
        batch_size=batch_size,
    )


if __name__ == "__main__":
    main()
