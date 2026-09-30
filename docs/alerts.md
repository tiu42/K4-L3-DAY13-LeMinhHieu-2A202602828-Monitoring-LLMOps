# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-<MSSV>`

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: SLO `fast_successful_requests` (`response_sent.latency_ms <= 3000`, 99.5% trong 28 ngày); panel **Latency percentiles and TTFT**
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` liên tục 5 phút (baseline bình thường ~400 ms, TTFT P95 50 ms)
- Ảnh hưởng tới người dùng: người dùng chờ lâu trước khi nhận câu trả lời; mỗi request > 3000 ms tiêu error budget (0.5%)
- Ba bước kiểm tra đầu tiên:
  1. **Metrics:** mở dashboard, xác nhận P95/P99 tăng từ lúc nào; so TTFT P95 với latency P95: TTFT vẫn ~50 ms mà latency tăng → chậm nằm trước/ngoài bước sinh token (retrieval, fetch prompt); TTFT cũng tăng → chậm ở generation.
  2. **Logs:** lọc `data/logs.jsonl` trong khoảng đó, `event == "response_sent"` và `latency_ms > 3000`; lấy vài `correlation_id`, kiểm tra chúng có chung `feature`, `model` hay chỉ là request đầu tiên sau `app_started` (cold start).
  3. **Traces:** trên Langfuse lọc trace có metadata `correlation_id` đó, mở waterfall `lab-agent-run` và so thời lượng `retrieval` với `generation` để xác định span chiếm phần lớn thời gian.
- Mitigation tạm thời: nếu chậm ở retrieval → khôi phục cấu hình/nguồn retrieval hoặc tắt nguồn gây chậm; nếu chỉ do cold start → warm-up API sau deploy; nếu chậm ở generation sau khi đổi prompt → rollback label `production` về version trước. Giảm tải nếu đang demo.
- Owner: `student-2A202602828`

## Alert 2

- Tên: `HighErrorRate`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: SLO `fast_successful_requests` (request lỗi là bad event) và guardrails `error_rate_pct_max: 2`, `retrieval_success_rate_pct_min: 90`; panel **Error rate and retrieval success**
- Điều kiện và thời gian duy trì: `count(request_failed) / count(request_received) * 100 > 2%` **hoặc** retrieval success `< 90%` liên tục 5 phút
- Ảnh hưởng tới người dùng: người dùng nhận HTTP 500 thay vì câu trả lời; error budget 0.5% cạn rất nhanh (với 10,000 request chỉ cho phép 50 request hỏng)
- Ba bước kiểm tra đầu tiên:
  1. **Metrics:** xác nhận error rate và retrieval success trên dashboard, xem breakdown theo `error_type` để biết lỗi tập trung vào một loại hay rải rác.
  2. **Logs:** lọc `event == "request_failed"`, đọc `error_type`, `tool_name`, `tool_success` và `payload.detail`; lấy `correlation_id` của một request lỗi tiêu biểu.
  3. **Traces:** mở trace cùng `correlation_id`, tìm observation có level `ERROR` (thường là `retrieval` nếu `tool_success=false`), đọc status message để xác định dependency nào lỗi.
- Mitigation tạm thời: khôi phục dependency/cấu hình bị lỗi (vector store, tool), tắt thay đổi vừa deploy; nếu lỗi xuất hiện sau khi đổi prompt thì rollback label `production`. Thông báo trên Slack channel khi error rate về dưới 2%.
- Owner: `student-2A202602828`

## Alert 3

- Tên: `CostPerRequestSpike`
- Severity: `warning`
- Duration: `10m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5` (≈ 0.104 USD/giờ); baseline chi phí trung bình ~0.0019 USD/request; panel **Cost over time** và **Input and output tokens**
- Điều kiện và thời gian duy trì: `avg(cost_usd) > 0.004 USD/request` (gấp ~2 lần baseline) **hoặc** `sum(cost_usd)` trong 1 giờ `> 0.104 USD`, liên tục 10 phút
- Ảnh hưởng tới người dùng: người dùng có thể nhận câu trả lời dài dòng hơn; với vận hành, ngân sách LLM trong ngày bị đốt nhanh và có thể phải chặn traffic
- Ba bước kiểm tra đầu tiên:
  1. **Metrics:** so panel Cost với panel Tokens: `tokens_out` tăng → câu trả lời dài hơn; `tokens_in` tăng → prompt/context dài hơn; chỉ traffic tăng mà cost/request không đổi → không phải spike bất thường.
  2. **Logs:** lọc `response_sent` có `cost_usd` hoặc `tokens_out` cao, lấy `correlation_id`, kiểm tra có tập trung ở một `feature`/`model` không.
  3. **Traces:** mở trace đó, xem observation `generation` (usage, cost, `promptName`/`promptVersion`) và metadata `prompt_label`/`prompt_version` của `lab-agent-run` để biết prompt version nào đang chạy.
- Mitigation tạm thời: nếu cost tăng sau khi promote prompt → rollback label `production` về version trước; giới hạn `max_tokens`/độ dài output; tạm giảm traffic không quan trọng cho tới khi cost về baseline.
- Owner: `student-2A202602828`
