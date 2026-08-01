# Chương 5. Thực nghiệm

---

## 5.1 Môi trường thực nghiệm

### 5.1.1 Phần cứng

| Thành phần | Cấu hình |
|------------|----------|
| **CPU** | … (ví dụ: Intel Core i7-12700H, 14 cores, 20 threads) |
| **RAM** | … (ví dụ: 32 GB DDR5) |
| **GPU** | … (ví dụ: NVIDIA RTX 3060 6GB — nếu dùng cho embedding/phoBERT) |
| **Ổ cứng** | … (ví dụ: SSD NVMe 512 GB) |
| **Hệ điều hành** | Windows 11 / Ubuntu 22.04 |

### 5.1.2 Phần mềm & Thư viện

| Thành phần | Phiên bản |
|------------|-----------|
| **Python** | 3.12+ |
| **FastAPI** | ≥0.110 |
| **LangGraph** | ≥0.2 |
| **LiteLLM** | ≥1.40 |
| **Qdrant** | ≥1.9 (client + server) |
| **PhoBERT** | (`vinai/phobert-base` fine-tuned) |
| **rank-bm25** | ≥0.2 |
| **PostgreSQL** | 15+ (Neon Serverless) |
| **SQLAlchemy** | ≥2.0 |
| **Apache Spark** | 3.5 (local mode) |
| **APScheduler** | ≥3.10 |
| **httpx** | ≥0.27 |
| **Google Generative AI SDK** | ≥0.8 |

> **Ghi chú:** PhoBERT được triển khai dưới dạng REST API trên Google Colab (hoặc server riêng).  
> Embedding model BAAI/bge-m3 chạy qua API endpoint riêng (ví dụ: vLLM hoặc FastAPI).

---

## 5.2 Dữ liệu thực nghiệm

### 5.2.1 Nguồn dữ liệu

- **Google Play Store (CH Play):** Các review tiếng Việt từ ứng dụng … (tên app hoặc category).
- **Document nội bộ:** FAQ, hướng dẫn sử dụng, changelog, tài liệu hỗ trợ.
- **Dữ liệu web:** Google Custom Search Index (tìm kiếm khi thiếu context nội bộ).

### 5.2.2 Thống kê dữ liệu

| Loại dữ liệu | Số lượng | Ghi chú |
|--------------|----------|---------|
| Tổng số review thu thập | … | |
| Review có label (PhoBERT) | … | |
| Document (chunked) | … chunks | Chunk size: 512, overlap: 64 |
| Document vectorized | … vectors | Embedding dim: 1024 (bge-m3) |
| BM25 index | … documents | |
| Bộ test (query đánh giá thủ công) | … queries | |

### 5.2.3 Phân bố nhãn của review (PhoBERT Classification)

| Nhãn | Số lượng | Tỉ lệ |
|------|----------|-------|
| bug_report | … | …% |
| feature_request | … | …% |
| complaint | … | …% |
| support_ticket | … | …% |
| praise | … | …% |
| other / question | … | …% |
| **Tổng** | … | 100% |

---

## 5.3 Cấu hình tham số thực nghiệm

### 5.3.1 Embedding & Vector Search

| Tham số | Giá trị | Mô tả |
|---------|---------|-------|
| Embedding model | `BAAI/bge-m3` | Multilingual embedding |
| Embedding dimension | 1024 | |
| Qdrant collection | `documents` | |
| Qdrant similarity | Cosine | |
| Qdrant top_k (vector) | 20 | Số lượng vector gọi về trước khi fusion |
| Score threshold | None | Không ngưỡng |

### 5.3.2 BM25

| Tham số | Giá trị | Mô tả |
|---------|---------|-------|
| BM25 algorithm | Okapi BM25 (rank_bm25) | |
| k1 | 1.5 | BM25 parameter |
| b | 0.75 | BM25 parameter |
| top_k (BM25) | 20 | |

### 5.3.3 Hybrid Search (RRF Fusion)

| Tham số | Giá trị | Mô tả |
|---------|---------|-------|
| weight_vector | 0.5 | Trọng số vector search |
| weight_bm25 | 0.5 | Trọng số BM25 search |
| RRF k | 60 | Hằng số RRF |
| top_k (final) | 10 | Số kết quả cuối cùng |

### 5.3.4 LLM (Gemini / LiteLLM)

| Tham số | Giá trị | Mô tả |
|---------|---------|-------|
| Model chính | `gemini-3.5-flash` | Via LiteLLM |
| Fallback models | (none / …) | |
| Temperature (query rewrite) | 0.3 | |
| Temperature (answer) | 0.7 | |
| Max tokens (answer) | 2048 | |
| Max context chars | 8000 (RAG) + 4000 (web) | |

### 5.3.5 Web Search

