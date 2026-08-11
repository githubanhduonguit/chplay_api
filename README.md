# CH Play API - AI Agent tự động trả lời review

Hệ thống AI Agent thông minh tự động phân tích và trả lời các review trên Google Play Store (CH Play). Sử dụng **LangGraph** pipeline với hybrid search (Qdrant vector search + BM25), PhoBERT classification, RAG, và Web Search để tạo câu trả lời chính xác, có nguồn tham chiếu rõ ràng.

---

## 🏗️ Kiến trúc tổng quan

### Luồng xử lý chính

```
User Query
    │
    ▼
┌─────────────────┐
│  Rewrite Query  │  ← LLM viết lại query để search tốt hơn
└────────┬────────┘
         ▼
┌─────────────────┐
│  Hybrid Search  │  ← Vector search (Qdrant) + BM25 (keyword)
└────────┬────────┘
         ▼
┌─────────────────┐
│  Classification │  ← PhoBERT classify query (bug, feature, ...)
└────────┬────────┘
         ▼
┌─────────────────┐
│     Rerank      │  ← Cross-encoder rerank (nếu có)
└────────┬────────┘
         ▼
┌─────────────────┐
│  Context Builder│  ← Format RAG results → context string
└────────┬────────┘
         ▼
┌──────────────────────────┐
│  Web Search Decision     │  ← Kiểm tra RAG có đủ dữ liệu không?
└──────┬───────────┬───────┘
       │           │
    Cần web     Không cần
       │           │
       ▼           ▼
┌────────────┐  ┌────────────┐
│Web Search  │  │LLM Answer  │ ← Chỉ dùng RAG context
└─────┬──────┘  └────────────┘
      │                    ▲
      ▼                    │
┌─────────────────┐        │
│Web Context      │        │
│Builder          │        │
└─────┬───────────┘        │
      │                    │
      ▼                    │
┌─────────────────┐        │
│ Merge Context   │────────┘ ← Gộp RAG + Web context
│ (rag_plus_web)  │
└─────┬───────────┘
      │
      ▼
┌─────────────────┐
│   LLM Answer    │  ← GLM/LiteLLM sinh câu trả lời cuối
└─────────────────┘
      │
      ▼
   Final Answer
```

### Components chính

| Component | Công nghệ | Mô tả |
|-----------|-----------|-------|
| **Orchestration** | LangGraph + Python asyncio | Pipeline state graph |
| **Vector Store** | Qdrant | Lưu document embeddings |
| **Keyword Search** | BM25 (rank-bm25) | Search từ khóa truyền thống |
| **Embedding** | BAAI/bge-m3 | Text embedding 1024-d |
| **LLM** | GLM (qua LiteLLM) | Query rewrite + Answer generation |
| **Classification** | PhoBERT (custom model) | Phân loại intent của review |
| **Reranker** | Cross-encoder (pass-through hiện tại) | Rerank search results |
| **Web Search** | Google Custom Search API | Tra cứu thông tin web khi RAG thiếu |
| **Database** | PostgreSQL (Neon) + SQLAlchemy async | Lưu review, comment, document |
| **Scheduler** | APScheduler | Job tự động xử lý review |

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone <repo-url>
cd chplay_api
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Cấu hình môi trường

Tạo file `.env` từ mẫu:

```bash
cp .env.example .env
```

### 3. Chạy ứng dụng

```bash
# API server
uvicorn app.main:app --reload

# Hoặc chạy job generate review replies
python -m app.jobs.generate_review_replies --limit 10
```

---

## 🔧 Cấu hình môi trường

### Biến bắt buộc

| Biến | Mô tả | Mặc định |
|------|-------|----------|
| `DATABASE_URL` | PostgreSQL async connection string | _(required)_ |
| `ZAI_API_KEY` | Z.AI (Zhipu AI) API key cho GLM models | _(required for LLM)_ |
| `LITELLM_API_KEY` | LiteLLM API key | _(optional)_ |

### VDB & Search

| Biến | Mô tả | Mặc định |
|------|-------|----------|
| `QDRANT_URL` | Qdrant server URL | `http://localhost:6333` |
| `QDRANT_API_KEY` | Qdrant API key | `""` |
| `QDRANT_COLLECTION` | Collection name | `documents` |
| `EMBEDDING_API_URL` | Embedding server URL | `http://localhost:8001/v1/embeddings` |
| `EMBEDDING_MODEL` | Embedding model | `BAAI/bge-m3` |

### Web Search (Google Custom Search)

> **Mặc định tắt** (`WEB_SEARCH_ENABLED=False`). Bật khi có nhu cầu tra cứu web.

| Biến | Mô tả | Mặc định |
|------|-------|----------|
| `WEB_SEARCH_ENABLED` | Bật/tắt web search | `False` |
| `WEB_SEARCH_PROVIDER` | Provider (hiện chỉ hỗ trợ `google_custom_search`) | `google_custom_search` |
| `WEB_SEARCH_API_KEY` | Google API key **(required nếu bật)** | `""` |
| `WEB_SEARCH_ENGINE_ID` | Google Custom Search Engine ID (cx) **(required nếu bật)** | `""` |
| `WEB_SEARCH_TIMEOUT` | Timeout mỗi request (giây) | `15` |
| `WEB_SEARCH_TOP_K` | Số kết quả tối đa mỗi search | `5` |
| `WEB_SEARCH_LANGUAGE` | Ngôn ngữ (`lang_vi`, `lang_en`) | `lang_vi` |
| `WEB_SEARCH_SAFE_SEARCH` | Safe search (`active`, `off`) | `active` |
| `WEB_SEARCH_MIN_RAG_SCORE` | Ngưỡng score RAG tối thiểu để quyết định có cần web search | `0.3` |

