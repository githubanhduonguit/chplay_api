# 📋 Implementation Plan — CH Play API Backend

> **Tech Stack:** Python 3.12+ · FastAPI · LangGraph · LiteLLM · Gemini · Qdrant · PostgreSQL · Spark  
> **Architecture:** Clean Architecture · SOLID · DDD-lite · Async-first · Type Hint

---

## 🗂 Bước 1: Khởi tạo Project

**Mục tiêu:** Thiết lập project skeleton với uv, cài đặt dependencies, tạo cấu trúc thư mục.

- [x] `uv init` — khởi tạo pyproject.toml
- [x] Tạo cây thư mục theo kiến trúc đã định
- [x] Cài đặt dependencies:
  - `fastapi`, `uvicorn[standard]`, `pydantic>=2`
  - `sqlalchemy>=2.0`, `asyncpg`, `alembic`
  - `qdrant-client`
  - `litellm`
  - `langgraph`, `langchain-core`
  - `pyspark`
  - `httpx`, `tenacity` (retry), `python-multipart`
  - `python-dotenv`, `pydantic-settings`
- [x] Tạo `.env.example` với tất cả biến môi trường
- [x] Tạo `.gitignore`
- [x] Kiểm tra `uv sync` / `uv lock` thành công

---

## ⚙️ Bước 2: Config

**Mục tiêu:** Hệ thống config tập trung, đọc từ ENV, type-safe với Pydantic Settings.

- [x] `app/core/config.py` — class `Settings(BaseSettings)`:
  - `DATABASE_URL`, `QDRANT_URL`, `GEMINI_API_KEY`
  - `LITELLM_KEY`, `PHOBERT_API_URL`
  - `SPARK_MASTER`, `SPARK_APP_NAME`
  - `EMBEDDING_MODEL` (bge-m3)
  - `HYBRID_SEARCH_WEIGHTS`, `TOP_K`
  - `RETRY_ATTEMPTS`, `TIMEOUT_SECONDS`
- [x] `app/core/__init__.py` — singleton `settings`
- [x] Load `.env` tự động

---

## 🗄️ Bước 3: Database

**Mục tiêu:** SQLAlchemy 2.0 async session + Base models + Alembic migrations.

- [x] `app/db/session.py`:
  - `AsyncEngine`, `AsyncSessionLocal`
  - `get_db()` — async generator dependency
- [x] `app/db/base.py`:
  - `Base = declarative_base()`
  - `BaseMixin` (id, created_at, updated_at)
- [x] `app/db/models/`:
  - `Document`: id, filename, file_path, mime_type, size, version, metadata (JSONB), status, timestamps
  - `DocumentChunk`: id, document_id (FK), chunk_index, content, embedding (Vector), metadata (JSONB)
  - `ChunkMetadata`: id, chunk_id (FK), key, value
  - `IndexStatus`: id, type (bm25/vector), status, last_synced
- [x] `app/db/repository/`:
  - `BaseRepository` — generic CRUD async
  - `DocumentRepository`
  - `ChunkRepository`
  - `IndexStatusRepository`
- [x] `app/db/migrations/` — Alembic init + first migration

---

## 📄 Bước 4: Document Management

**Mục tiêu:** Upload, delete, list, versioning, metadata cho documents.

- [x] `app/schemas/document.py` — Pydantic models:
  - `DocumentCreate`, `DocumentResponse`, `DocumentList`, `DocumentVersion`
- [x] `app/services/document.py`:
  - `upload_file(file)` → lưu disk + DB record
  - `delete_file(document_id)` → xóa file + DB record
  - `list_files(filters, pagination)`
  - `get_versions(document_id)`
  - `update_metadata(document_id, metadata)`
- [x] `app/api/v1/documents.py`:
  - `POST /documents/upload`
  - `DELETE /documents/{id}`
  - `GET /documents`
  - `GET /documents/{id}/versions`
  - `PATCH /documents/{id}/metadata`
- [x] Validate file type & size

---

## 🔤 Bước 5: Embedding Service

**Mục tiêu:** Wrapper cho BAAI/bge-m3 với async, batch, retry, timeout.

- [x] `app/services/embedding/`:
  - `client.py` — `EmbeddingClient` (gọi API embedding model)
  - `schemas.py` — `EmbeddingRequest`, `EmbeddingResponse`
  - `service.py` — `EmbeddingService`:
    - `embed(texts: list[str]) → list[list[float]]`
    - `embed_query(query: str) → list[float]`
    - `embed_batch(texts, batch_size=32)`
    - `aembed(texts)`, `aembed_query(query)`, `aembed_batch(texts)`
  - `retry.py` — decorator tenacity retry + timeout
