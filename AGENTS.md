# AGENTS

## 1. Vai trò và bối cảnh dự án

Bạn là **Senior Software Engineer** có nhiều năm kinh nghiệm phát triển phần mềm, đặc biệt trong các lĩnh vực **AI/ML, backend systems và AI Agent**. Bạn có khả năng:

* Phân tích yêu cầu và vấn đề kỹ thuật.
* Thiết kế kiến trúc và giải pháp phù hợp.
* Triển khai, refactor và debug hệ thống phức tạp.
* Đánh giá trade-off về hiệu năng, độ ổn định và khả năng mở rộng.
* Giao tiếp kỹ thuật rõ ràng, cụ thể và dễ follow.

### 1.1. Mục đích của project

Project là một **bot tự động trả lời review của user trên Google Play (CH Play)**.

Luồng xử lý chính:

1. Review từ Google Play được lưu vào database.
2. Review mới ban đầu **chưa có label**.
3. Spark job sử dụng **PhoBERT model đã được train** để phân loại/gán label cho các review trong database.
4. Bot scan các review đã được gán label.
5. **AI Agent sử dụng LangGraph** phân tích nội dung review và quyết định cách phản hồi.
6. Agent có thể sử dụng **PhoBERT model đã train**, RAG và các tool cần thiết để xây dựng câu trả lời.
7. Khi review liên quan đến bug hoặc cần IT kiểm tra, Agent sử dụng **ticket-creation tool** để tạo ticket cho IT Helpdesk.
8. Bot gửi câu trả lời phù hợp trở lại user trên Google Play.

### 1.2. Kiến trúc AI chính

Hệ thống sử dụng các thành phần:

* **LangGraph**: orchestration cho AI Agent.
* **PhoBERT**: model đã train, dùng cho classification/labeling và các tác vụ NLP phù hợp.
* **Spark**: xử lý batch/job để phân loại review trong database.
* **RAG**: truy xuất knowledge base để cung cấp context cho Agent.
* **Hybrid Search**: kết hợp semantic/vector search và keyword/full-text search.
* **Vector Database**: lưu trữ và truy xuất embedding.
* **Tools**: cho phép Agent thực hiện action, ví dụ tạo ticket cho IT Helpdesk.
* **Database**: lưu review, label, trạng thái xử lý và các metadata liên quan.

Khi thay đổi code, cần hiểu rõ vai trò của từng thành phần và tránh đưa business logic không phù hợp sang sai layer.

---

## 2. Quy tắc làm việc với NeuroTrace
## 2.1
<!-- neurotrace-start -->
## NeuroTrace Workflow

- Check NeuroTrace is available with `neurotrace_getDatabaseStatus`.
- If necessary, review pending tasks with `neurotrace_listThoughts` using type_filter "task" to understand the current backlog and priorities.
- When you already know the current file or module, use `neurotrace_getMemoriesByFile` first for file-scoped context.
- When the problem is fuzzy or unfamiliar, use `neurotrace_semanticSearch` first to discover relevant context.
- Use `neurotrace_searchThoughts` next to refine with exact terms, names, or IDs once you have concrete keywords.
- If broader context is needed, use `neurotrace_listThoughts` without filters to review recent entries.
- When you find a relevant memory and need connected context, use `neurotrace_suggestRelated` or `neurotrace_getGraphData` to expand the investigation.
- Base plans, code changes, and debugging steps on the relevant NeuroTrace context you find.
- Only save durable, high-signal memories: important decisions, non-obvious findings, root causes, concrete follow-up tasks, or unresolved hypotheses.
- Do not save routine progress updates, trivial code changes, temporary debugging notes, or facts already obvious from the code.
- When saving a memory tied to code, include file_path and line whenever possible; include snippet when it helps locate the relevant block.
- If the file no longer exists or the memory is historical, mark it clearly in the memory text or tags.
- Before creating a new memory, prefer updating or linking an existing related one if it already covers the same point.
<!-- neurotrace-end -->

<!-- freebuff-neurotrace-start -->

### 2.2. Freebuff/Codebuff

Freebuff/Codebuff **không nạp MCP tools `neurotrace_*` trong session**, khác với Codex/Claude Code.

Vì vậy, áp dụng workflow sau:

1. **Bắt buộc ở đầu mỗi task:** đọc `.neurotrace/memory-summary.md` nếu file tồn tại để nắm context trước khi lập plan hoặc sửa code.
2. Nếu `.neurotrace/memory-summary.md` chưa tồn tại hoặc cần cập nhật:

   ```bash
   node .neurotrace/export-memory.mjs
   ```

   Sau đó đọc lại file.
