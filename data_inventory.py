"""Local Garmin export coverage inventory."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date().isoformat()
    except Exception:
        return None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict, str)) and len(value) == 0:
        return True
    return False


def build_data_inventory(data_dir: str = "./data") -> dict[str, Any]:
    root = Path(data_dir)
    categories = {}
    for folder in sorted([x for x in root.iterdir() if x.is_dir()]) if root.exists() else []:
        files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime)
        categories[folder.name] = {
            "files": len(files),
            "latest_file": files[-1].name if files else None,
            "latest_mtime": datetime.fromtimestamp(files[-1].stat().st_mtime).isoformat(timespec="seconds") if files else None,
        }

    activities = []
    for path in (root / "activities").glob("*.json"):
        payload = _load(path)
        if isinstance(payload, list):
            activities.extend(x for x in payload if isinstance(x, dict))
    activity_dates = [
        _date(x.get("startTimeLocal") or x.get("startTimeGMT"))
        for x in activities
        if isinstance(x, dict)
    ]
    activity_dates = [x for x in activity_dates if x]

    health_missing: dict[str, list[str]] = {}
    health_present: dict[str, list[str]] = {}
    for path in (root / "health").glob("*.json"):
        payload = _load(path)
        if not isinstance(payload, dict):
            continue
        day = path.name[:10]
        for key, value in payload.items():
            bucket = health_missing if _is_missing(value) else health_present
            bucket.setdefault(day, []).append(key)

    latest_activity = None
    if activities:
        latest_activity = max(activities, key=lambda x: str(x.get("startTimeLocal") or x.get("startTimeGMT") or ""))

    return {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "data_dir": str(root),
        "categories": categories,
        "activities": {
            "count": len(activities),
            "first_date": min(activity_dates) if activity_dates else None,
            "latest_date": max(activity_dates) if activity_dates else None,
            "latest": {
                "activity_id": latest_activity.get("activityId") if latest_activity else None,
                "name": latest_activity.get("activityName") if latest_activity else None,
                "date": _date((latest_activity or {}).get("startTimeLocal") or (latest_activity or {}).get("startTimeGMT")),
            } if latest_activity else None,
        },
        "health_coverage": {
            "present_by_file_date": health_present,
            "missing_by_file_date": health_missing,
        },
        "recommendation": _recommend(categories, len(activities), activity_dates),
    }


def save_data_inventory(data_dir: str = "./data") -> dict[str, Any]:
    inventory = build_data_inventory(data_dir)
    out_dir = Path(data_dir) / "metrics"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "data_inventory.json"
    path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    inventory["path"] = str(path)
    return inventory


def _recommend(categories: dict[str, Any], activity_count: int, activity_dates: list[str]) -> list[str]:
    recs = []
    required = ("health", "activities", "training", "gear", "device", "goals")
    for name in required:
        if not categories.get(name, {}).get("files"):
            recs.append(f"{name} 缺少导出文件，建议跑 --deep 或 --sync-mode full")
    if activity_count == 0:
        recs.append("没有活动数据，训练负荷分析会很弱")
    elif activity_dates and max(activity_dates) < date.today().isoformat():
        recs.append("最新活动不是今天；如果今天训练过，建议先同步手表再跑复盘")
    if not recs:
        recs.append("本地数据覆盖可用于深度复盘")
    return recs
