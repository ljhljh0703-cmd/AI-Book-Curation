# ai-server service layout

The service layer is organized by responsibility. Root-level service implementation files were removed; import from the responsibility package directly.

- `chat/`: chat orchestration application service
- `clients/`: external LLM and embedding clients
- `common/`: shared utilities, config loading, rate limiting
- `context/`: conversation/profile context builders
- `intent/`: intent parsing and personalization routing
- `recommendation/`: recommendation policy, filtering, reranking, guardrails, reasons
- `retrieval/`: Qdrant retrieval adapters
- `indexing/`: Qdrant indexing and payload maintenance tools
- `profiling/`: review/profile analysis and vectorization