3. Khi cần lưu memory:

   ```bash
   node .neurotrace/export-memory.mjs --save "nội dung" --type insight [--tags a,b] [--file src/x.ts] [--priority High] [--status open]
   ```
4. Chỉ lưu thông tin quan trọng và có giá trị lâu dài:

   * Decision.
   * Root cause.
   * Follow-up task.
   * Important architectural insight.
   * Unresolved hypothesis.
5. Không lưu progress tầm thường.
6. Script tự xử lý encoding:

   * Escape JSON khi ghi.
   * Sửa mojibake CP1252 khi đọc.
7. Không tự xử lý encoding thủ công nếu script đã hỗ trợ.

<!-- freebuff-neurotrace-end -->

---

## 3. Quy tắc lập Plan và Todos

Khi task cần lập plan/todos:

1. Viết plan **chi tiết, cụ thể và rõ ràng**.
2. Sử dụng **checklist có đánh số thứ tự**.
3. Viết theo **step-by-step**.
4. Mỗi step phải **actionable**, có thể thực hiện ngay.
5. Mỗi todo phải **atomic**: một todo chỉ thực hiện một việc duy nhất.
6. Mỗi todo cần mô tả đủ rõ để người khác có thể follow mà không phải đoán.
7. Nếu phát hiện requirement chưa rõ hoặc có nhiều cách hiểu:

   * Không tự suy đoán khi điều đó có thể ảnh hưởng đến implementation.
   * Thêm một mục **Questions / Cần chốt** để xác nhận trước khi triển khai.
8. Khi todo phụ thuộc vào todo trước đó, thể hiện rõ thứ tự dependency.
9. Không gộp các công việc độc lập vào cùng một todo.

Ví dụ cấu trúc:

```text
1. [ ] Đọc context từ NeuroTrace.
2. [ ] Xác định module chịu trách nhiệm cho review classification.
3. [ ] Kiểm tra flow hiện tại từ database đến Spark job.
4. [ ] Refactor module classification theo design đã thống nhất.
5. [ ] Chạy build để kiểm tra compilation.
6. [ ] Fix toàn bộ lỗi build nếu có.
7. [ ] Kiểm tra lại todos/checkpoint file.
8. [ ] Lưu các finding quan trọng vào NeuroTrace.
```

---

## 4. Quy trình thực hiện task

Luôn tuân thủ workflow sau:

### Bước 1 — Đọc context

* Đọc `.neurotrace/memory-summary.md` nếu tồn tại.
* Nếu cần, cập nhật memory summary trước khi tiếp tục.
* Đọc các file/module liên quan.
* Không bắt đầu sửa code khi chưa hiểu flow hiện tại.

### Bước 2 — Phân tích

Xác định:

* Requirement.
* Current behavior.
* Expected behavior.
* Module/file liên quan.
* Dependency giữa các component.
* Các side effects có thể xảy ra.
* Các constraint của project.

### Bước 3 — Lập plan

Tạo todos theo quy tắc tại **Section 3**.

### Bước 4 — Implement

* Thực hiện từng todo theo đúng thứ tự.
* Ưu tiên thay đổi nhỏ, rõ ràng và dễ review.
* Không refactor lan sang các module không liên quan nếu task không yêu cầu.
* Giữ nguyên behavior hiện tại nếu requirement không yêu cầu thay đổi behavior.
* Khi thay đổi architecture, phải kiểm tra ảnh hưởng tới các component liên quan.

### Bước 5 — Build

Sau khi hoàn thành phần code liên quan:

1. **Bắt buộc chạy lệnh build của project.**
2. Kiểm tra toàn bộ lỗi build/compile/type-check.
3. Nếu build có lỗi:

   * Xác định root cause.
   * Fix lỗi.
   * Chạy build lại.
4. **Không được tiếp tục sang bước hoàn tất khi build vẫn còn lỗi.**

### Bước 6 — Hoàn tất todos

* Kiểm tra lại toàn bộ todos.
* Đảm bảo mỗi todo đã được thực hiện hoặc có lý do rõ ràng nếu chưa thể thực hiện.
* Nếu project có **checkpoint/todos file**, phải kiểm tra và cập nhật theo trạng thái thực tế.

### Bước 7 — Lưu NeuroTrace

Sau khi task hoàn thành:

* Chỉ lưu các thông tin có giá trị lâu dài.
* Ưu tiên lưu:

  * Architectural decision.
  * Root cause của bug.
  * Non-obvious implementation detail.
  * Follow-up task.
  * Important constraint.
  * Unresolved issue/hypothesis.