- [ ] (Optional) fallback nếu model không available

---

## 🗃️ Bước 6: Qdrant — Vector Store

**Mục tiêu:** Quản lý collection + vector operations trên Qdrant.

- [x] `app/services/qdrant/`:
  - `client.py` — `QdrantClientWrapper` (singleton connection)
  - `service.py` — `QdrantService`:
    - `create_collection(name, vector_size)`
    - `delete_collection(name)`
    - `upsert(collection, points)`
    - `batch_upsert(collection, points, batch_size)`
    - `search(collection, query_vector, limit, filters)`
    - `hybrid_search(collection, query_vector, bm25_scores, weight, limit)`
    - `scroll(collection, filter, limit)` (pagination)
    - `delete_points(collection, ids / filter)`
  - `schemas.py` — `QdrantPoint`, `QdrantSearchResult`, `QdrantFilter`
- [x] Retry + timeout cho mọi operation

---

## 📊 Bước 7: BM25

**Mục tiêu:** BM25 index riêng, support build/update/delete/search.

- [x] `app/services/bm25/`:
  - `indexer.py` — `BM25Indexer`:
    - `build_index(documents)`
    - `update_index(document_id, text)`
    - `delete_from_index(document_id)`
    - `search(query, top_k) → list[(doc_id, score)]`
  - Có thể dùng `rank_bm25` hoặc tự implement
  - Lưu index trên disk hoặc memory (cân nhắc persistent)

---

## 🔀 Bước 8: Hybrid Search

**Mục tiêu:** Kết hợp vector search + BM25 với Reciprocal Rank Fusion (RRF).

- [x] `app/services/retrieval/`:
  - `hybrid.py` — `HybridSearchService`:
    - `search(query, top_k, weight_vector, weight_bm25)`
    - Pipeline: Query → Embed → Vector Search → BM25 Search → Merge → RRF → Top K
  - `reranker.py` — `RerankerService`:
    - `rerank(query, candidates)`
- [x] `app/services/retrieval/schemas.py`:
  - `SearchQuery`, `SearchResult`, `RerankedResult`

---

## 🧠 Bước 9: PhoBERT Client

**Mục tiêu:** REST client cho PhoBERT deployed trên Google Colab.

- [ ] `app/services/phobert/`:
  - `client.py` — `PhoBERTClient`:
    - `health_check() → bool`
    - `predict(texts: list[str]) → list[dict]`
    - `predict_batch(texts, batch_size)`
    - `apredict(texts)`, `apredict_batch(texts)`
  - Retry + timeout + circuit breaker
  - `schemas.py` — `PhoBERTRequest`, `PhoBERTResponse`

---

## 🤖 Bước 10: LiteLLM

**Mục tiêu:** Wrapper unified LLM với routing, fallback, streaming.

- [ ] `app/services/llm/`:
  - `litellm.py` — `LiteLLMService`:
    - `chat(messages, model, options)`
    - `chat_stream(messages, model, options)`
    - `chat_with_fallback(messages, models, options)`
    - `get_token_usage(response)`
    - `model_routing(task_type) → model_name`
  - Support: Gemini, OpenAI-compatible, (future) Anthropic

---

## 🌌 Bước 11: Gemini

**Mục tiêu:** Wrapper riêng cho Gemini API (chat, vision, tool calling, JSON mode).

- [ ] `app/services/llm/`:
  - `gemini.py` — `GeminiService`:
    - `chat(message, system_prompt)`
    - `chat_vision(image_url, prompt)`
    - `chat_with_tools(message, tools)`
    - `chat_stream(message)`
    - `chat_json(message, response_schema)`
  - Sử dụng `google-generativeai` SDK hoặc LiteLLM

---

## 🔁 Bước 12: LangGraph

**Mục tiêu:** Xây dựng graph pipeline hoàn chỉnh.

- [ ] `app/graph/`:
  - `state.py` — `GraphState(TypedDict)`: query, rewritten_query, vector_results, bm25_results, hybrid_results, phobert_label, reranked, context, llm_response
  - `nodes.py`:
    - `rewrite_query(state)`
    - `hybrid_search_node(state)`
    - `phobert_classify(state)`
    - `rerank(state)`
    - `build_context(state)`
    - `llm_generate(state)`
  - `graph.py` — build LangGraph with:
    ```
    START → Rewrite → Hybrid Search → PhoBERT → Rerank → Context Builder → LLM → END
    ```
  - `service.py` — `GraphService.run(query) → response`

