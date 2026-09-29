from __future__ import annotations

import json
import asyncio
import re
from pathlib import Path

import httpx

from app import logging_config
from app.main import app
from app.pii import hash_user_id


def test_chat_response_log_exposes_quality_for_dashboard(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": "Explain observability",
                },
            )

    response = asyncio.run(send_request())

    assert response.status_code == 200
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    response_event = next(event for event in events if event["event"] == "response_sent")
    assert response_event["quality_score"] == response.json()["quality_score"]
    assert response_event["ttft_ms"] == response.json()["ttft_ms"]
    assert response_event["tool_name"] == "retrieval"
    assert response_event["tool_success"] is True


def test_chat_correlation_headers_and_request_context(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_requests() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                "/chat",
                headers={"x-request-id": "req-ABCDEF12"},
                json={"user_id": "student-01", "session_id": "session-01", "feature": "qa", "message": "Explain observability"},
            )
            second = await client.post(
                "/chat",
                headers={"x-request-id": "invalid"},
                json={"user_id": "student-02", "session_id": "session-02", "feature": "summary", "message": "Summarize logging"},
            )
            return first, second

    first, second = asyncio.run(send_requests())
    assert first.status_code == second.status_code == 200
    assert first.headers["x-request-id"] == first.json()["correlation_id"] == "req-ABCDEF12"
    assert re.fullmatch(r"req-[0-9a-f]{8}", second.headers["x-request-id"])
    assert second.headers["x-request-id"] == second.json()["correlation_id"]
    assert float(first.headers["x-response-time-ms"]) >= 0
    assert float(second.headers["x-response-time-ms"]) >= 0

    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    received = [record for record in records if record["event"] == "request_received"]
    assert len(received) == 2
    for record, response, user_id, session_id, feature in zip(
        received,
        (first, second),
        ("student-01", "student-02"),
        ("session-01", "session-02"),
        ("qa", "summary"),
    ):
        assert record["correlation_id"] == response.headers["x-request-id"]
        assert record["user_id_hash"] == hash_user_id(user_id)
        assert record["session_id"] == session_id
        assert record["feature"] == feature
        assert record["model"] == "claude-sonnet-4-5"
        assert record["env"] == "dev"
