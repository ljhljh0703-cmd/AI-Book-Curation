import json
import math
from pathlib import Path
from typing import List, Dict, Any


class SimpleBookRetriever:
    def __init__(self, data_path: str):
        self.data_path = Path(data_path)
        self.books: List[Dict[str, Any]] = self._load_books()

    def _load_books(self) -> List[Dict[str, Any]]:
        with self.data_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [token.strip().lower() for token in text.split() if token.strip()]

    def _score_book(self, query: str, book: Dict[str, Any]) -> float:
        query_tokens = self._tokenize(query)

        fields = [
            book.get("title", ""),
            book.get("author", ""),
            book.get("description", ""),
            " ".join(book.get("categories", [])),
        ]
        book_text = " ".join(fields).lower()

        score = 0.0
        for token in query_tokens:
            if token in book_text:
                score += 1.0
            if token in book.get("title", "").lower():
                score += 1.5
            if token in " ".join(book.get("categories", [])).lower():
                score += 1.2

        # query가 길수록 너무 불리해지지 않게 정규화
        if query_tokens:
            score = score / math.sqrt(len(query_tokens))

        return score

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        scored = []
        for book in self.books:
            score = self._score_book(query, book)
            scored.append({**book, "score": round(score, 4)})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]