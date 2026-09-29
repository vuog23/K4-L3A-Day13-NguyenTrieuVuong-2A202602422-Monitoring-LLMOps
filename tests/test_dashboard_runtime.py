from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.dashboard import build_snapshot


def test_dashboard_aggregates_log_events_in_the_last_hour(tmp_path: Path) -> None:
    now = datetime(2026, 9, 29, 12, 0, 30, tzinfo=timezone.utc)
    recent = now - timedelta(seconds=20)
    prior = now - timedelta(minutes=1, seconds=20)
    stale = now - timedelta(hours=2)
    records = [
        {"ts": prior.isoformat(), "event": "request_received"},
        {"ts": prior.isoformat(), "event": "response_sent", "latency_ms": 100, "ttft_ms": 30, "tokens_in": 20, "tokens_out": 100, "cost_usd": 0.001, "quality_score": 0.8, "tool_success": True},
        {"ts": recent.isoformat(), "event": "request_received"},
        {"ts": recent.isoformat(), "event": "request_failed", "error_type": "RuntimeError", "tool_success": False},
        {"ts": stale.isoformat(), "event": "request_received"},
    ]
    log_path = tmp_path / "logs.jsonl"
    log_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

    snapshot = build_snapshot(log_path, now=now)
    panels = {panel["id"]: panel for panel in snapshot["panels"]}

    assert len(panels) == 6
    assert snapshot["time_range_minutes"] == 60
    assert snapshot["refresh_seconds"] == 30
    assert panels["latency"]["metrics"] == {"p50": 100.0, "p95": 100.0, "p99": 100.0, "ttft_p95": 30.0}
    assert panels["traffic"]["metrics"]["count"] == 2
    assert panels["errors"]["metrics"] == {"error_rate_pct": 50.0, "error_breakdown": {"RuntimeError": 1}, "tool_success_rate_pct": 50.0}
    assert panels["cost"]["metrics"]["total"] == 0.001
    assert panels["tokens"]["metrics"] == {"tokens_in": 20, "tokens_out": 100}
    assert panels["quality"]["metrics"]["mean"] == 0.8
    assert snapshot["slo"]["good_requests"] == 1
    assert snapshot["slo"]["bad_requests"] == 1


def test_dashboard_handles_missing_log_file(tmp_path: Path) -> None:
    snapshot = build_snapshot(tmp_path / "missing.jsonl")
    assert len(snapshot["panels"]) == 6
    assert snapshot["slo"]["total_requests"] == 0