---

## ⚡ Bước 13: Spark Jobs

**Mục tiêu:** Apache Spark integration — submit job, status, cancel, ETL.

- [ ] `app/services/spark/`:
  - `session.py` — `SparkSessionManager` (singleton)
  - `jobs.py` — `SparkJobService`:
    - `submit_job(job_type, params) → job_id`
    - `get_job_status(job_id)`
    - `cancel_job(job_id)`
  - `etl.py` — `SparkETL`:
    - `batch_embedding(documents)`
    - `build_index(documents)`
    - `data_cleanup()`
- [ ] `app/schemas/spark.py` — `SparkJobRequest`, `SparkJobResponse`, `SparkJobStatus`

---

## ⏰ Bước 14: Scheduler

**Mục tiêu:** Background jobs định kỳ — daily index, sync, cleanup, retry.

- [ ] `app/workers/`:
  - `scheduler.py` — `BackgroundScheduler`:
    - `start()`, `stop()`
    - Jobs:
      - `daily_rebuild_index()` — rebuild BM25 + vector index
      - `sync_external_data()` — đồng bộ dữ liệu
      - `cleanup_old_versions()` — dọn dẹp version cũ
      - `retry_failed_jobs()` — retry Spark jobs failed
  - Sử dụng `apscheduler` hoặc `schedule`

---

## 🌐 Bước 15: REST API

**Mục tiêu:** Gắn kết tất cả module thành REST API hoàn chỉnh + Swagger.

- [ ] `app/api/v1/`:
  - `documents.py` — CRUD document
  - `search.py`:
    - `POST /search` — hybrid search
    - `POST /search/graph` — LangGraph pipeline
  - `embedding.py`:
    - `POST /embed` — embed texts
    - `POST /embed/query` — embed query
  - `collections.py`:
    - CRUD Qdrant collections
  - `spark.py`:
    - `POST /spark/jobs` — submit
    - `GET /spark/jobs/{id}` — status
    - `DELETE /spark/jobs/{id}` — cancel
  - `phobert.py`:
    - `POST /phobert/predict`
    - `GET /phobert/health`
  - `chat.py`:
    - `POST /chat` — LLM chat
    - `POST /chat/stream` — streaming chat
- [ ] `app/main.py` — FastAPI app:
  - CORS middleware
  - Global exception handler
  - Lifespan (start/stop scheduler, spark session, qdrant)
- [ ] `app/middleware/`:
  - `logging.py` — request/response logging
  - `timeout.py` — request timeout
- [ ] Swagger docs đầy đủ (tags, summary, response models)

---

## ❗ Bước 16: Exception Handling

**Mục tiêu:** Global + Business exceptions, xử lý tập trung.

- [ ] `app/core/exceptions.py`:
  - `AppException` (base, status_code, detail, error_code)
  - `NotFoundException`
  - `ValidationException`
  - `DatabaseException`
  - `EmbeddingException`
  - `VectorDBException`
  - `LLMException`
  - `PhoBERTException`
  - `SparkException`
  - `RetryExhaustedException`
- [ ] `app/core/error_handler.py`:
  - `global_exception_handler` → JSON response chuẩn
  - `validation_exception_handler` → 422 chi tiết

---

## 📖 Bước 17: README

**Mục tiêu:** Tài liệu project đầy đủ.

- [ ] Tổng quan architecture
- [ ] Hướng dẫn cài đặt (uv, docker)
- [ ] Danh sách API endpoints
- [ ] Cấu hình ENV
- [ ] Hướng dẫn deploy

---

## ✅ Nguyên Tắc Khi Implement

| Nguyên tắc | Mô tả |
|---|---|
| **Async-first** | Mọi I/O operation đều async |
| **Type Hint** | 100% functions có type hint |
| **Docstring** | Mỗi module/class/function có docstring |
| **Error Handling** | Không swallow exception, không bare except |
| **Retry + Timeout** | Mọi external call có retry + timeout |
| **No hardcode** | Config qua ENV (pydantic-settings) |
| **No pseudo code** | Code phải chạy được |
| **Commit sau mỗi bước** | Build → Test → Commit → Next |

---

> **Tiến độ:** 8/17 bước
