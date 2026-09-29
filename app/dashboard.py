from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "dashboard.yaml"
SLO_PATH = ROOT / "config" / "slo.yaml"


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentile / 100) - 1)
    return round(ordered[index], 3)


def _number(record: dict[str, Any], field: str) -> float | None:
    value = record.get(field)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _read_window(log_path: Path, start: datetime, end: datetime) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    records = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
            timestamp = datetime.fromisoformat(record["ts"].replace("Z", "+00:00"))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
        if timestamp.tzinfo is None:
            continue
        timestamp = timestamp.astimezone(timezone.utc)
        if start <= timestamp < end:
            record["_minute"] = timestamp.replace(second=0, microsecond=0)
            records.append(record)
    return records


def build_snapshot(
    log_path: Path | None = None, *, now: datetime | None = None
) -> dict[str, Any]:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["dashboard"]
    slo = yaml.safe_load(SLO_PATH.read_text(encoding="utf-8"))["primary_slo"]
    if now is None:
        now = datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc)
    minutes = config["time_range_minutes"]
    first_minute = now.replace(second=0, microsecond=0) - timedelta(minutes=minutes - 1)
    minute_points = [first_minute + timedelta(minutes=i) for i in range(minutes)]
    records = _read_window(log_path or ROOT / "data" / "logs.jsonl", first_minute, now)
    requests = [record for record in records if record.get("event") == "request_received"]
    responses = [record for record in records if record.get("event") == "response_sent"]
    failures = [record for record in records if record.get("event") == "request_failed"]

    by_minute: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_minute[record["_minute"]].append(record)

    def minute_records(minute: datetime, event: str) -> list[dict[str, Any]]:
        return [record for record in by_minute[minute] if record.get("event") == event]

    def values(source: list[dict[str, Any]], field: str) -> list[float]:
        return [value for record in source if (value := _number(record, field)) is not None]

    latencies = values(responses, "latency_ms")
    ttfts = values(responses, "ttft_ms")
    cost_values = values(responses, "cost_usd")
    quality_values = values(responses, "quality_score")
    known_tools = [record for record in records if isinstance(record.get("tool_success"), bool)]
    successful_tools = sum(record["tool_success"] for record in known_tools)
    request_count = len(requests)
    failure_count = len(failures)
    latency_threshold = float(slo["latency_threshold_ms"])
    good_count = sum(
        latency is not None and latency <= latency_threshold
        for record in responses
        if (latency := _number(record, "latency_ms")) is not None
    )
    target = float(slo["target_percent"])
    budget = request_count * (100 - target) / 100

    metrics: dict[str, dict[str, Any]] = {
        "latency": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
            "ttft_p95": _percentile(ttfts, 95),
        },
        "traffic": {
            "count": request_count,
            "rate_per_minute": len(minute_records(minute_points[-1], "request_received")),
        },
        "errors": {
            "error_rate_pct": round(failure_count / request_count * 100, 2) if request_count else None,
            "error_breakdown": dict(Counter(record.get("error_type") or "unknown" for record in failures)),
            "tool_success_rate_pct": round(successful_tools / len(known_tools) * 100, 2) if known_tools else None,
        },
        "cost": {"total": round(sum(cost_values), 6)},
        "tokens": {
            "tokens_in": int(sum(values(responses, "tokens_in"))),
            "tokens_out": int(sum(values(responses, "tokens_out"))),
        },
        "quality": {"mean": round(mean(quality_values), 3) if quality_values else None},
    }

    series: dict[str, dict[str, list[float | None]]] = {
        "latency": {
            "p95": [_percentile(values(minute_records(minute, "response_sent"), "latency_ms"), 95) for minute in minute_points],
            "ttft_p95": [_percentile(values(minute_records(minute, "response_sent"), "ttft_ms"), 95) for minute in minute_points],
        },
        "traffic": {
            "rate_per_minute": [len(minute_records(minute, "request_received")) for minute in minute_points],
        },
        "errors": {
            "error_rate_pct": [
                round(len(minute_records(minute, "request_failed")) / count * 100, 2) if (count := len(minute_records(minute, "request_received"))) else None
                for minute in minute_points
            ],
            "tool_success_rate_pct": [
                round(sum(record["tool_success"] for record in known) / len(known) * 100, 2) if (known := [record for record in by_minute[minute] if isinstance(record.get("tool_success"), bool)]) else None
                for minute in minute_points
            ],
        },
        "cost": {
            "sum_by_minute": [round(sum(values(minute_records(minute, "response_sent"), "cost_usd")), 6) for minute in minute_points],
        },
        "tokens": {
            "tokens_in": [sum(values(minute_records(minute, "response_sent"), "tokens_in")) for minute in minute_points],
            "tokens_out": [sum(values(minute_records(minute, "response_sent"), "tokens_out")) for minute in minute_points],
        },
        "quality": {
            "mean": [round(mean(items), 3) if (items := values(minute_records(minute, "response_sent"), "quality_score")) else None for minute in minute_points],
        },
    }

    return {
        "title": config["title"],
        "generated_at": now.isoformat(),
        "window_start": first_minute.isoformat(),
        "time_range_minutes": minutes,
        "refresh_seconds": config["refresh_seconds"],
        "minutes": [point.strftime("%H:%M") for point in minute_points],
        "panels": [
            {
                "id": panel["id"],
                "title": panel["title"],
                "unit": panel["unit"],
                "threshold": panel["threshold"],
                "metrics": metrics[panel["id"]],
                "series": series[panel["id"]],
            }
            for panel in config["panels"]
        ],
        "slo": {
            "name": slo["name"],
            "target_percent": target,
            "latency_threshold_ms": latency_threshold,
            "actual_percent": round(good_count / request_count * 100, 2) if request_count else None,
            "total_requests": request_count,
            "good_requests": good_count,
            "bad_requests": request_count - good_count,
            "error_budget_requests": round(budget, 3),
            "remaining_budget_requests": round(budget - (request_count - good_count), 3),
        },
    }
