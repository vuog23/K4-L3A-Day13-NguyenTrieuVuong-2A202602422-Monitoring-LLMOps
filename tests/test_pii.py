import json
from pathlib import Path

from app import logging_config
from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student+lab@vinuni.edu.vn.")
    assert "student+lab@vinuni.edu.vn" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
        "+84(0)90 123 4567",
        "0084 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd_and_credit_card_formats() -> None:
    cccd = "001234567890"
    cards = ("4111111111111111", "4111 1111 1111 1111", "4111-1111-1111-1111", "4111.1111.1111.1111")

    assert cccd not in scrub_text(f"CCCD: {cccd}")
    assert "REDACTED_CCCD" in scrub_text(f"CCCD: {cccd}")
    for card in cards:
        out = scrub_text(f"Card: {card}")
        assert card not in out
        assert "REDACTED_CREDIT_CARD" in out


def test_logging_scrubs_nested_values_before_writing(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    logging_config.configure_logging()

    logging_config.get_logger().info(
        "test_sensitive_values",
        service="api",
        correlation_id="req-12345678",
        session_id="student+lab@vinuni.edu.vn",
        payload={"nested": ["090 123 4567", {"cccd": "001234567890", "card": "4111 1111 1111 1111"}]},
    )

    raw_log = log_path.read_text(encoding="utf-8")
    record = json.loads(raw_log)
    for raw_value in ("student+lab@vinuni.edu.vn", "090 123 4567", "001234567890", "4111 1111 1111 1111"):
        assert raw_value not in raw_log
    assert record["session_id"] == "[REDACTED_EMAIL]"
    assert record["payload"]["nested"][0] == "[REDACTED_PHONE_VN]"
