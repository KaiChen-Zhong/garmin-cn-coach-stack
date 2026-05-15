"""Cached Garmin metrics for faster coaching analysis."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except Exception:
        return None


def _activity_load(activity: dict[str, Any]) -> float:
    explicit = activity.get("activityTrainingLoad") or activity.get("trainingLoad")
    if isinstance(explicit, (int, float)) and explicit > 0:
        return float(explicit)
    minutes = float(activity.get("duration") or activity.get("movingDuration") or 0) / 60.0
    avg_hr = float(activity.get("averageHR") or 0)
    calories = float(activity.get("calories") or 0)
    if avg_hr:
        return minutes * (avg_hr / 100.0)
    if calories:
        return calories / 5.0
    return minutes


def _activity_type(activity: dict[str, Any]) -> str:
    sport = activity.get("activityType") or {}
    return str(sport.get("typeKey") or activity.get("activityTypeKey") or "unknown")


def _ensure_day(days: dict[str, dict[str, Any]], day: str) -> dict[str, Any]:
    return days.setdefault(day, {
        "date": day,
        "activities": {"count": 0, "distance_km": 0.0, "duration_min": 0.0, "load": 0.0, "by_type": {}},
        "health": {},
        "advanced": {},
    })


def _extract_body_battery(payload: dict[str, Any]) -> int | float | None:
    body_battery = payload.get("body_battery") or []
    if body_battery and isinstance(body_battery, list) and isinstance(body_battery[0], dict):
        arr = body_battery[0].get("bodyBatteryValuesArray") or []
        if arr:
            return arr[-1][1]
        return body_battery[0].get("charged")
    return None


def _extract_daily_health(payload: dict[str, Any]) -> dict[str, Any]:
    sleep = payload.get("sleep") or {}
    hr = payload.get("heart_rate") or {}
    hrv = payload.get("hrv") or {}
    hrv_summary = hrv.get("hrvSummary") or {}
    steps = payload.get("steps") or {}
    return {
        "sleep_hours": round(float(sleep.get("sleepTimeSeconds") or 0) / 3600.0, 2) if sleep else None,
        "sleep_score_feedback": sleep.get("sleepScoreFeedback"),
        "resting_hr": hr.get("restingHeartRate"),
        "resting_hr_7d": hr.get("lastSevenDaysAvgRestingHeartRate"),
        "hrv_status": hrv_summary.get("status"),
        "hrv_last": hrv_summary.get("lastNightAvg"),
        "hrv_weekly": hrv_summary.get("weeklyAvg"),
        "body_battery": _extract_body_battery(payload),
        "steps": steps.get("totalSteps") or steps.get("total_steps") if isinstance(steps, dict) else None,
    }


def _extract_advanced(payload: dict[str, Any]) -> dict[str, Any]:
    training_status = payload.get("training_status") or {}
    vo2 = ((training_status.get("mostRecentVO2Max") or {}).get("generic") or {}).get("vo2MaxValue")
    readiness = payload.get("training_readiness") or payload.get("morning_training_readiness") or {}
    return {
        "vo2max": vo2,
        "training_status": training_status.get("trainingStatus"),
        "training_readiness": readiness.get("score") or readiness.get("overallScore"),
    }


def _round_activity(day: dict[str, Any]) -> None:
    acts = day["activities"]
    for key in ("distance_km", "duration_min", "load"):
        acts[key] = round(float(acts[key]), 1)
    for item in acts["by_type"].values():
        for key in ("distance_km", "duration_min", "load"):
            item[key] = round(float(item[key]), 1)


def build_metric_cache(data_dir: str = "./data", target: str | None = None) -> dict[str, Any]:
    root = Path(data_dir)
    target_day = _as_date(target) or date.today()
    days: dict[str, dict[str, Any]] = {}

    for path in (root / "activities").glob("*.json"):
        payload = _load_json(path)
        if not isinstance(payload, list):
            continue
        for activity in payload:
            if not isinstance(activity, dict):
                continue
            day = _as_date(activity.get("startTimeLocal") or activity.get("startTimeGMT"))
            if not day:
                continue
            slot = _ensure_day(days, day.isoformat())
            acts = slot["activities"]
            distance = float(activity.get("distance") or 0) / 1000.0
            duration = float(activity.get("duration") or activity.get("movingDuration") or 0) / 60.0
            load = _activity_load(activity)
            acts["count"] += 1
            acts["distance_km"] += distance
            acts["duration_min"] += duration
            acts["load"] += load
            type_key = _activity_type(activity)
            by_type = acts["by_type"].setdefault(type_key, {"count": 0, "distance_km": 0.0, "duration_min": 0.0, "load": 0.0})
            by_type["count"] += 1
            by_type["distance_km"] += distance
            by_type["duration_min"] += duration
            by_type["load"] += load

    daily_re = re.compile(r"^\d{4}-\d{2}-\d{2}_(\d{4}-\d{2}-\d{2})\.json$")
    advanced_re = re.compile(r"^\d{4}-\d{2}-\d{2}_advanced_(\d{4}-\d{2}-\d{2})\.json$")
    for path in (root / "health").glob("*.json"):
        daily_match = daily_re.match(path.name)
        advanced_match = advanced_re.match(path.name)
        payload = _load_json(path)
        if not isinstance(payload, dict):
            continue
        if daily_match:
            day = daily_match.group(1)
            _ensure_day(days, day)["health"].update(_extract_daily_health(payload))
        elif advanced_match:
            day = advanced_match.group(1)
            _ensure_day(days, day)["advanced"].update(_extract_advanced(payload))

    for day in days.values():
        _round_activity(day)

    cache = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": target_day.isoformat(),
        "days": dict(sorted(days.items())),
    }
    cache["trends"] = trend_summary(cache, target_day.isoformat())
    return cache


def refresh_metric_cache(data_dir: str = "./data", target: str | None = None) -> dict[str, Any]:
    cache = build_metric_cache(data_dir=data_dir, target=target)
    out_dir = Path(data_dir) / "metrics"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "metric_cache.json"
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    cache["path"] = str(path)
    return cache


def trend_summary(cache: dict[str, Any], target: str | None = None) -> dict[str, Any]:
    target_day = _as_date(target) or date.today()
    days = cache.get("days") or {}
    current_start = target_day - timedelta(days=6)
    previous_start = target_day - timedelta(days=13)
    previous_end = target_day - timedelta(days=7)
    month_start = target_day - timedelta(days=29)
    current = _window(days, current_start, target_day)
    previous = _window(days, previous_start, previous_end)
    month = _window(days, month_start, target_day)
    return {
        "current_7d": current,
        "previous_7d": previous,
        "last_30d": month,
        "delta_7d": _delta(current, previous),
        "flags": _flags(current, previous),
    }


def _window(days: dict[str, Any], start: date, end: date) -> dict[str, Any]:
    out = {"start": start.isoformat(), "end": end.isoformat(), "activity_days": 0, "activities": 0, "distance_km": 0.0, "duration_min": 0.0, "load": 0.0}
    cursor = start
    while cursor <= end:
        day = days.get(cursor.isoformat()) or {}
        acts = day.get("activities") or {}
        count = int(acts.get("count") or 0)
        if count:
            out["activity_days"] += 1
        out["activities"] += count
        out["distance_km"] += float(acts.get("distance_km") or 0)
        out["duration_min"] += float(acts.get("duration_min") or 0)
        out["load"] += float(acts.get("load") or 0)
        cursor += timedelta(days=1)
    for key in ("distance_km", "duration_min", "load"):
        out[key] = round(out[key], 1)
    return out


def _delta(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("activities", "distance_km", "duration_min", "load"):
        old = float(previous.get(key) or 0)
        new = float(current.get(key) or 0)
        out[key] = {
            "absolute": round(new - old, 1),
            "percent": round((new - old) / old * 100.0, 1) if old > 0 else None,
        }
    return out


def _flags(current: dict[str, Any], previous: dict[str, Any]) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    old_load = float(previous.get("load") or 0)
    new_load = float(current.get("load") or 0)
    if old_load > 0:
        change = (new_load - old_load) / old_load
        if change > 0.35:
            flags.append({"severity": "warning", "code": "load_jump", "message": f"7 日负荷较前 7 日增加 {round(change * 100, 1)}%"})
        elif change < -0.35:
            flags.append({"severity": "info", "code": "load_drop", "message": f"7 日负荷较前 7 日下降 {round(abs(change) * 100, 1)}%"})
    if int(current.get("activity_days") or 0) >= 6:
        flags.append({"severity": "warning", "code": "low_rest_days", "message": "近 7 日训练日过多，恢复日不足"})
    return flags
