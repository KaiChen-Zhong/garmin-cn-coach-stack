"""Cross-agent fitness review workflow.

One entry point for WorkBuddy, OpenClaw, Hermes, CLI, API, and MCP.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from auth import GarminAuth
from coach import FitnessCoach
from data_inventory import save_data_inventory
from exporter import GarminExporter
from importer import GarminImporter
from metrics_cache import refresh_metric_cache
from warehouse import refresh_warehouse, warehouse_status


PROJECT_ROOT = Path(__file__).parent


def run_fitness_review(
    target: str | None = None,
    data_dir: str = "./data",
    lookback_days: int = 30,
    weeks: int = 4,
    sync: bool = True,
    sync_mode: str = "smart",
    write_memory: bool = True,
    import_plan: bool = False,
    include_easy_workouts: bool = False,
    is_cn: bool | None = True,
    deep: bool = False,
) -> dict[str, Any]:
    """Sync latest Garmin CN data, build coach reports, write Obsidian, optionally import plan."""
    target = target or date.today().isoformat()
    target_date = datetime.fromisoformat(target[:10]).date()
    data_root = str(Path(data_dir))
    if deep:
        sync = True
        sync_mode = "full"
        lookback_days = max(lookback_days, 365)
        weeks = max(weeks, 8)
    auth = GarminAuth(is_cn=is_cn)

    if not sync:
        sync_mode = "none"
    export_status = _sync_garmin(auth, data_root, target, lookback_days, sync_mode)
    metric_cache = refresh_metric_cache(data_dir=data_root, target=target)
    data_inventory = save_data_inventory(data_dir=data_root)

    coach = FitnessCoach(data_dir=Path(data_root))
    today = {
        "morning": coach.morning(target, write_memory=write_memory),
        "evening": coach.evening(target, write_memory=write_memory),
        "alerts": coach.alerts(target),
        "gear": coach.gear_report(target),
        "confidence": coach.race_confidence(target),
    }
    current_week = coach.weekly(target, write_memory=write_memory)
    previous_week_end = (target_date - timedelta(days=7)).isoformat()
    previous_week = coach.weekly(previous_week_end, write_memory=False)
    recent_month = coach.monthly(target, write_memory=write_memory)
    plan = coach.plan(target, weeks=weeks, write_memory=write_memory)

    import_results: list[dict[str, Any]] = []
    if import_plan:
        importer = GarminImporter(auth=auth)
        import_results = importer.import_coach_plan(plan, include_easy=include_easy_workouts)

    report = {
        "date": target,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": _summary(today, current_week, previous_week, recent_month),
        "export": export_status,
        "analysis_mode": "deep" if deep else "standard",
        "metric_cache": {
            "path": metric_cache.get("path"),
            "generated_at": metric_cache.get("generated_at"),
            "trends": metric_cache.get("trends"),
        },
        "data_inventory": {
            "path": data_inventory.get("path"),
            "activities": data_inventory.get("activities"),
            "categories": data_inventory.get("categories"),
            "recommendation": data_inventory.get("recommendation"),
        },
        "today": today,
        "current_week": current_week,
        "previous_week": previous_week,
        "recent_month": recent_month,
        "training_plan": plan,
        "garmin_import": {
            "requested": import_plan,
            "include_easy_workouts": include_easy_workouts,
            "results": import_results,
            "success_count": sum(1 for item in import_results if item.get("success")),
            "failed_count": sum(1 for item in import_results if not item.get("success")),
        },
        "llm_prompt": _llm_prompt(target, deep=deep),
        "manual_review": {
            "obsidian": "填写 Daily/* Manual Review.md 里的主观疲劳、疼痛、压力、实际完成情况。",
            "recovery_log": "有疼痛或异常，用 `python main.py fitness-coach log-recovery --note \"...\" --cn` 记录。",
        },
    }

    if write_memory:
        path = coach.memory.write_manual_review(report, target)
        report["manual_review"]["path"] = str(path)

    return report


def _summary(today: dict[str, Any], current_week: dict[str, Any], previous_week: dict[str, Any], recent_month: dict[str, Any]) -> str:
    readiness = today.get("morning", {}).get("score", "n/a")
    alerts = today.get("alerts", {}).get("count", "n/a")
    confidence = today.get("confidence", {}).get("score", "n/a")
    return (
        f"今日准备度 {readiness}，预警 {alerts} 条，比赛信心 {confidence}。"
        f" 本周：{current_week.get('summary', '')}"
        f" 前一周：{previous_week.get('summary', '')}"
        f" 近期：{recent_month.get('summary', '')}"
    )


def _llm_prompt(target: str, deep: bool = False) -> str:
    mode = "深度复盘模式：必须综合全量导出、指标缓存、数据覆盖清单、Obsidian 长期记忆。" if deep else "标准复盘模式：综合导出数据、指标缓存、Obsidian 长期记忆。"
    return "\n".join([
        f"你是耐力运动 AI 教练。请基于 {target} 的 Garmin 导出、教练指标、Obsidian 长期记忆，输出中文复盘。",
        mode,
        "必须覆盖：1. 今日恢复状态；2. 睡眠/HRV/RHR/Body Battery；3. 佳明官方训练状态/准备度/VO2max/HRV状态；4. 今日训练建议；5. 本周与前一周负荷差异；6. 近 30 天趋势；7. ACWR 风险；8. 装备风险；9. 训练计划是否应导入 Garmin；10. 需要用户手动补充的问题。",
        "深度模式下还要说明数据覆盖是否充分：哪些类别已导出、哪些指标缺失、缺失如何影响结论置信度。",
        "不要编造未出现的数据。数据缺失时明确说缺失，并给保守建议。",
        "输出格式：状态结论、数据覆盖、证据、风险、今天怎么练、未来 7-28 天计划、手动复盘问题。",
    ])


def _sync_garmin(auth: GarminAuth, data_dir: str, target: str, lookback_days: int, sync_mode: str) -> dict[str, Any]:
    db_path = str(Path(data_dir) / "garmin_warehouse.sqlite")
    mode = (sync_mode or "smart").lower()
    if mode == "none":
        return {"synced": False, "mode": "none", "warehouse": warehouse_status(db_path)}

    exporter = GarminExporter(data_dir=data_dir, auth=auth)
    exported: dict[str, Any] = {}
    if mode == "full":
        exported = exporter.export_all(lookback_days=lookback_days, date_str=target)
    elif mode == "quick":
        exported["daily_health"] = exporter.export_daily_health(target)
        exported["advanced_health"] = exporter.export_advanced_health(target)
        exported["activities"] = exporter.export_activities(max(7, min(lookback_days, 14)))
    else:
        exported["daily_health"] = exporter.export_daily_health(target)
        exported["advanced_health"] = exporter.export_advanced_health(target)
        exported["activities"] = exporter.export_activities(lookback_days)
        exported["body_composition"] = exporter.export_body_composition(target)
        exported["hydration"] = exporter.export_hydration(target)
        if not _has_today_file(data_dir, "gear"):
            exported["gear"] = exporter.export_gear()
        else:
            exported["gear"] = "cached"
        if not _has_today_file(data_dir, "training"):
            exported["training_plans"] = exporter.export_training_plans()
        else:
            exported["training_plans"] = "cached"
    refresh = refresh_warehouse(data_dir=data_dir, db_path=db_path)
    return {"synced": True, "mode": mode, "categories": list(exported.keys()), "warehouse": refresh}


def _has_today_file(data_dir: str, category: str) -> bool:
    folder = Path(data_dir) / category
    if not folder.exists():
        return False
    today = date.today().isoformat()
    return any(path.name.startswith(today) and path.suffix == ".json" for path in folder.glob("*.json"))