| Tham số | Giá trị |
|---------|---------|
| Provider | Google Custom Search |
| top_k | 5 |
| Language | `lang_vi` |
| Safe search | `active` |
| Min RAG score threshold | 0.3 |
| Timeout | 15s |

### 5.3.6 PhoBERT Classification

| Tham số | Giá trị |
|---------|---------|
| Base model | `vinai/phobert-base` |
| Fine-tuned? | Có / Không |
| Batch size | 32 |
| API timeout | 30s |
| Max retries | 3 |

---

## 5.4 Các kịch bản thực nghiệm

### 5.4.1 Thực nghiệm 1: Đánh giá hiệu năng tìm kiếm (Retrieval Quality)

**Mục tiêu:** Đo lường chất lượng truy vấn của các phương pháp search riêng lẻ và kết hợp.

**Các phương pháp so sánh:**

| Phương pháp | Mô tả |
|-------------|-------|
| **Vector-only** | Chỉ dùng Qdrant vector search (cosine similarity) |
| **BM25-only** | Chỉ dùng Okapi BM25 keyword search |
| **Hybrid (RRF)** | Kết hợp vector + BM25 với RRF (trọng số 0.5-0.5) |
| **Hybrid + Rerank** | Hybrid + pass-through reranker |

**Metric đánh giá:**

- **Precision@k** (k = 1, 3, 5, 10)
- **Recall@k** (k = 5, 10)
- **MRR** (Mean Reciprocal Rank)
- **NDCG@k** (k = 5, 10)

**Kết quả:**

| Phương pháp | P@1 | P@5 | P@10 | R@5 | R@10 | MRR | NDCG@10 |
|-------------|-----|-----|------|-----|------|-----|---------|
| Vector-only | … | … | … | … | … | … | … |
| BM25-only | … | … | … | … | … | … | … |
| Hybrid (RRF) | … | … | … | … | … | … | … |
| Hybrid + Rerank | … | … | … | … | … | … | … |

**Nhận xét:**
- …
- …

---

### 5.4.2 Thực nghiệm 2: Đánh giá chất lượng câu trả lời (Answer Quality)

**Mục tiêu:** Đánh giá chất lượng câu trả lời cuối cùng của pipeline dưới các chế độ context khác nhau.

**Các chế độ:**

| Chế độ | Mô tả |
|--------|-------|
| **LLM-only** | LLM trả lời trực tiếp không có RAG context |
| **RAG-only** | Chỉ dùng context từ hybrid search |
| **RAG + Web** | Dùng cả RAG context và web search context |
| **Full pipeline** | Toàn bộ pipeline gồm: rewrite → hybrid → phobert → rerank → context → web decision → merge → LLM |

**Metric đánh giá (đánh giá thủ công bởi 3 annotator):**

| Metric | Mô tả |
|--------|-------|
| **Relevance** | Mức độ liên quan của câu trả lời với câu hỏi (1-5) |
| **Accuracy** | Mức độ chính xác về mặt thông tin (1-5) |
| **Completeness** | Mức độ đầy đủ của câu trả lời (1-5) |
| **Conciseness** | Mức độ ngắn gọn, đúng trọng tâm (1-5) |
| **Citation quality** | Chất lượng trích dẫn nguồn (1-5) |
| **Language quality** | Chất lượng tiếng Việt, tự nhiên (1-5) |

**Kết quả:**

| Chế độ | Relevance | Accuracy | Completeness | Conciseness | Citation | Language | **Trung bình** |
|--------|-----------|----------|--------------|-------------|----------|----------|----------------|
| LLM-only | … | … | … | … | N/A | … | … |
| RAG-only | … | … | … | … | … | … | … |
| RAG + Web | … | … | … | … | … | … | … |
| Full pipeline | … | … | … | … | … | … | … |

**Nhận xét:**
- …
- …

---

### 5.4.3 Thực nghiệm 3: Đánh giá hiệu năng PhoBERT Classification

**Mục tiêu:** Đánh giá độ chính xác của PhoBERT trong việc phân loại intent của review.

**Metric:** Accuracy, Precision, Recall, F1-score.

**Confusion Matrix:**

| | bug_report | feature_request | complaint | praise | other/question |
|-------------|------------|-----------------|-----------|--------|----------------|
| bug_report | … | … | … | … | … |
| feature_request | … | … | … | … | … |
| complaint | … | … | … | … | … |
| praise | … | … | … | … | … |
| other/question | … | … | … | … | … |

**Kết quả phân loại:**

| Nhãn | Precision | Recall | F1-score | Support |
|------|-----------|--------|----------|---------|
| bug_report | … | … | … | … |
| feature_request | … | … | … | … |
| complaint | … | … | … | … |
| praise | … | … | … | … |
| other/question | … | … | … | … |
| **Macro avg** | … | … | … | … |
| **Weighted avg** | … | … | … | … |
| **Accuracy** | **…%** | | | |

