# Mẫu Thực Nghiệm 1: Đánh giá hiệu năng tìm kiếm (Retrieval Quality)

---

## 1. Mục tiêu

Đo lường và so sánh chất lượng truy vấn của bốn phương pháp tìm kiếm trong pipeline RAG:

| Phương pháp | Mô tả |
|-------------|-------|
| **Vector-only** | Chỉ sử dụng Qdrant vector search (cosine similarity) với embedding BAAI/bge-m3 (1024-d) |
| **BM25-only** | Chỉ sử dụng Okapi BM25 keyword search (k1 = 1.5, b = 0.75) |
| **Hybrid (RRF)** | Kết hợp Vector + BM25 với Reciprocal Rank Fusion (trọng số 0.5-0.5, k = 60) |
| **Hybrid + Rerank** | Hybrid + pass-through reranker (giữ nguyên thứ tự) |

---

## 2. Bộ dữ liệu đánh giá

### 2.1 Test set

- **50 câu hỏi đánh giá** được xây dựng thủ công từ các review thực tế trên CH Play.
- Mỗi câu hỏi được gán **ground-truth document(s)** có liên quan (đánh giá bởi 3 annotator).
- Phân bố thể loại câu hỏi:

| Thể loại | Số lượng | Ví dụ |
|----------|----------|-------|
| Hướng dẫn sử dụng | 15 | "Làm sao để đổi mật khẩu?" |
| Báo lỗi / Sự cố | 12 | "Sao app cứ bị crash khi mở camera?" |
| Hỏi về tính năng | 10 | "App có hỗ trợ Dark Mode không?" |
| Yêu cầu tính năng | 8 | "Khi nào có tính năng chuyển khoản?" |
| Câu hỏi chung | 5 | "App này có tốt không?" |

### 2.2 Ground-truth statistics

- Trung bình **2.4 tài liệu liên quan** trên mỗi câu hỏi.
- Tổng số cặp (query, relevant_doc): **120 cặp**.
- Tổng số document trong kho dữ liệu: **1,247 chunks** (512 tokens/chunk, overlap 64).

---

## 3. Quy trình đánh giá

```
Test set (50 queries)
    │
    ├── Vector-only:   embed → search Qdrant → top-K
    ├── BM25-only:     tokenize → BM25 search → top-K
    ├── Hybrid (RRF):  embed → search Qdrant + BM25 → RRF fusion → top-K
    └── Hybrid+Rerank: embed → search Qdrant + BM25 → RRF fusion → rerank → top-K
    │
    └── So sánh với ground-truth → Tính Precision@k, Recall@k, MRR, NDCG@k
```

Mỗi phương pháp được chạy **3 lần** và lấy giá trị trung bình.

---

## 4. Metrics

| Metric | Công thức | Ý nghĩa |
|--------|-----------|---------|
| **Precision@k** | TP@k / k | Tỉ lệ tài liệu liên quan trong top-k |
| **Recall@k** | TP@k / total_relevant | Tỉ lệ tài liệu liên quan được tìm thấy |
| **MRR** | Trung bình 1/rank của tài liệu liên quan đầu tiên | Đo độ nhanh tìm thấy kết quả đầu tiên |
| **NDCG@k** | DCG@k / IDCG@k | Đo chất lượng thứ tự sắp xếp có trọng số |

---

## 5. Kết quả

### 5.1 Kết quả tổng quan

| Phương pháp | P@1 | P@3 | P@5 | R@5 | R@10 | MRR | NDCG@5 | NDCG@10 |
|-------------|:---:|:---:|:---:|:---:|:----:|:---:|:------:|:-------:|
| Vector-only | 0.640 | 0.553 | 0.472 | 0.583 | 0.708 | 0.712 | 0.614 | 0.668 |
| BM25-only | 0.580 | 0.513 | 0.436 | 0.542 | 0.667 | 0.654 | 0.571 | 0.625 |
| **Hybrid (RRF)** | **0.740** | **0.653** | **0.556** | **0.708** | **0.833** | **0.798** | **0.698** | **0.752** |
| Hybrid + Rerank | 0.740 | 0.647 | 0.552 | 0.700 | 0.825 | 0.798 | 0.692 | 0.747 |

> **Bảng 5.1:** Kết quả đánh giá hiệu năng tìm kiếm trên test set 50 queries.

### 5.2 Biểu đồ so sánh (đề xuất)

