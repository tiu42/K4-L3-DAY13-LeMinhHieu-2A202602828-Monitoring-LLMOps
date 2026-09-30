# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Lê Minh Hiếu
- **MSSV:** 2A202602828
- **Lớp:** K4-L3B
- **Repository URL:**
- **Commit SHA cuối:**
- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-2A202602828`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (23 records; 20 thiếu required fields, 20 thiếu enrichment, 0 correlation ID) | | Baseline chỉ pass PII scrubbing |
| `validate_dashboard.py` | 6/6 panel hợp lệ | | |
| `pytest` | 22 passed | | |
| Số traces hợp lệ | 10 (1 trace/request từ `load_test.py`, `tracing_enabled: true`) | | Chưa nối được trace với log vì log chưa có `correlation_id` |
| Số PII leak | 0 | | |
| Latency P95 / TTFT P95 | 3522 ms / 50 ms | | Tính từ 10 event `response_sent` trong `data/logs.jsonl` |
| Retrieval success rate | 100% (10/10) | | |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:**
- **Các metadata được ghi vào structured log:**
- **Cách bảo đảm PII được scrub trước khi ghi:**
- **Cách kiểm chứng kết quả:**

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Trace nằm trong project `day13-k4-l3b-2A202602828` (API key của project này trong `.env`), trace name `day13-agent-request`, metadata `correlation_id` khớp với `x-request-id` và log trong `data/logs.jsonl`. Đối chiếu qua Observations API: 101 trace đủ cây (113 trace / 118 request trong log; vài trace bị mất do mạng/DNS chập chờn khi export).
- **Cấu trúc root/retrieval/generation observations:** `day13-agent-request` → `lab-agent-run` (agent) → `retrieval` (retriever, metadata `doc_count`, `matched_key`) và `generation` (generation: model `claude-sonnet-4-5`, `usage_details` input/output, `cost_details` input/output/total, `completion_start_time` cho TTFT, link prompt `day13-chat`). Dùng `@observe(..., capture_input=False, capture_output=False)` nên không gửi câu hỏi/câu trả lời thô (có thể chứa PII).
- **Cách nối trace với log:** Middleware sinh/nhận `x-request-id` (`req-<8 hex>`), bind vào structlog contextvars và truyền vào `agent.run()`; `propagate_attributes(metadata={"correlation_id": ...})` gắn cùng ID lên mọi observation. Lấy `correlation_id` từ log → lọc trace theo metadata đó trên Langfuse.
- **Prompt name:** `day13-chat` (text prompt, 3 biến `{{feature}}`, `{{docs}}`, `{{message}}`)
- **Version/label baseline:** v1, labels `baseline` + `production`
- **Version/label candidate:** v2 (thêm dòng `Instruction=Trả lời ngắn gọn, tối đa 3 câu.`), label `candidate` (+ `latest` tự gắn)
- **Trace ID của mỗi version:** v1/baseline: `7745002edc3cde59206bda1b0b3a851b` (`req-44fa59bb`, tokens_in 45); v2/candidate: `c0b545a91116bc5fe75dcceee632d3b7` (`req-f10ddef1`, tokens_in 56). Metadata của `lab-agent-run` ghi đúng `prompt_name`, `prompt_label`, `prompt_version`, `prompt_source=langfuse`.
- **Cách promote và rollback `production`:** App chỉ hỏi Langfuse theo `LANGFUSE_PROMPT_NAME` + `LANGFUSE_PROMPT_LABEL=production`, nên không sửa code. Promote: dời label `production` sang v2 → request kiểm tra `req-75073b03` dùng v2 (tokens_in 56). Rollback: dời `production` về v1 → request kiểm tra `req-8411f077` dùng v1 (tokens_in 45). Prompt cache 60 s nên sau mỗi lần đổi label phải restart API hoặc chờ hết cache mới kiểm tra.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** `dashboard/app.py` (Streamlit + Plotly, venv riêng `.venv-dashboard`, cài theo `dashboard/requirements.txt`), đọc `data/logs.jsonl` và lấy tên panel/đơn vị/threshold trực tiếp từ `config/dashboard.yaml`. Time range 60 phút (UTC), auto refresh 30 s, mỗi panel có đường threshold. Sáu panel: Latency P50/P95/P99 + TTFT P95 (≤ 3000 ms), Traffic req/phút (≥ 1), Error rate % + breakdown `error_type` + retrieval success (≤ 2 %), Cost theo phút + cumulative (≤ 2.5 USD), Tokens in/out (≤ 50,000), Quality mean (≥ 0.75). Retrieval success tính trên mọi event có `tool_success`.
- **SLO và lý do chọn:** `fast_successful_requests`: `response_sent` với `latency_ms ≤ 3000` / `request_received`, target 99.5 % trong 28 ngày. Baseline bình thường ~400 ms, TTFT P95 50 ms → 3000 ms cho headroom ~7x. Tuy vậy dashboard cho thấy P95 ~6 s dù P50 chỉ 155 ms: phần chậm không nằm ở `retrieval`/`generation` (~0.15 s trong trace) mà ở bước fetch prompt từ Langfuse nằm trong request path (đo được 250–1500 ms khi không cache, lâu hơn khi DNS lỗi). Giữ ngưỡng và xử lý bằng warm-up/cache thay vì nới SLO.
- **Cách tính error budget:** `allowed_bad = total × (100 − 99.5) / 100`. 10,000 request / 28 ngày → tối đa 50 request lỗi hoặc > 3000 ms. Ở quy mô lab ~100 request thì budget chỉ 0.5 request, nên một request cold start cũng đủ breach.
- **Ba alert và runbook tương ứng:** (`config/alert_rules.yaml`, runbook trong `docs/alerts.md`, Slack `#k4-l3b-alerts`, owner `student-2A202602828`)
  1. `HighLatencyP95` (warning, 5m): `p95(latency_ms) > 3000` → [Alert 1](../docs/alerts.md#alert-1)
  2. `HighErrorRate` (critical, 5m): error rate > 2 % hoặc retrieval success < 90 % → [Alert 2](../docs/alerts.md#alert-2)
  3. `CostPerRequestSpike` (warning, 10m): avg cost > 0.004 USD/request (~2x baseline) hoặc > 0.104 USD/giờ → [Alert 3](../docs/alerts.md#alert-3)

> Ví dụ cách viết error budget: "SLO 99.5% trong 28 ngày nghĩa là error budget 0.5%. Nếu workload có 10,000 request thì tối đa 50 request được phép lỗi hoặc chậm hơn ngưỡng SLO."

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1` (cohort K4)
- **Khoảng thời gian điều tra:** 2026-09-30, UTC. Baseline 04:46:37–04:46:41 (10 request, chưa bật incident); incident 04:47:59 (`incident_enabled`, `correlation_id=req-f6cd8803`) → 04:48:14 (5 request challenge, `--concurrency 5`); khôi phục 04:49:52–04:49:54.
- **Triệu chứng từ metrics:** Panel **Latency** bất thường: `latency_ms` P50 tăng từ **153 ms → 2655 ms** (~17x), P95 **2665 ms**, cả 5/5 request vượt ngưỡng 2000 ms của challenge (và vượt xa baseline). Trong khi đó **TTFT P95 giữ nguyên 50 ms**, **error rate 0 %**, **retrieval success 100 %** (5/5 `tool_success=true`), cost (~0.0022 USD/request) và tokens (~35 in / ~145 out) không đổi, quality 0.84 (vẫn ≥ 0.75). → Request chậm nhưng không lỗi, và phần chậm nằm ngoài bước sinh token. Traffic lúc đó chỉ có feature `monitoring`. (Thời gian 10–13 s mà `load_test.py` in ra là số phía client do request xếp hàng, không dùng để kết luận.)
- **Log line và correlation ID liên quan:** Lọc `data/logs.jsonl` event `response_sent` trong 04:48:00–04:48:14: cả 5 request `feature=monitoring` đều có `latency_ms` 2654–2665. Log đại diện:
  `{"event": "response_sent", "correlation_id": "req-918a1f69", "feature": "monitoring", "session_id": "k4-l3b-challenge-s01", "latency_ms": 2655, "ttft_ms": 50, "tool_name": "retrieval", "tool_success": true, "tokens_in": 35, "tokens_out": 125, "cost_usd": 0.00198, "ts": "2026-09-30T04:48:08.738132Z"}`
  Các `response_sent` kết thúc cách nhau đều ~2.67 s → server xử lý tuần tự nên độ trễ phía client cộng dồn.
- **Trace ID và span gây ảnh hưởng:** Trace `62eff1a0c8f82dc02b2e4240156c449d` (metadata `correlation_id=req-918a1f69`): `lab-agent-run` 2657 ms = **`retrieval` 2504 ms** + `generation` 153 ms; mọi span level `DEFAULT`, không có lỗi. So với trace baseline `1926bf12c55c318c3b111feab8decf81` (`req-dfca5606`): `retrieval` **3 ms**, `generation` 152 ms. → `generation` không đổi, chỉ `retrieval` tăng ~2.5 s.
- **Root cause:** Bước retrieval (RAG/vector store lookup) bị chậm thêm ~2.5 s mỗi request (incident `rag_slow` đang bật). Ba bằng chứng cùng chỉ về một chỗ: metric latency tăng nhưng TTFT/cost/token/error không đổi → log cho thấy mọi request trong cửa sổ đều ~2655 ms với `tool_success=true` → trace cho thấy 94 % thời gian (2504/2657 ms) nằm trong span `retrieval`.
- **Fix action:** Khôi phục retrieval bằng cách tắt incident (`python scripts/inject_incident.py --disable`, `/health` → mọi incident `false`), rồi chạy lại đúng workload challenge: 5 request `monitoring` (`req-2e98a8ca`, `req-44681292`, `req-637e8b0d`, `req-9c836bfb`, `req-d7d47b5f`) có `latency_ms` = **152–153 ms**, về lại baseline.
- **Preventive measure:**
  1. Alert `HighLatencyP95` (Alert 1) đã có; bổ sung alert theo span: `p95(retrieval duration) > 500 ms` trong 5 phút để phát hiện trực tiếp dependency retrieval chậm trước khi SLO latency bị breach, runbook trỏ tới bước so sánh `retrieval` vs `generation` trong trace.
  2. Guardrail trong code: đặt timeout cho retrieval (vd 1 s) và fallback (context cache/"no document matched") để một dependency chậm không kéo toàn bộ request vượt 2000 ms.
  3. `/chat` là `async def` nhưng gọi `agent.run()` đồng bộ nên chặn event loop: 5 request đồng thời bị xử lý tuần tự (client thấy 10–13 s). Chuyển sang `run_in_threadpool`/async để một request chậm không làm chậm các request khác.
  4. Thêm test/ load test có kiểm tra latency theo feature trước khi deploy thay đổi liên quan tới retrieval.

> Gợi ý cách viết ngắn, không thay cho evidence thực tế: "Metric cho thấy `[latency/error/cost/quality]` bất thường trong `[khoảng thời gian]`. Log line `[event]` có `correlation_id=[...]` đại diện cho request bị ảnh hưởng. Trace cùng `correlation_id` cho thấy span `[retrieval/generation/prompt/tool]` có dấu hiệu `[chậm/lỗi/token tăng]`. Root cause là `[nguyên nhân suy ra từ evidence]`. Fix action là `[hành động khôi phục]`; preventive measure là `[alert/runbook/test/guardrail để ngăn tái diễn]`."

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
- **Một lỗi/blocker đã gặp:**
- **Cách tìm nguyên nhân và xử lý:**
- **Cách hiểu luồng Metrics → Logs → Traces:**
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
- **Điều quan trọng nhất đã học:**
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