**Nhận xét:**
- …
- …

---

### 5.4.4 Thực nghiệm 4: Web Search Decision — Độ chính xác quyết định

**Mục tiêu:** Đánh giá khả năng quyết định **khi nào cần web search** của pipeline.

**Các tiêu chí:**

| Quyết định | Label thực tế |
|-------------|---------------|
| Need web = True | Cần web (thiếu context nội bộ) |
| Need web = False | Không cần web (context nội bộ đủ) |

**Confusion matrix cho quyết định web search:**

| | Cần web (thực tế) | Không cần web (thực tế) |
|---|-------------------|------------------------|
| **Cần web (dự đoán)** | TP = … | FP = … |
| **Không cần web (dự đoán)** | FN = … | TN = … |

**Kết quả:**

| Metric | Giá trị |
|--------|---------|
| Accuracy | …% |
| Precision | …% |
| Recall | …% |
| F1-score | … |
| False positive rate (fetc.h web không cần thiết) | …% |
| False negative rate (bỏ sót cần web) | …% |

**Nhận xét:**
- …
- …

---

### 5.4.5 Thực nghiệm 5: Ablation Study

**Mục tiêu:** Đo lường đóng góp của từng thành phần trong pipeline.

| Cấu hình | Thành phần bỏ qua | Metric chính (VD: Relevance avg) | Thay đổi so với full pipeline |
|-----------|-------------------|----------------------------------|-------------------------------|
| Full pipeline | — | … | baseline |
| No rewrite | Bỏ qua rewrite query | … | … |
| No BM25 | Chỉ dùng vector search | … | … |
| No vector | Chỉ dùng BM25 | … | … |
| No rerank | Bỏ qua reranker | … | … |
| No web search | Tắt web search | … | … |
| No phobert | Bỏ qua classification | … | … |

**Nhận xét:**
- …
- …

---

### 5.4.6 Thực nghiệm 6: Đánh giá thời gian xử lý (Latency)

**Mục tiêu:** Đo lường thời gian xử lý trung bình của từng node và toàn pipeline.

| Node | Thời gian TB (ms) | Phân vị 50% (ms) | Phân vị 95% (ms) | Phân vị 99% (ms) |
|------|-------------------|------------------|------------------|------------------|
| Rewrite Query | … | … | … | … |
| Hybrid Search (embed + vector + bm25) | … | … | … | … |
| PhoBERT Classify | … | … | … | … |
| Rerank | … | … | … | … |
| Context Builder | … | … | … | … |
| Web Search Decision | … | … | … | … |
| Web Search (nếu có) | … | … | … | … |
| Merge Context | … | … | … | … |
| LLM Answer Generation | … | … | … | … |
| **Total (avg)** | **…** | **…** | **…** | **…** |
| **Total (có web search)** | **…** | **…** | **…** | **…** |
| **Total (không web search)** | **…** | **…** | **…** | **…** |

**Nhận xét:**
- Node tốn nhiều thời gian nhất: … (ví dụ: LLM Answer Generation)
- Tác động của web search đến latency tổng thể: …
- …

---

## 5.5 Kết quả định tính (Qualitative Analysis)

### 5.5.1 Ví dụ câu trả lời tốt

> **Query:** "Làm sao để reset mật khẩu?"
>
> **Context:** [RAG] Document về hướng dẫn reset mật khẩu (score: 0.85)
>
> **Answer:**
> ```
> Bạn có thể reset mật khẩu bằng cách:
> 1. Vào mục "Cài đặt" → "Tài khoản"
> 2. Chọn "Đổi mật khẩu"
> 3. Nhập email đã đăng ký
> 4. Làm theo hướng dẫn trong email
>
> [1] Hướng dẫn sử dụng ứng dụng - mục Tài khoản
> ```
>
> **Đánh giá:** Relevance 5/5, Accuracy 5/5, Citation đầy đủ.

### 5.5.2 Ví dụ câu trả lời cần web search

> **Query:** "Tính năng mới nhất trên phiên bản 2.0 là gì?"
>
> **Context:** [RAG] không có document về phiên bản 2.0 → Web search được kích hoạt.
>
> **Answer:**
> ```
> Phiên bản 2.0 vừa ra mắt với các tính năng mới:
> - Giao diện người dùng được thiết kế lại
> - Hỗ trợ Dark Mode
> - Cải thiện tốc độ tải 40%
>
> Lưu ý: Thông tin này được lấy từ nguồn web, không phải dữ liệu nội bộ của ứng dụng.
> [W1] Trang chủ ứng dụng
> URL: https://example.com/changelog
> ```
>
> **Đánh giá:** Relevance 5/5, sử dụng web search đúng lúc, cảnh báo nguồn rõ ràng.