```mermaid
---
title: So sánh Precision@k giữa các phương pháp
---
xychart-beta
  x-title "k"
  y-title "Precision"
  x-axis [1, 3, 5, 10]
  line "Vector-only" [0.640, 0.553, 0.472, 0.358]
  line "BM25-only" [0.580, 0.513, 0.436, 0.342]
  line "Hybrid (RRF)" [0.740, 0.653, 0.556, 0.417]
```

```mermaid
---
title: So sánh Recall@k giữa các phương pháp
---
xychart-beta
  x-title "k"
  y-title "Recall"
  x-axis [5, 10]
  y-axis [0, 1]
  bar "Vector-only" [0.583, 0.708]
  bar "BM25-only" [0.542, 0.667]
  bar "Hybrid (RRF)" [0.708, 0.833]
  bar "Rerank" [0.700, 0.825]
```

### 5.3 Phân tích chi tiết theo thể loại câu hỏi

| Thể loại | Số lượng | Phương pháp tốt nhất | P@5 | Nhận xét |
|----------|:--------:|:--------------------:|:---:|----------|
| Hướng dẫn sử dụng | 15 | Hybrid (RRF) | 0.693 | BM25 cho kết quả tốt vì query chứa nhiều keyword đặc trưng |
| Báo lỗi / Sự cố | 12 | Vector-only | 0.617 | Vector search hiểu ngữ nghĩa tốt hơn với từ ngữ biến thể |
| Hỏi về tính năng | 10 | Hybrid (RRF) | 0.640 | Hybrid tận dụng được cả keyword lẫn ngữ nghĩa |
| Yêu cầu tính năng | 8 | Hybrid (RRF) | 0.575 | Kết quả thấp nhất — thiếu document liên quan |
| Câu hỏi chung | 5 | Hybrid (RRF) | 0.720 | Query ngắn, BM25 + Vector bù trừ cho nhau |

---

## 6. Phân tích kết quả

### 6.1 Vector-only vs BM25-only

**Vector-only** vượt trội hơn **BM25-only** ở tất cả các metrics:

| Metric | Vector | BM25 | Chênh lệch |
|--------|:------:|:----:|:----------:|
| P@1 | 0.640 | 0.580 | **+10.3%** |
| R@10 | 0.708 | 0.667 | **+6.1%** |
| MRR | 0.712 | 0.654 | **+8.9%** |

**Giải thích:**
- BGE-M3 embedding model có khả năng hiểu ngữ nghĩa tiếng Việt tốt, kể cả với từ ngữ không chính thống (teen code, viết tắt, sai chính tả).
- BM25 phụ thuộc vào keyword matching, dễ miss khi query dùng từ đồng nghĩa (VD: "đổi mật khẩu" ≠ "reset password" theo keyword).
- Tuy nhiên, BM25 vẫn hữu ích với các query chứa từ khóa hiếm/đặc thù (VD: "mã lỗi 500", "crash iphone 14").

### 6.2 Hybrid (RRF) vượt trội

**Hybrid (RRF)** cho kết quả tốt nhất ở hầu hết các metrics:

| Metric | Hybrid | Vector (tốt nhì) | Cải thiện |
|--------|:------:|:----------------:|:---------:|
| P@1 | **0.740** | 0.640 | **+15.6%** |
| R@5 | **0.708** | 0.583 | **+21.4%** |
| R@10 | **0.833** | 0.708 | **+17.6%** |
| MRR | **0.798** | 0.712 | **+12.1%** |

**Giải thích:**
- RRF fusion kết hợp được ưu điểm của cả hai phương pháp:
  - Vector search góp phần tìm tài liệu có ngữ nghĩa tương đồng (ngay cả khi không cùng từ khóa).
  - BM25 góp phần boost các tài liệu có keyword chính xác.
- Khi một phương pháp cho kết quả kém (VD: BM25 không tìm thấy document do từ đồng nghĩa), phương pháp kia vẫn có thể "cứu" được kết quả.
- RRF với k = 60 giúp giảm ảnh hưởng của ranking thấp từ một phía.

### 6.3 Tác động của Reranker

**Hybrid + Rerank** (pass-through) không cải thiện đáng kể so với Hybrid thuần:

| Metric | Hybrid | Hybrid+Rerank | Chênh lệch |
|--------|:------:|:-------------:|:----------:|
| P@5 | 0.556 | 0.552 | -0.4% |
| R@10 | 0.833 | 0.825 | -0.8% |
| NDCG@10 | 0.752 | 0.747 | -0.5% |

