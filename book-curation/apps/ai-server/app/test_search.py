from app.services.retrieval.qdrant_search import BookQdrantSearcher

searcher = BookQdrantSearcher()

result = searcher.search("자기계발 추천해줘", limit=5)

for book in result:
    print("제목:", book["title"])
    print("저자:", book["author"])
    print("점수:", book["score"])
    print("설명:", book["description"])
    print("-" * 50)