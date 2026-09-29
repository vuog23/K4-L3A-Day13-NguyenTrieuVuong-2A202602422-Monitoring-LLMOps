# Alert và runbook CP2

Các alert dùng triệu chứng quan sát được từ `data/logs.jsonl`, với nguồn và công thức trong `config/dashboard.yaml`. Kênh đích là Slack `#llmops-alerts`; cấu hình này mô tả nơi thông báo, chưa tự gửi thông báo ra Slack.

## Alert 1

- **Tên:** `high_tail_latency`
- **Severity:** warning
- **Duration:** P95 latency > 1.000 ms trong 5 phút liên tiếp, với ít nhất 20 request/5 phút.
- **Kênh thông báo:** Slack `#llmops-alerts`
- **Owner:** `student-2A202602422`
- **SLI/SLO liên quan:** P95 latency và SLO `fast_successful_requests` (request thành công trong 3.000 ms).
- **Ảnh hưởng tới người dùng:** phản hồi chậm dù API vẫn trả HTTP 200.
- **Ba bước kiểm tra đầu tiên:** (1) Xác định phút P95 tăng trên panel latency và so với traffic. (2) Lọc `response_sent` có `latency_ms > 1000`, lấy `correlation_id`. (3) Mở trace cùng ID, so thời lượng `retrieve-context` và `fake-llm-generate`.
- **Mitigation tạm thời:** giảm đồng thời hoặc dùng fallback retrieval nếu child retriever chậm; giới hạn độ dài generation nếu child generation chậm. Xác nhận P95 hồi phục bằng workload cùng input.

## Alert 2

- **Tên:** `elevated_errors_or_retrieval_failures`
- **Severity:** critical
- **Duration:** error rate > 2% hoặc retrieval success < 90% trong 5 phút liên tiếp, với ít nhất 20 request/5 phút.
- **Kênh thông báo:** Slack `#llmops-alerts`
- **Owner:** `student-2A202602422`
- **SLI/SLO liên quan:** error rate, retrieval success và tỷ lệ request thành công của SLO.
- **Ảnh hưởng tới người dùng:** request lỗi hoặc không lấy được context cần thiết.
- **Ba bước kiểm tra đầu tiên:** (1) Xem panel errors để xác định error rate, breakdown và retrieval success. (2) Lọc `request_failed` theo `error_type`, lấy `correlation_id`. (3) Mở trace để tìm child retriever lỗi và đối chiếu thời điểm với log.
- **Mitigation tạm thời:** khôi phục dependency retrieval hoặc chuyển sang câu trả lời fallback an toàn; tắt incident practice nếu đang bật. Chạy lại workload và xác nhận tỷ lệ lỗi giảm.

## Alert 3

- **Tên:** `unexpected_llm_spend`
- **Severity:** warning
- **Duration:** cost > 0,05 USD/10 phút trong 10 phút liên tiếp, với ít nhất 20 request/10 phút.
- **Kênh thông báo:** Slack `#llmops-alerts`
- **Owner:** `student-2A202602422`
- **SLI/SLO liên quan:** cost guardrail 2,5 USD/ngày và output tokens.
- **Ảnh hưởng tới người dùng:** ngân sách bị tiêu nhanh; có thể kèm câu trả lời dài bất thường.
- **Ba bước kiểm tra đầu tiên:** (1) So panel cost và tokens với traffic để tách tăng tải khỏi tăng cost/request. (2) Lọc `response_sent` có `tokens_out` và `cost_usd` cao, lấy `correlation_id`. (3) Mở generation observation của trace, kiểm tra model, prompt version, usage và cost.
- **Mitigation tạm thời:** giới hạn output tokens, giảm concurrency hoặc rollback prompt `production` nếu phiên bản mới làm câu trả lời dài hơn. Chạy lại workload và kiểm tra cost/request.