**Giải thích:**
- Reranker hiện tại là pass-through (không có cross-encoder), do đó giữ nguyên kết quả RRF.
- Chênh lệch nhỏ là do nhiễu thống kê giữa các lần chạy.
- **Kết luận:** Cần triển khai cross-encoder reranker (VD: BAAI/bge-reranker-v2-m3) để reranker thực sự có ích.

### 6.4 Example queries điển hình

**Ví dụ 1: Hybrid cải thiện (Query: "Làm sao để đăng xuất tài khoản?")**

| Phương pháp | Top-1 | Score | Relevant? |
|-------------|-------|:-----:|:---------:|
| Vector-only | "Hướng dẫn đăng nhập ứng dụng" | 0.82 | ❌ (gần ngữ nghĩa nhưng sai) |
| BM25-only | (không tìm thấy) | — | ❌ |
| **Hybrid (RRF)** | **"Cách đăng xuất và bảo mật tài khoản"** | **0.61** | **✅** |

> Vector search tìm thấy "đăng nhập" (gần nghĩa với "đăng xuất") nhưng không đúng.  
> BM25 không tìm thấy do query không có keyword đặc thù.  
> Khi kết hợp, RRF fusion vớt được document đúng ở hạng thấp hơn.

**Ví dụ 2: Vector vượt trội (Query: "App lag quá, chậm như rùa")**

| Phương pháp | Top-1 | Score | Relevant? |
|-------------|-------|:-----:|:---------:|
| **Vector-only** | **"Tối ưu hiệu năng ứng dụng"** | **0.79** | **✅** |
| BM25-only | "Hướng dẫn nuôi rùa cảnh" | 0.45 | ❌ (keyword "rùa") |
| Hybrid (RRF) | "Tối ưu hiệu năng ứng dụng" | 0.68 | ✅ |

> Vector search hiểu ngữ nghĩa câu nói, BM25 bị đánh lừa bởi từ "rùa".  
> Hybrid vẫn cho kết quả đúng nhờ vector search chiếm ưu thế.

**Ví dụ 3: BM25 vượt trội (Query: "Mã lỗi ECONNRESET")**

| Phương pháp | Top-1 | Score | Relevant? |
|-------------|-------|:-----:|:---------:|
| Vector-only | "Các lỗi kết nối thường gặp" | 0.65 | ❌ (chung chung) |
| **BM25-only** | **"Xử lý lỗi ECONNRESET trong ứng dụng"** | **0.88** | **✅** |
| **Hybrid (RRF)** | **"Xử lý lỗi ECONNRESET trong ứng dụng"** | **0.71** | **✅** |

> BM25 tìm chính xác nhờ keyword đặc thù "ECONNRESET".  
> Vector search chỉ hiểu được ngữ nghĩa chung chung là "lỗi kết nối".

---

## 7. Thống kê bổ sung

### 7.1 Phân bố vị trí tài liệu liên quan đầu tiên

| Phương pháp | Rank 1 | Rank 2-3 | Rank 4-5 | Rank >5 | Không tìm thấy |
|-------------|:------:|:--------:|:--------:|:-------:|:--------------:|
| Vector-only | 64.0% | 18.0% | 6.0% | 4.0% | 8.0% |
| BM25-only | 58.0% | 20.0% | 8.0% | 2.0% | 12.0% |
| **Hybrid (RRF)** | **74.0%** | **16.0%** | **6.0%** | **2.0%** | **2.0%** |

> Hybrid (RRF) tìm thấy tài liệu liên quan ở vị trí đầu tiên trong 74% trường hợp, và chỉ fail hoàn toàn 2% (1/50 queries).

### 7.2 Điểm số RRF trung bình

| Thành phần | Score trung bình (có liên quan) | Score trung bình (không liên quan) |
|------------|:------------------------------:|:---------------------------------:|
| Vector contribution | 0.473 | 0.241 |
| BM25 contribution | 0.382 | 0.198 |
| **RRF fused score** | **0.688** | **0.344** |

> Có sự phân tách rõ rệt giữa tài liệu liên quan và không liên quan (gap ~2x).

---

## 8. Tác động của tham số đến kết quả

### 8.1 Ảnh hưởng của trọng số RRF (weight_vector, weight_bm25)

| weight_vector | weight_bm25 | P@5 | R@10 | MRR |
|:-------------:|:-----------:|:---:|:----:|:---:|
| 0.0 | 1.0 | 0.436 | 0.667 | 0.654 |
| 0.2 | 0.8 | 0.504 | 0.742 | 0.723 |
| **0.5** | **0.5** | **0.556** | **0.833** | **0.798** |
| 0.8 | 0.2 | 0.528 | 0.767 | 0.761 |
| 1.0 | 0.0 | 0.472 | 0.708 | 0.712 |

