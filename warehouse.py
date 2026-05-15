"""Normalize Garmin export JSON into a small SQLite warehouse."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _date_from_name(path: Path) -> str:
    return path.name[:10]


def _activity_date(item: dict[str, Any]) -> str:
    value = item.get("startTimeLocal") or item.get("startTimeGMT") or ""
    return str(value)[:10] if value else ""


def refresh_warehouse(data_dir: str = "./data", db_path: str = "./data/garmin_warehouse.sqlite") -> dict[str, int]:
    data_root = Path(data_dir)
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    counts = {"activities": 0, "daily_metrics": 0, "devices": 0, "workouts": 0, "gear": 0}

    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activities (
                activity_id TEXT PRIMARY KEY,
                activity_date TEXT,
                name TEXT,
                type_key TEXT,
                distance_m REAL,
                duration_s REAL,
                avg_hr REAL,
                max_hr REAL,
                calories REAL,
                training_load REAL,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_metrics (
                metric_date TEXT,
                metric TEXT,
                raw_json TEXT,
                PRIMARY KEY(metric_date, metric)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                name TEXT,
                status TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workouts (
                workout_id TEXT PRIMARY KEY,
                name TEXT,
                sport_type TEXT,
                duration_s REAL,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gear (
                gear_uuid TEXT PRIMARY KEY,
                name TEXT,
                type_name TEXT,
                status TEXT,
                date_begin TEXT,
                maximum_m REAL,
                raw_json TEXT
            )
            """
        )

        for path in (data_root / "activities").glob("*.json"):
            items = _load_json(path)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict) or not item.get("activityId"):
                    continue
                sport = item.get("activityType") or {}
                conn.execute(
                    """
                    INSERT OR REPLACE INTO activities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(item.get("activityId")),
                        _activity_date(item),
                        item.get("activityName"),
                        sport.get("typeKey"),
                        item.get("distance"),
                        item.get("duration"),
                        item.get("averageHR"),
                        item.get("maxHR"),
                        item.get("calories"),
                        item.get("activityTrainingLoad") or item.get("aerobicTrainingEffect"),
                        json.dumps(item, ensure_ascii=False, default=str),
                    ),
                )
                counts["activities"] += 1

        for path in (data_root / "health").glob("*.json"):
            payload = _load_json(path)
            if not isinstance(payload, dict):
                continue
            metric_date = _date_from_name(path)
            for metric, value in payload.items():
                conn.execute(
                    "INSERT OR REPLACE INTO daily_metrics VALUES (?, ?, ?)",
                    (metric_date, metric, json.dumps(value, ensure_ascii=False, default=str)),
                )
                counts["daily_metrics"] += 1

        for path in (data_root / "device").glob("*.json"):
            payload = _load_json(path)
            if not isinstance(payload, dict):
                continue
            for item in payload.get("devices") or []:
                if not isinstance(item, dict):
                    continue
                device_id = item.get("deviceId") or item.get("id")
                if not device_id:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO devices VALUES (?, ?, ?, ?)",
                    (
                        str(device_id),
                        item.get("productDisplayName"),
                        item.get("deviceStatus"),
                        json.dumps(item, ensure_ascii=False, default=str),
                    ),
                )
                counts["devices"] += 1

        for path in (data_root / "training").glob("*.json"):
            payload = _load_json(path)
            if not isinstance(payload, dict):
                continue
            for item in payload.get("workouts") or []:
                if not isinstance(item, dict) or not item.get("workoutId"):
                    continue
                sport = item.get("sportType") or {}
                conn.execute(
                    "INSERT OR REPLACE INTO workouts VALUES (?, ?, ?, ?, ?)",
                    (
                        str(item.get("workoutId")),
                        item.get("workoutName"),
                        sport.get("sportTypeKey"),
                        item.get("estimatedDurationInSecs"),
                        json.dumps(item, ensure_ascii=False, default=str),
                    ),
                )
                counts["workouts"] += 1

        for path in (data_root / "gear").glob("*.json"):
            payload = _load_json(path)
            if not isinstance(payload, dict):
                continue
            for item in payload.get("gear") or []:
                if not isinstance(item, dict):
                    continue
                gear_uuid = item.get("uuid") or item.get("gearUuid") or item.get("gearUUID")
                if not gear_uuid:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO gear VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(gear_uuid),
                        item.get("displayName") or item.get("gearMakeName"),
                        item.get("gearTypeName"),
                        item.get("gearStatusName"),
                        item.get("dateBegin"),
                        item.get("maximumMeters"),
                        json.dumps(item, ensure_ascii=False, default=str),
                    ),
                )
                counts["gear"] += 1

    return counts


def warehouse_status(db_path: str = "./data/garmin_warehouse.sqlite") -> dict[str, Any]:
    db = Path(db_path)
    if not db.exists():
        return {"exists": False, "path": str(db)}
    out: dict[str, Any] = {"exists": True, "path": str(db), "tables": {}}
    with sqlite3.connect(db) as conn:
        for table in ("activities", "daily_metrics", "devices", "workouts", "gear"):
            try:
                out["tables"][table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                out["tables"][table] = 0
        latest = conn.execute("SELECT activity_date, name FROM activities ORDER BY activity_date DESC LIMIT 1").fetchone()
        if latest:
            out["latest_activity"] = {"date": latest[0], "name": latest[1]}
    out["checked_at"] = date.today().isoformat()
    return out