### 5.5.3 Ví dụ câu trả lời chưa tốt (Error Analysis)

> **Query:** "Khi nào app fix lỗi đăng nhập?"
>
> **Answer dự kiến:**
> ```
> Chúng tôi đã ghi nhận lỗi đăng nhập và đang khắc phục. ...
> ```
>
> **Vấn đề gặp phải:**
> - … (ví dụ: RAG không tìm thấy document liên quan)
> - … (ví dụ: Web search trả về thông tin không chính xác)
>
> **Nguyên nhân:**
> - …
>
> **Hướng cải thiện:**
> - …

---

## 5.6 Thảo luận

### 5.6.1 Nhận xét chung

- Pipeline hoạt động hiệu quả với các câu hỏi có context nội bộ tốt (điểm RAG > 0.3).
- Web search bù đắp tốt cho những câu hỏi thiếu context nội bộ, nhưng cần cẩn trọng với chất lượng nguồn web.
- PhoBERT classification giúp pipeline đưa ra quyết định chính xác hơn (bỏ qua web search cho bug report, complaint).
- Hybrid search (vector + BM25) cho kết quả tốt hơn từng phương pháp riêng lẻ trong hầu hết trường hợp.

### 5.6.2 Các yếu tố ảnh hưởng đến kết quả

1. **Chất lượng dữ liệu nội bộ:** Document càng đầy đủ, pipeline càng ít phải dùng web search.
2. **Chất lượng embedding:** bge-m3 cho kết quả tốt với tiếng Việt nhưng vẫn có hạn chế với từ ngữ chuyên ngành.
3. **Ngưỡng RAG score:** Ngưỡng 0.3 là phù hợp, nhưng cần tinh chỉnh theo từng loại câu hỏi.
4. **PhoBERT fine-tuning:** Mô hình nền phobert-base cần fine-tune trên dữ liệu review thực tế để đạt accuracy cao.
5. **Temperature của LLM:** Temperature 0.7 phù hợp cho sinh câu trả lời sáng tạo nhưng đôi khi gây hallucination nhẹ.

### 5.6.3 Hạn chế của thực nghiệm

- Kích thước bộ dữ liệu đánh giá thủ công còn nhỏ (… queries).
- Chất lượng đánh giá phụ thuộc vào annotator (có thể thiếu nhất quán).
- Chưa có A/B testing trên production.
- Chưa đánh giá trên đa dạng ứng dụng (mới chỉ test trên 1-2 app).

### 5.6.4 Hướng phát triển

- Fine-tune reranker (cross-encoder) thay vì pass-through hiện tại.
- Mở rộng bộ dữ liệu đánh giá (100+ queries, đa dạng thể loại).
- Thêm phản hồi từ người dùng để cải thiện pipeline (RLHF / active learning).
- Tích hợp thêm nguồn dữ liệu (Zendesk, email support, …).
- Tối ưu latency (caching, async processing, …).

---

## 5.7 Tóm tắt chương

Chương 5 đã trình bày chi tiết:

1. **Môi trường và dữ liệu thực nghiệm** — cấu hình phần cứng, phần mềm, thống kê dữ liệu.
2. **Cấu hình tham số** — embedding, BM25, hybrid search, LLM, web search, PhoBERT.
3. **6 kịch bản thực nghiệm:**
   - Đánh giá hiệu năng tìm kiếm (Retrieval Quality)
   - Đánh giá chất lượng câu trả lời (Answer Quality)
   - Đánh giá PhoBERT Classification
   - Đánh giá quyết định web search
   - Ablation Study
   - Đánh giá thời gian xử lý (Latency)
4. **Kết quả định tính** — ví dụ câu trả lời tốt, cần web search, và phân tích lỗi.
5. **Thảo luận** — nhận xét, yếu tố ảnh hưởng, hạn chế, hướng phát triển.

Kết quả thực nghiệm cho thấy pipeline đề xuất hoạt động hiệu quả trong việc tự động trả lời review tiếng Việt trên CH Play, đặc biệt khi kết hợp cả RAG context và web search. Tuy nhiên, vẫn còn nhiều hướng cải thiện để nâng cao chất lượng và độ tin cậy của hệ thống.

---

> **📝 Hướng dẫn điền kết quả:**
>
> 1. Các ô trống (…) cần được điền số liệu thực tế sau khi chạy thực nghiệm.
> 2. Nên chạy mỗi thực nghiệm ít nhất 3 lần và lấy giá trị trung bình.
> 3. Với đánh giá thủ công, nên có ít nhất 2-3 annotator và tính inter-annotator agreement (Cohen's Kappa).
> 4. Dataset test nên có ít nhất 30-50 queries để đảm bảo ý nghĩa thống kê.