> **Nhận xét:**
> - Trọng số 0.5-0.5 cho kết quả tốt nhất.
> - Vector search (weight_vector = 1.0) nhỉnh hơn BM25 (weight_bm25 = 1.0) ở mọi metric.
> - Kết hợp cả hai luôn tốt hơn dùng đơn lẻ (từ 5-15% cải thiện).

### 8.2 Ảnh hưởng của RRF constant k

| RRF k | P@5 | R@10 | MRR | Mô tả |
|:-----:|:---:|:----:|:---:|-------|
| 30 | 0.548 | 0.817 | 0.784 | Ưu tiên top rank cao hơn |
| **60** | **0.556** | **0.833** | **0.798** | Cân bằng (default) |
| 100 | 0.540 | 0.808 | 0.775 | Dàn đều kết quả hơn |
| 500 | 0.508 | 0.783 | 0.741 | Quá dàn đều, mất tác dụng |

> **Nhận xét:**
> - k = 60 cho kết quả tốt nhất.
> - k càng nhỏ → ưu tiên top rank → dễ miss tài liệu liên quan ở hạng thấp (recall giảm).
> - k càng lớn → dàn đều score → giảm độ phân biệt giữa liên quan và không liên quan.

---

## 9. Thảo luận

### 9.1 Kết luận chính

1. **Phương pháp Hybrid (RRF) với trọng số 0.5-0.5 và k = 60 cho kết quả tìm kiếm tốt nhất**, vượt trội so với vector-only và BM25-only.
2. **Cải thiện đáng kể nhất là Precision@1 (+15.6%) và Recall@10 (+17.6%)** — nghĩa là hybrid search vừa tìm đúng ngay từ kết quả đầu tiên, vừa tìm được nhiều tài liệu liên quan hơn.
3. **Vector search ngữ nghĩa (bge-m3) nhỉnh hơn BM25** trong hầu hết trường hợp, đặc biệt với query tiếng Việt có biến thể ngôn ngữ.
4. **BM25 vẫn đóng vai trò quan trọng** với các query có từ khóa đặc thù (mã lỗi, tên tính năng).
5. **Reranker pass-through chưa mang lại cải thiện** — cần cross-encoder để thực sự có ích.

### 9.2 Hạn chế của thực nghiệm này

- Test set 50 queries là chưa lớn để kết luận tổng quát.
- Ground-truth chỉ gồm tài liệu nội bộ (chưa đánh giá chất lượng web search).
- Mới chỉ dùng một embedding model (bge-m3) — chưa so sánh với các embedding model khác.
- Chưa đánh giá consistency (cùng query với cùng document có cho embedding ổn định không).

### 9.3 Hướng mở rộng

- Mở rộng test set lên 200+ queries với đa dạng thể loại.
- Thử nghiệm với cross-encoder reranker (VD: BAAI/bge-reranker-v2-m3).
- So sánh thêm với các phương pháp RAG hiện đại (ColBERT, Dense Passage Retrieval).
- Đánh giá trên multiple embedding models (multilingual-e5, gte, ...).

---

## 10. Tóm tắt

Thực nghiệm Retrieval Quality đã so sánh 4 phương pháp tìm kiếm trên 50 queries đánh giá thủ công. Kết quả cho thấy **Hybrid (RRF)** là phương pháp tốt nhất với **P@1 = 0.740, R@10 = 0.833, MRR = 0.798** — cải thiện lần lượt **+15.6%, +17.6%, +12.1%** so với vector-only (phương pháp tốt thứ hai). 

Trọng số tối ưu là **weight_vector = 0.5, weight_bm25 = 0.5** và **RRF k = 60**. Kết quả này khẳng định lợi ích của việc kết hợp vector search ngữ nghĩa và keyword search truyền thống trong bài toán RAG tiếng Việt.

---

> **📝 Ghi chú cho tác giả khóa luận:**
> - Các số liệu trong file này là **dữ liệu mẫu hợp lý** dựa trên các công bố khoa học và thực nghiệm điển hình. Bạn có thể tham khảo để viết luận trước khi có kết quả thực tế, sau đó thay bằng số liệu thật.
> - Cấu trúc và cách phân tích này có thể áp dụng cho các thực nghiệm còn lại (Answer Quality, Ablation, Latency,...).
> - Các biểu đồ `mermaid` có thể render được trên GitHub, VSCode, hoặc dùng draw.io / Excel để vẽ đẹp hơn.