> **Hướng dẫn lấy Google Custom Search API key:**
> 1. Vào [Google Cloud Console](https://console.cloud.google.com/) → tạo project mới
> 2. Bật **Custom Search API** → tạo API key
> 3. Vào [Programmable Search Engine](https://programmablesearchengine.google.com/) → tạo search engine
> 4. Copy **Search engine ID (cx)** và **API key** vào `.env`

### LLM & Models

| Biến | Mô tả | Mặc định |
|------|-------|----------|
| `LITELLM_MODEL` | Model chính | `zai/glm-4.7-flash` |
| `ZAI_API_KEY` | Z.AI (Zhipu AI) API key cho GLM models | `""` |
| `LITELLM_API_KEY` | LiteLLM API key (ưu tiên hơn `ZAI_API_KEY`) | `""` |
| `LITELLM_FALLBACK_MODELS` | Fallback models (comma-separated) | `""` |
| `PHOBERT_API_URL` | PhoBERT classification API | `""` |
| `GEMINI_MODEL` | Gemini model name | `gemini-3.5-flash` |

---

## 🌐 Web Search Integration

### Khi nào web search được gọi?

Web search chỉ được kích hoạt khi **RAG/hybrid search nội bộ không đủ dữ liệu**:

1. **RAG không có kết quả**: `search_results` rỗng
2. **Context rỗng**: Context builder trả `"No relevant documents found."`
3. **Score thấp**: Top score của RAG < `WEB_SEARCH_MIN_RAG_SCORE` (mặc định 0.3)

### Khi nào web search bị bỏ qua?

Web search tự động bị bỏ qua cho các query liên quan đến dữ liệu nội bộ:
- Review, ticket, bug report
- Câu hỏi về rating, app version
- Comment, reply, status
- Được PhoBERT classify là `bug_report`, `feature_request`, `complaint`

### Source modes

Sau khi xử lý, context được gắn nhãn để LLM biết nguồn thông tin:

| Mode | Ý nghĩa |
|------|---------|
| `rag_only` | Chỉ dùng dữ liệu nội bộ (RAG) |
| `web_only` | Chỉ dùng dữ liệu web (RAG không có) |
| `rag_plus_web` | Kết hợp cả hai nguồn (RAG ưu tiên) |
| `none` | Không có thông tin từ nguồn nào |

### Citation format

```text
[RAG context]
[1] Thông tin từ document nội bộ...
[2] ...

[Web context]
[W1] Tiêu đề trang web
URL: https://example.com
Snippet mô tả...

[W2] ...
```

### Cấu hình cho từng môi trường

```bash
# Development — tắt web search
WEB_SEARCH_ENABLED=False

# Production — bật web search
WEB_SEARCH_ENABLED=True
WEB_SEARCH_API_KEY=your_google_api_key
WEB_SEARCH_ENGINE_ID=your_search_engine_id
WEB_SEARCH_TIMEOUT=15
WEB_SEARCH_TOP_K=5
```

---

## 📡 API Endpoints

### `POST /api/v1/search` — Search với RAG pipeline

```json
{
  "query": "Làm sao để reset mật khẩu?",
  "collection": "documents",
  "top_k": 5
}
```

### `POST /api/v1/query` — Chat với AI Agent (RAG + Web Search)

```json
{
  "query": "Tính năng mới nhất trên phiên bản 2.0 là gì?"
}
```

### `POST /api/v1/reviews/reply` — Generate review reply

```json
{
  "review_id": 123
}
```

---

## 🧪 Testing

```bash
# Chạy tất cả tests
python -m pytest

# Chạy tests cho graph
python -m pytest tests/graph/

# Chạy tests cho services
python -m pytest tests/services/
```

## 🗂️ Project Structure

```
app/
├── api/                    # FastAPI routes
│   └── v1/                 # API version 1
├── core/                   # Config, exceptions
│   └── config.py           # Settings (env vars)
├── db/                     # Database models, migrations
├── graph/                  # LangGraph pipeline
│   ├── state.py            # GraphState definition
│   ├── nodes.py            # Pipeline nodes
│   ├── graph.py            # Graph builder
│   └── service.py          # Graph service
├── jobs/                   # Background jobs
│   └── generate_review_replies.py
├── services/               # Business logic services
│   ├── agents/
│   │   └── review_reply_agent.py   # Review reply agent
│   ├── embedding/          # Text embedding
│   ├── bm25/               # Keyword search
│   ├── qdrant/             # Vector store
│   ├── retrieval/          # Hybrid search, reranker
│   ├── web_search/         # 🌐 Web search (Google CSE)
│   │   ├── schemas.py      # Request/response schemas
│   │   ├── client.py       # Google API client
│   │   └── service.py      # Web search service
│   ├── llm/                # LLM services (Gemini, GLM, LiteLLM)
│   ├── phobert/            # PhoBERT classification
│   ├── chunking/           # Document chunking
│   ├── spark/              # Spark session
│   └── reranker/           # Result reranking
├── schemas/                # Pydantic schemas
└── workers/                # Worker tasks
```

---

## 📝 License

MIT