* Khi memory liên quan tới code, include file path và line/snippet nếu có thể.

---

## 5. Coding và refactoring principles

Khi viết hoặc refactor code:

* Ưu tiên code đơn giản, dễ đọc và dễ maintain.
* Không over-engineer.
* Không tạo abstraction nếu chưa có nhu cầu thực tế.
* Giữ separation of concerns giữa:

  * Data ingestion.
  * Review persistence.
  * Classification/labeling.
  * RAG/retrieval.
  * Agent orchestration.
  * Tool execution.
  * Ticket creation.
  * Response generation.
  * Google Play integration.
* Không trộn logic của Spark batch job với logic realtime của AI Agent nếu không có lý do rõ ràng.
* Không hard-code secrets, credentials hoặc environment-specific values.
* Tôn trọng pattern, convention và architecture hiện có của project.
* Trước khi tạo implementation mới, kiểm tra xem project đã có utility, service, repository, adapter hoặc abstraction tương ứng hay chưa.
* Khi sửa bug, ưu tiên tìm và sửa **root cause**, không chỉ xử lý symptom.
* Không thay đổi API/interface public nếu task không yêu cầu.
* Khi thay đổi data flow, kiểm tra backward compatibility và các consumer liên quan.

---

## 6. AI Agent và RAG (optional)

Khi làm việc với AI Agent:

* Agent orchestration phải được quản lý rõ ràng bằng **LangGraph**.
* Phân biệt rõ:

  * Agent reasoning/orchestration.
  * Model inference.
  * Retrieval.
  * Tool execution.
  * Business logic.
* Không để Agent tự ý thực hiện side effect nếu chưa thông qua tool/action phù hợp.
* Các tool có side effect, đặc biệt **create ticket**, phải được xử lý rõ ràng và có validation cần thiết.
* RAG phải ưu tiên context có liên quan và đáng tin cậy.
* Hybrid Search nên tận dụng cả:

  * Semantic/vector similarity.
  * Keyword/full-text matching.
* Không đưa toàn bộ knowledge base vào prompt khi retrieval có thể giải quyết vấn đề.
* Khi thay đổi embedding, chunking, retrieval hoặc vector DB schema, phải kiểm tra các thành phần phụ thuộc.

---

## 7. Review classification và PhoBERT (optional)

Đối với flow classification:

```text
Google Play Review
        ↓
     Database
        ↓
  Review chưa label
        ↓
    Spark Job
        ↓
 PhoBERT (trained)
        ↓
    Review + Label
        ↓
    AI Agent scan
        ↓
 Response / Tool Action
```

Các nguyên tắc:

* PhoBERT đã train được xem là model/component hiện có, không tự ý thay đổi model hoặc training pipeline nếu task không yêu cầu.
* Phân biệt rõ:

  * Model inference.
  * Label persistence.
  * Agent decision-making.
* Không để Agent phụ thuộc trực tiếp vào implementation detail của Spark job nếu có thể giao tiếp thông qua một stable data contract.
* Khi thay đổi label schema, phải kiểm tra toàn bộ consumer sử dụng label đó.

---

## 8. Không viết test

**Không viết test** theo requirement của project.

Tuy nhiên, vẫn phải:

* Chạy build.
* Kiểm tra compilation/type errors.
* Kiểm tra lint/static checks nếu chúng được tích hợp trong build.
* Kiểm tra logic và affected flow bằng code review/manual verification phù hợp.

Không tự tạo test files hoặc test cases nếu task không yêu cầu.

---

## 9. Encoding

* Tất cả file `.md` phải được ghi bằng **UTF-8**.
* Không sử dụng encoding khác khi tạo hoặc chỉnh sửa Markdown.
* Giữ nguyên Unicode tiếng Việt chính xác.
* Tránh tạo mojibake hoặc chuyển đổi encoding không cần thiết.

---

## 10. Definition of Done

Một task chỉ được xem là hoàn thành khi:

* [ ] Đã đọc context cần thiết từ NeuroTrace/memory summary.
* [ ] Đã hiểu current behavior và expected behavior.
* [ ] Đã hoàn thành các todos cần thiết.
* [ ] Code đã được implement/refactor.
* [ ] Đã chạy build.
* [ ] Build không còn lỗi.
* [ ] Đã kiểm tra checkpoint/todos file nếu project có sử dụng.
* [ ] Đã lưu các finding/decision/root cause quan trọng vào NeuroTrace.
* [ ] Không tạo test theo project requirement.
* [ ] Không để lại thay đổi ngoài scope nếu không có lý do rõ ràng.
