"""Fitness coach analytics for Garmin CN exports."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from coach_memory import CoachMemory


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _latest_file(folder: Path, pattern: str) -> Path | None:
    files = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _clamp(value: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, value))


def _as_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value[:10]).date()
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
    return str(sport.get("typeKey") or activity.get("activityTypeKey") or "").lower()


def _sum_duration_minutes(items: list[dict[str, Any]]) -> float:
    return sum(float(x.get("duration") or x.get("movingDuration") or 0) for x in items) / 60.0


def _sum_distance_km(items: list[dict[str, Any]]) -> float:
    return sum(float(x.get("distance") or 0) for x in items) / 1000.0


def _month_bounds(target: date) -> tuple[date, date]:
    start = target.replace(day=1)
    return start, target


@dataclass
class FitnessCoach:
    data_dir: Path = Path("data")
    memory: CoachMemory = field(default_factory=CoachMemory)

    def __post_init__(self) -> None:
        if not isinstance(self.data_dir, Path):
            self.data_dir = Path(self.data_dir)

    def health_for(self, target: str) -> dict[str, Any]:
        path = self.data_dir / "health" / f"{date.today().isoformat()}_{target}.json"
        if path.exists():
            data = _load(path)
            return data if isinstance(data, dict) else {}
        latest = _latest_file(self.data_dir / "health", f"*_{target}.json")
        data = _load(latest) if latest else {}
        return data if isinstance(data, dict) else {}

    def advanced_for(self, target: str) -> dict[str, Any]:
        latest = _latest_file(self.data_dir / "health", f"*_advanced_{target}.json")
        data = _load(latest) if latest else {}
        return data if isinstance(data, dict) else {}

    def activities(self) -> list[dict[str, Any]]:
        latest = _latest_file(self.data_dir / "activities", "*.json")
        data = _load(latest) if latest else []
        items = data if isinstance(data, list) else []
        return [x for x in items if isinstance(x, dict)]

    def gear_data(self) -> dict[str, Any]:
        latest = _latest_file(self.data_dir / "gear", "*.json")
        data = _load(latest) if latest else {}
        return data if isinstance(data, dict) else {}

    def activities_between(self, start: date, end: date) -> list[dict[str, Any]]:
        out = []
        for item in self.activities():
            d = _as_date(item.get("startTimeLocal") or item.get("startTimeGMT") or "")
            if d and start <= d <= end:
                out.append(item)
        return out

    def acwr(self, target: str | None = None) -> dict[str, Any]:
        end = _as_date(target or date.today().isoformat()) or date.today()
        acute_start = end - timedelta(days=6)
        chronic_start = end - timedelta(days=27)
        acute_items = self.activities_between(acute_start, end)
        chronic_items = self.activities_between(chronic_start, end)
        acute = sum(_activity_load(x) for x in acute_items)
        chronic_weekly = sum(_activity_load(x) for x in chronic_items) / 4.0
        ratio = acute / chronic_weekly if chronic_weekly > 0 else None
        if ratio is None:
            status = "insufficient_data"
        elif ratio < 0.8:
            status = "underloading"
        elif ratio <= 1.3:
            status = "optimal"
        elif ratio <= 1.5:
            status = "caution"
        else:
            status = "high_risk"
        return {
            "acute_7d_load": round(acute, 1),
            "chronic_28d_weekly_load": round(chronic_weekly, 1),
            "ratio": round(ratio, 2) if ratio is not None else None,
            "status": status,
            "activities_7d": len(acute_items),
            "activities_28d": len(chronic_items),
        }

    def gear_report(self, target: str | None = None) -> dict[str, Any]:
        end = _as_date(target or date.today().isoformat()) or date.today()
        payload = self.gear_data()
        gear = [x for x in payload.get("gear") or [] if isinstance(x, dict)]
        activities = self.activities()
        reports = []
        for item in gear:
            uuid = item.get("uuid") or item.get("gearUuid") or item.get("gearUUID")
            begin = _as_date(str(item.get("dateBegin") or ""))
            max_m = item.get("maximumMeters") or item.get("maxDistance") or item.get("maximumDistanceInMeters")
            explicit_m = (
                item.get("totalMeters")
                or item.get("totalDistanceInMeters")
                or item.get("totalDistance")
                or item.get("distance")
            )
            linked = []
            if uuid:
                for activity in activities:
                    raw = json.dumps(activity, ensure_ascii=False, default=str)
                    if str(uuid) in raw:
                        linked.append(activity)
            inferred = False
            if explicit_m is None and len(gear) == 1:
                linked = [x for x in activities if (not begin or ((_as_date(x.get("startTimeLocal") or x.get("startTimeGMT") or "") or end) >= begin))]
                explicit_m = sum(float(x.get("distance") or 0) for x in linked)
                inferred = True
            used_m = float(explicit_m or 0)
            max_m_float = float(max_m or 0)
            percent = (used_m / max_m_float * 100.0) if max_m_float > 0 else None
            if percent is None:
                status = "unknown"
            elif percent >= 100:
                status = "replace_now"
            elif percent >= 85:
                status = "near_limit"
            else:
                status = "ok"
            reports.append({
                "name": item.get("displayName") or item.get("gearMakeName") or str(uuid),
                "uuid": uuid,
                "type": item.get("gearTypeName"),
                "status": status,
                "used_km": round(used_m / 1000.0, 1),
                "limit_km": round(max_m_float / 1000.0, 1) if max_m_float else None,
                "used_percent": round(percent, 1) if percent is not None else None,
                "activity_count": len(linked),
                "usage_source": "inferred_all_activities" if inferred else "garmin_or_linked_activity",
                "date_begin": item.get("dateBegin"),
            })
        alerts = [
            {"severity": "warning", "message": f"{x['name']} 接近寿命上限 {x['used_percent']}%"}
            for x in reports
            if x.get("status") == "near_limit"
        ]
        alerts.extend(
            {"severity": "critical", "message": f"{x['name']} 已超过寿命上限 {x['used_percent']}%"}
            for x in reports
            if x.get("status") == "replace_now"
        )
        return {"count": len(reports), "gear": reports, "alerts": alerts}

    def alerts(self, target: str | None = None) -> dict[str, Any]:
        target = target or date.today().isoformat()
        d = _as_date(target) or date.today()
        health = self.health_for(target)
        readiness = self.readiness(target)
        acwr = readiness["evidence"]["acwr"]
        alerts: list[dict[str, Any]] = []

        def add(severity: str, code: str, message: str, action: str) -> None:
            alerts.append({"severity": severity, "code": code, "message": message, "action": action})

        if readiness["verdict"] == "red":
            add("critical", "readiness_red", f"准备度 {readiness['score']}，不适合上强度。", "休息或低强度恢复。")
        elif readiness["verdict"] == "yellow":
            add("warning", "readiness_yellow", f"准备度 {readiness['score']}，恢复一般。", "只做轻松有氧或技术练习。")

        sleep = health.get("sleep") or {}
        sleep_hours = float(sleep.get("sleepTimeSeconds") or 0) / 3600.0
        if sleep_hours and sleep_hours < 5:
            add("critical", "sleep_low", f"睡眠 {round(sleep_hours, 1)}h，明显不足。", "取消质量课，补觉优先。")
        elif sleep_hours and sleep_hours < 6:
            add("warning", "sleep_low", f"睡眠 {round(sleep_hours, 1)}h，低于训练日下限。", "降低训练量 20-40%。")

        hrv = health.get("hrv") or {}
        hrv_summary = hrv.get("hrvSummary") or {}
        hrv_status = str(hrv_summary.get("status") or "").upper()
        hrv_last = hrv_summary.get("lastNightAvg")
        hrv_weekly = hrv_summary.get("weeklyAvg")
        if hrv_status and hrv_status not in ("BALANCED", "OPTIMAL"):
            add("warning", "hrv_unbalanced", f"HRV 状态 {hrv_status}。", "观察疲劳、压力、睡眠，避免连续高强度。")
        elif hrv_last and hrv_weekly and float(hrv_last) < float(hrv_weekly) * 0.85:
            add("warning", "hrv_drop", f"HRV {hrv_last} 低于周均 {hrv_weekly}。", "今日训练降级。")

        hr = health.get("heart_rate") or {}
        rhr = hr.get("restingHeartRate")
        rhr_base = hr.get("lastSevenDaysAvgRestingHeartRate")
        if rhr and rhr_base and float(rhr) >= float(rhr_base) + 5:
            add("warning", "rhr_rise", f"静息心率 {rhr}，高于 7 日均值 {rhr_base}。", "先排除生病、压力、睡眠不足。")

        ratio = acwr.get("ratio")
        if ratio is not None:
            if ratio > 1.5:
                add("critical", "acwr_high", f"ACWR {ratio}，负荷跳增风险高。", "未来 3-5 天降负荷。")
            elif ratio > 1.3:
                add("warning", "acwr_caution", f"ACWR {ratio}，负荷偏高。", "保留恢复日，避免叠加强度。")
            elif ratio < 0.8:
                add("info", "acwr_low", f"ACWR {ratio}，当前负荷偏低。", "若目标比赛，可渐进加量。")

        recent = self.activities_between(d - timedelta(days=2), d)
        hard = [
            x for x in recent
            if float(x.get("duration") or 0) >= 1200
            and (float(x.get("averageHR") or 0) >= 155 or _activity_load(x) >= 80)
        ]
        if len(hard) >= 2:
            add("warning", "consecutive_hard", f"近 3 天有 {len(hard)} 次偏硬训练。", "安排 24-48 小时低强度恢复。")

        if self.memory.active_risk_penalty() > 0:
            add("warning", "recovery_log_risk", "Recovery Log 存在活跃风险记录。", "训练前确认疼痛/不适是否已消失。")

        for item in self.gear_report(target).get("alerts", []):
            add(item["severity"], "gear_life", item["message"], "检查装备磨损，必要时退役或拆分记录。")

        severity_rank = {"critical": 0, "warning": 1, "info": 2}
        alerts.sort(key=lambda x: severity_rank.get(x["severity"], 9))
        return {"date": target, "count": len(alerts), "alerts": alerts, "readiness": readiness["score"], "acwr": acwr}

    def readiness(self, target: str | None = None) -> dict[str, Any]:
        target = target or date.today().isoformat()
        health = self.health_for(target)
        advanced = self.advanced_for(target)
        memory_penalty = self.memory.active_risk_penalty()

        sleep = health.get("sleep") or {}
        sleep_seconds = float(sleep.get("sleepTimeSeconds") or 0)
        sleep_score = _clamp((sleep_seconds / 28800.0) * 100) if sleep_seconds else 70
        sleep_feedback = sleep.get("sleepScoreFeedback") or ""

        hrv = health.get("hrv") or advanced.get("hrv_data") or {}
        hrv_summary = hrv.get("hrvSummary") or {}
        hrv_status = str(hrv_summary.get("status") or "").upper()
        hrv_last = hrv_summary.get("lastNightAvg")
        hrv_weekly = hrv_summary.get("weeklyAvg")
        if hrv_status == "BALANCED":
            hrv_score = 90
        elif hrv_last and hrv_weekly:
            hrv_score = _clamp(float(hrv_last) / max(float(hrv_weekly), 1) * 85)
        else:
            hrv_score = 70

        hr = health.get("heart_rate") or {}
        rhr = hr.get("restingHeartRate") or (advanced.get("rhr") or {}).get("restingHeartRate")
        rhr_base = hr.get("lastSevenDaysAvgRestingHeartRate")
        if rhr and rhr_base:
            rhr_score = _clamp(90 - max(0, float(rhr) - float(rhr_base)) * 8)
        else:
            rhr_score = 75

        body_battery = health.get("body_battery") or []
        bb_value = None
        if body_battery and isinstance(body_battery[0], dict):
            arr = body_battery[0].get("bodyBatteryValuesArray") or []
            if arr:
                bb_value = arr[-1][1]
            else:
                bb_value = body_battery[0].get("charged")
        bb_score = float(bb_value) if isinstance(bb_value, (int, float)) else 70

        acwr = self.acwr(target)
        ratio = acwr.get("ratio")
        if ratio is None:
            load_score = 75
        elif 0.8 <= ratio <= 1.3:
            load_score = 90
        elif ratio < 0.8:
            load_score = 70
        elif ratio <= 1.5:
            load_score = 60
        else:
            load_score = 35

        score = (
            sleep_score * 0.30
            + hrv_score * 0.25
            + rhr_score * 0.15
            + bb_score * 0.20
            + load_score * 0.10
            - memory_penalty
        )
        score = round(_clamp(score), 1)
        if score >= 80:
            verdict = "green"
            actions = ["可以安排质量课或中等偏高负荷训练", "热身后再决定是否上强度", "训练后补碳水和蛋白"]
        elif score >= 65:
            verdict = "yellow"
            actions = ["建议轻松跑、有氧骑行或技术练习", "避免连续高强度", "观察腿部和睡眠反馈"]
        else:
            verdict = "red"
            actions = ["优先恢复或休息", "只做低强度活动和灵活性训练", "若有疼痛，记录到 Recovery Log"]

        return {
            "score": score,
            "verdict": verdict,
            "summary": f"睡眠 {round(sleep_seconds/3600,1) if sleep_seconds else 'n/a'}h；HRV {hrv_status or 'n/a'}；RHR {rhr or 'n/a'}；Body Battery {bb_value or 'n/a'}；ACWR {ratio or 'n/a'}。",
            "actions": actions,
            "evidence": {
                "sleep_score": round(sleep_score, 1),
                "sleep_feedback": sleep_feedback,
                "hrv_score": round(hrv_score, 1),
                "rhr_score": round(rhr_score, 1),
                "body_battery_score": round(bb_score, 1),
                "load_score": round(load_score, 1),
                "injury_penalty": memory_penalty,
                "acwr": acwr,
            },
        }

    def race_confidence(self, target: str | None = None) -> dict[str, Any]:
        target = target or date.today().isoformat()
        readiness = self.readiness(target)
        acwr = self.acwr(target)
        advanced = self.advanced_for(target)
        training_status = advanced.get("training_status") or {}
        vo2 = ((training_status.get("mostRecentVO2Max") or {}).get("generic") or {}).get("vo2MaxValue")
        load_status = acwr.get("status")
        injury = self.memory.active_risk_penalty()

        injury_score = 100 - injury * 3
        load_score = {"optimal": 90, "underloading": 65, "caution": 60, "high_risk": 35}.get(str(load_status), 70)
        fitness_score = _clamp((float(vo2) / 60.0) * 100) if vo2 else 70
        recovery_score = readiness["score"]
        confidence = round(_clamp(injury_score * 0.40 + load_score * 0.25 + fitness_score * 0.25 + recovery_score * 0.10), 1)
        return {
            "score": confidence,
            "verdict": "confident" if confidence >= 80 else "building" if confidence >= 65 else "fragile",
            "summary": f"比赛信心由伤病风险、负荷、VO2max、恢复状态合成。VO2max={vo2 or 'n/a'}，ACWR={acwr.get('ratio') or 'n/a'}。",
            "evidence": {
                "injury_component": round(injury_score, 1),
                "load_component": load_score,
                "fitness_component": round(fitness_score, 1),
                "recovery_component": recovery_score,
                "weights": "injury 40%, load 25%, fitness 25%, recovery 10%",
            },
        }

    def morning(self, target: str | None = None, write_memory: bool = True) -> dict[str, Any]:
        report = self.readiness(target)
        report["race_confidence"] = self.race_confidence(target)
        if write_memory:
            path = self.memory.write_daily_report("Morning", report, target)
            report["memory_path"] = str(path)
        return report

    def evening(self, target: str | None = None, write_memory: bool = True) -> dict[str, Any]:
        target = target or date.today().isoformat()
        d = _as_date(target) or date.today()
        acts = self.activities_between(d, d)
        total_load = sum(_activity_load(x) for x in acts)
        total_minutes = sum(float(x.get("duration") or 0) for x in acts) / 60.0
        if acts:
            main = max(acts, key=lambda x: float(x.get("duration") or 0))
            avg_hr = main.get("averageHR")
            speed = main.get("averageSpeed")
            efficiency = round((float(speed) * 60.0) / float(avg_hr), 4) if speed and avg_hr else None
            summary = f"{len(acts)} 次活动，{round(total_minutes,1)} 分钟，估算负荷 {round(total_load,1)}。主训练：{main.get('activityName')}。"
        else:
            main = {}
            efficiency = None
            summary = "今日没有导出的活动记录。"
        acwr = self.acwr(target)
        report = {
            "score": round(_clamp(100 - max(0, (acwr.get("ratio") or 1) - 1.3) * 60), 1),
            "verdict": "logged",
            "summary": summary,
            "actions": ["记录主观疲劳 RPE", "若出现疼痛，写入 Recovery Log", "睡前优先恢复"],
            "evidence": {"activities": len(acts), "load": round(total_load, 1), "efficiency_speed_per_hr": efficiency, "main_activity": main, "acwr": acwr},
        }
        if write_memory:
            path = self.memory.write_daily_report("Evening", report, target)
            report["memory_path"] = str(path)
        return report

    def weekly(self, target: str | None = None, write_memory: bool = True) -> dict[str, Any]:
        end = _as_date(target or date.today().isoformat()) or date.today()
        start = end - timedelta(days=6)
        acts = self.activities_between(start, end)
        total_load = sum(_activity_load(x) for x in acts)
        total_distance = sum(float(x.get("distance") or 0) for x in acts)
        total_minutes = sum(float(x.get("duration") or 0) for x in acts) / 60.0
        acwr = self.acwr(end.isoformat())
        race = self.race_confidence(end.isoformat())
        report = {
            "score": race["score"],
            "verdict": acwr["status"],
            "summary": f"{start.isoformat()}~{end.isoformat()}：{len(acts)} 次活动，{round(total_distance/1000,1)} km，{round(total_minutes,1)} 分钟，估算负荷 {round(total_load,1)}。",
            "actions": ["下周负荷按 ACWR 调整", "保留至少 1 天恢复", "质量课后 24-48 小时观察 HRV/RHR"],
            "evidence": {"acwr": acwr, "race_confidence": race},
        }
        if write_memory:
            path = self.memory.write_daily_report("Weekly", report, end.isoformat())
            report["memory_path"] = str(path)
        return report

    def monthly(self, target: str | None = None, write_memory: bool = True) -> dict[str, Any]:
        end = _as_date(target or date.today().isoformat()) or date.today()
        start, end = _month_bounds(end)
        acts = self.activities_between(start, end)
        run_acts = [x for x in acts if _activity_type(x) == "running"]
        total_distance = _sum_distance_km(acts)
        running_distance = _sum_distance_km(run_acts)
        total_minutes = _sum_duration_minutes(acts)
        total_load = sum(_activity_load(x) for x in acts)
        longest = max(acts, key=lambda x: float(x.get("distance") or 0), default={})
        by_type: dict[str, dict[str, Any]] = {}
        for item in acts:
            key = _activity_type(item) or "unknown"
            slot = by_type.setdefault(key, {"count": 0, "distance_km": 0.0, "minutes": 0.0, "load": 0.0})
            slot["count"] += 1
            slot["distance_km"] += float(item.get("distance") or 0) / 1000.0
            slot["minutes"] += float(item.get("duration") or 0) / 60.0
            slot["load"] += _activity_load(item)
        for slot in by_type.values():
            slot["distance_km"] = round(slot["distance_km"], 1)
            slot["minutes"] = round(slot["minutes"], 1)
            slot["load"] = round(slot["load"], 1)
        acwr = self.acwr(end.isoformat())
        alerts = self.alerts(end.isoformat())
        score = self.race_confidence(end.isoformat())["score"]
        report = {
            "score": score,
            "verdict": acwr["status"],
            "summary": f"{start.isoformat()}~{end.isoformat()}：{len(acts)} 次活动，合计 {round(total_distance,1)} km / {round(total_minutes,1)} 分钟；跑步 {round(running_distance,1)} km；估算负荷 {round(total_load,1)}。",
            "actions": [
                "下月周跑量增幅控制在 5-10%",
                "每周保留 1 次长距离、1 次质量课、1-2 次力量/灵活性",
                "若预警为 warning/critical，先恢复再加量",
            ],
            "evidence": {
                "period": {"start": start.isoformat(), "end": end.isoformat()},
                "by_type": by_type,
                "longest_activity": {
                    "name": longest.get("activityName"),
                    "date": (longest.get("startTimeLocal") or "")[:10],
                    "distance_km": round(float(longest.get("distance") or 0) / 1000.0, 1),
                },
                "acwr": acwr,
                "alerts": alerts,
                "gear": self.gear_report(end.isoformat()),
            },
        }
        if write_memory:
            path = self.memory.write_daily_report("Monthly", report, end.isoformat())
            report["memory_path"] = str(path)
        return report

    def plan(self, target: str | None = None, weeks: int = 4, write_memory: bool = True) -> dict[str, Any]:
        start = _as_date(target or date.today().isoformat()) or date.today()
        weeks = max(1, min(int(weeks), 12))
        recent_start = start - timedelta(days=27)
        recent = self.activities_between(recent_start, start)
        run_recent = [x for x in recent if _activity_type(x) == "running"]
        weekly_km = _sum_distance_km(run_recent) / 4.0
        if weekly_km <= 0:
            weekly_km = _sum_distance_km(recent) / 4.0
        base_km = max(8.0, weekly_km)
        readiness = self.readiness(start.isoformat())
        acwr = self.acwr(start.isoformat())
        ratio = acwr.get("ratio")
        multiplier = 1.0
        if readiness["verdict"] == "red":
            multiplier = 0.65
        elif readiness["verdict"] == "yellow":
            multiplier = 0.85
        if ratio is not None and ratio > 1.3:
            multiplier = min(multiplier, 0.8)
        elif ratio is not None and ratio < 0.8:
            multiplier = max(multiplier, 1.05)
        first_week_km = round(base_km * multiplier, 1)
        weekly_plan = []
        for index in range(weeks):
            week_start = start + timedelta(days=index * 7)
            week_end = week_start + timedelta(days=6)
            build = 1.0 + min(index, 2) * 0.08
            if index == 3:
                build = 0.8
            target_km = round(first_week_km * build, 1)
            long_run_km = round(max(4.0, target_km * 0.32), 1)
            easy_km = round(max(3.0, (target_km - long_run_km) / 3.0), 1)
            quality_detail = "节奏跑 2x8 分钟，Z3-Z4，中间慢跑 3 分钟"
            if readiness["verdict"] == "red" or (ratio is not None and ratio > 1.3):
                quality_detail = "取消强度，改 Z2 轻松跑 30-45 分钟"
            sessions = [
                {"day": "Mon", "type": "rest_or_mobility", "detail": "休息 + 15 分钟灵活性"},
                {"day": "Tue", "type": "easy_run", "detail": f"Z2 {easy_km} km"},
                {"day": "Wed", "type": "strength", "detail": "核心、臀腿、足踝 30-40 分钟"},
                {"day": "Thu", "type": "quality", "detail": quality_detail},
                {"day": "Fri", "type": "recovery", "detail": "休息或低强度骑行 30 分钟"},
                {"day": "Sat", "type": "long_run", "detail": f"Z2 {long_run_km} km"},
                {"day": "Sun", "type": "easy_run", "detail": f"Z1-Z2 {easy_km} km + 拉伸"},
            ]
            weekly_plan.append({
                "week": index + 1,
                "start": week_start.isoformat(),
                "end": week_end.isoformat(),
                "target_distance_km": target_km,
                "target_minutes": round(target_km / 7.5 * 60),
                "long_run_km": long_run_km,
                "sessions": sessions,
            })
        plan = {
            "start_date": start.isoformat(),
            "weeks": weeks,
            "focus": "跑步基础能力 + 稳定负荷 + 伤病风险控制",
            "guardrails": [
                f"当前准备度 {readiness['score']} / {readiness['verdict']}",
                f"当前 ACWR {acwr.get('ratio') or 'n/a'} / {acwr.get('status')}",
                "任何疼痛超过 3/10 或改变跑姿，立刻停止质量课",
                "HRV 明显下降或静息心率升高时，强度课降级为 Z2",
            ],
            "weekly_plan": weekly_plan,
            "source": {"recent_weekly_running_km": round(weekly_km, 1), "readiness": readiness, "acwr": acwr},
        }
        if write_memory:
            path = self.memory.write_training_plan(plan)
            plan["memory_path"] = str(path)
        return plan
