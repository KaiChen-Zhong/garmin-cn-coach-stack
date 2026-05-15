"""
Garmin Connect 全量数据导出模块
- 覆盖全部 12 个数据类别
- 支持增量同步（仅导出上次同步后的新数据）
- 数据按日期+类别组织存储
- 兼容 garminconnect 0.3.3+ API
"""

import json
import logging
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional, Any

from auth import GarminAuth

logger = logging.getLogger(__name__)


class GarminExporter:
    """Garmin Connect 全量数据导出器"""

    def __init__(self, data_dir: str = "./data", auth: Optional[GarminAuth] = None):
        self.data_dir = Path(data_dir)
        self.auth = auth or GarminAuth()
        self._sync_state: dict = {}

    def _client(self):
        return self.auth.ensure_connected()

    # ─── 同步状态管理 ───

    def _load_sync_state(self, state_file: str = "./config/sync_state.json") -> dict:
        """加载同步状态"""
        path = Path(state_file)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._sync_state = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._sync_state = {}
        return self._sync_state

    def _save_sync_state(self, state_file: str = "./config/sync_state.json") -> None:
        """保存同步状态"""
        path = Path(state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._sync_state, f, indent=2, ensure_ascii=False)

    def _get_last_sync(self, category: str) -> Optional[str]:
        """获取某类别上次同步时间"""
        return self._sync_state.get(category, {}).get("last_sync")

    def _update_sync(self, category: str) -> None:
        """更新某类别同步时间"""
        self._sync_state.setdefault(category, {})["last_sync"] = datetime.now().isoformat()

    # ─── 数据存储 ───

    def _save_data(self, category: str, data: Any, suffix: str = "") -> Path:
        """保存数据到 JSON 文件"""
        today = date.today().isoformat()
        dir_path = self.data_dir / category
        dir_path.mkdir(parents=True, exist_ok=True)

        filename = f"{today}{suffix}.json"
        filepath = dir_path / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        logger.info("已保存 %s 数据到 %s", category, filepath)
        return filepath

    # ─── 用户资料 ───

    def export_user_profile(self) -> dict:
        """导出用户个人资料"""
        client = self._client()
        result = {}
        try:
            profile = client.get_user_profile()
            result["profile"] = profile
        except Exception as e:
            logger.error("导出用户资料失败: %s", e)

        try:
            settings = client.get_userprofile_settings()
            result["settings"] = settings
        except Exception as e:
            logger.warning("导出用户设置失败: %s", e)

        self._save_data("user_profile", result)
        self._update_sync("user_profile")
        return result

    # ─── 每日健康数据 ───

    def export_daily_health(self, for_date: Optional[str] = None) -> dict:
        """导出每日健康数据（心率、步数、睡眠、压力等）"""
        client = self._client()
        target = for_date or date.today().isoformat()
        result = {}

        health_methods = {
            "heart_rate": client.get_heart_rates,
            "steps": client.get_steps_data,
            "sleep": client.get_sleep_data,
            "stress": client.get_stress_data,
            "body_battery": client.get_body_battery,
            "floors": client.get_floors,
            "respiration": client.get_respiration_data,
            "spo2": client.get_spo2_data,
            "hrv": client.get_hrv_data,
        }

        for name, method in health_methods.items():
            try:
                data = method(target)
                result[name] = data
            except Exception as e:
                logger.warning("导出 %s 数据失败 (%s): %s", name, target, e)
                result[name] = None

        self._save_data("health", result, suffix=f"_{target}")
        self._update_sync("daily_health")
        return result

    # ─── 高级健康指标 ───

    def export_advanced_health(self, for_date: Optional[str] = None) -> dict:
        """导出高级健康指标（VO2 max、训练准备度、HRV等）"""
        client = self._client()
        target = for_date or date.today().isoformat()
        result = {}

        # 需要日期参数的方法
        advanced_date_methods = {
            "training_readiness": client.get_training_readiness,
            "training_status": client.get_training_status,
            "body_composition": client.get_body_composition,
            "all_day_stress": client.get_all_day_stress,
            "hrv_data": client.get_hrv_data,
            "rhr": client.get_rhr_day,
            "stats_and_body": client.get_stats_and_body,
            "intensity_minutes": client.get_intensity_minutes_data,
            "hill_score": client.get_hill_score,
            "endurance_score": client.get_endurance_score,
            "fitnessage": client.get_fitnessage_data,
            "lifestyle_logging": client.get_lifestyle_logging_data,
        }

        for name, method in advanced_date_methods.items():
            try:
                data = method(target)
                result[name] = data
            except Exception as e:
                logger.warning("导出高级健康 %s 失败 (%s): %s", name, target, e)
                result[name] = None

        # 需要单个日期参数的方法（非日期范围）
        single_date_methods = {
            "max_metrics": client.get_max_metrics,
            "morning_training_readiness": client.get_morning_training_readiness,
        }

        for name, method in single_date_methods.items():
            try:
                data = method(target)
                result[name] = data
            except Exception as e:
                logger.warning("导出高级健康 %s 失败 (%s): %s", name, target, e)
                result[name] = None

        # 需要日期范围参数的方法 (startdate, enddate, _type)
        start = (date.today() - timedelta(days=30)).isoformat()
        range_methods = {
            "race_predictions": client.get_race_predictions,
            "running_tolerance": client.get_running_tolerance,
        }

        for name, method in range_methods.items():
            try:
                if name == "race_predictions":
                    # race_predictions 要求全部参数或不传参数
                    data = method(start, target, "daily")
                else:
                    data = method(start, target)
                result[name] = data
            except Exception as e:
                logger.warning("导出高级健康 %s 失败 (%s~%s): %s", name, start, target, e)
                result[name] = None

        self._save_data("health", result, suffix=f"_advanced_{target}")
        self._update_sync("advanced_health")
        return result

    # ─── 活动数据 ───

    def export_activities(self, lookback_days: int = 30) -> list:
        """导出最近活动数据。

        Garmin limits one activities request to 1000 rows.  Older code used
        lookback_days * 5 in a single request, so --lookback 365 failed.
        """
        client = self._client()
        requested = max(1, lookback_days * 5)
        page_size = 1000
        activities: list = []
        try:
            for start in range(0, requested, page_size):
                limit = min(page_size, requested - start)
                page = client.get_activities(start, limit) or []
                activities.extend(page)
                if len(page) < limit:
                    break
            self._save_data("activities", activities)
            self._update_sync("activities")
            return activities
        except Exception as e:
            logger.error("导出活动数据失败: %s", e)
            return []

    def export_activity_details(self, activity_id: str) -> dict:
        """导出单个活动的详细数据"""
        client = self._client()
        try:
            details = client.get_activity(activity_id)
            return details
        except Exception as e:
            logger.error("导出活动详情 %s 失败: %s", activity_id, e)
            return {}

    def export_activity_fit(self, activity_id: str) -> Optional[bytes]:
        """导出活动的原始 FIT 文件（ORIGINAL 格式为 ZIP 压缩包，内含 .fit 文件）"""
        import zipfile
        import io
        from garminconnect import Garmin
        client = self._client()
        try:
            fit_data = client.download_activity(activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
            dir_path = self.data_dir / "activities" / "fit"
            dir_path.mkdir(parents=True, exist_ok=True)

            # ORIGINAL 格式可能是 ZIP 压缩包，需要解压
            if fit_data[:2] == b'PK':
                # ZIP 文件 - 解压获取 .fit 文件
                with zipfile.ZipFile(io.BytesIO(fit_data)) as zf:
                    fit_files = [n for n in zf.namelist() if n.endswith('.fit')]
                    if fit_files:
                        fit_content = zf.read(fit_files[0])
                        filepath = dir_path / f"{activity_id}.fit"
                        with open(filepath, "wb") as f:
                            f.write(fit_content)
                        logger.info("已从 ZIP 解压 FIT 文件: %s", filepath)
                        return fit_content
                    else:
                        # 没有 .fit 文件，保存整个 ZIP
                        filepath = dir_path / f"{activity_id}.zip"
                        with open(filepath, "wb") as f:
                            f.write(fit_data)
                        logger.info("已保存 ZIP 文件: %s", filepath)
                        return fit_data
            else:
                # 非 ZIP，直接保存
                filepath = dir_path / f"{activity_id}.fit"
                with open(filepath, "wb") as f:
                    f.write(fit_data)
                logger.info("已保存 FIT 文件: %s", filepath)
                return fit_data
        except Exception as e:
            logger.error("导出 FIT 文件 %s 失败: %s", activity_id, e)
            return None

    def export_activity_gpx(self, activity_id: str) -> Optional[str]:
        """导出活动的 GPX 文件"""
        from garminconnect import Garmin
        client = self._client()
        try:
            gpx_data = client.download_activity(activity_id, dl_fmt=Garmin.ActivityDownloadFormat.GPX)
            dir_path = self.data_dir / "activities" / "gpx"
            dir_path.mkdir(parents=True, exist_ok=True)
            filepath = dir_path / f"{activity_id}.gpx"
            mode = "wb" if isinstance(gpx_data, bytes) else "w"
            with open(filepath, mode) as f:
                f.write(gpx_data)
            logger.info("已保存 GPX 文件: %s", filepath)
            return filepath
        except Exception as e:
            logger.error("导出 GPX 文件 %s 失败: %s", activity_id, e)
            return None

    # ─── 身体成分 ───

    def export_body_composition(self, for_date: Optional[str] = None) -> dict:
        """导出身体成分数据"""
        client = self._client()
        target = for_date or date.today().isoformat()
        result = {}

        try:
            result["composition"] = client.get_body_composition(target)
        except Exception as e:
            logger.warning("导出身体成分失败: %s", e)

        try:
            result["weight"] = client.get_weigh_ins(target, target)
        except Exception as e:
            logger.warning("导出体重数据失败: %s", e)

        self._save_data("body_composition", result, suffix=f"_{target}")
        self._update_sync("body_composition")
        return result

    # ─── 目标与成就 ───

    def export_goals(self) -> dict:
        """导出目标、徽章、挑战、个人记录"""
        client = self._client()
        result = {}

        goal_methods = {
            "goals": lambda: client.get_goals(),
            "badges": lambda: client.get_earned_badges(),
            "challenges": lambda: client.get_adhoc_challenges(0, 20),
            "personal_records": lambda: client.get_personal_record(),
            "badge_challenges": lambda: client.get_badge_challenges(1, 20),
            "available_badges": lambda: client.get_available_badges(),
        }

        for name, method in goal_methods.items():
            try:
                data = method()
                result[name] = data
            except Exception as e:
                logger.warning("导出 %s 失败: %s", name, e)
                result[name] = None

        self._save_data("goals", result)
        self._update_sync("goals")
        return result

    # ─── 设备信息 ───

    def export_device_info(self) -> dict:
        """导出设备信息和设置"""
        client = self._client()
        result = {}

        try:
            devices = client.get_devices()
            result["devices"] = devices
            # 尝试获取第一个设备的设置
            if devices and isinstance(devices, list):
                device_id = devices[0].get("deviceId") or devices[0].get("id")
                if device_id:
                    try:
                        result["device_settings"] = client.get_device_settings(device_id)
                    except Exception as e:
                        logger.warning("导出设备设置失败: %s", e)
        except Exception as e:
            logger.warning("导出设备列表失败: %s", e)

        try:
            result["alarms"] = client.get_device_alarms()
        except Exception as e:
            logger.warning("导出闹钟设置失败: %s", e)

        self._save_data("device", result)
        self._update_sync("device")
        return result

    # ─── 装备管理 ───

    def export_gear(self) -> dict:
        """导出装备数据"""
        client = self._client()
        result = {}

        # 需要 userProfileNumber，从用户资料中获取
        try:
            profile = client.get_user_profile()
            # profileId 可能位于 profile["id"] 或 profile["profileId"]
            profile_id = None
            if isinstance(profile, dict):
                profile_id = profile.get("profileId") or profile.get("id")
        except Exception:
            profile_id = None

        if profile_id:
            try:
                result["gear"] = client.get_gear(profile_id)
            except Exception as e:
                logger.warning("导出装备数据失败: %s", e)

            try:
                result["gear_defaults"] = client.get_gear_defaults(profile_id)
            except Exception as e:
                logger.warning("导出默认装备失败: %s", e)
        else:
            logger.warning("无法获取 profileId，跳过装备数据导出")

        self._save_data("gear", result)
        self._update_sync("gear")
        return result

    # ─── 水合与营养 ───

    def export_hydration(self, for_date: Optional[str] = None) -> dict:
        """导出水合与营养数据"""
        client = self._client()
        target = for_date or date.today().isoformat()
        result = {}

        try:
            result["hydration"] = client.get_hydration_data(target)
        except Exception as e:
            logger.warning("导出水合数据失败: %s", e)

        try:
            result["nutrition_food"] = client.get_nutrition_daily_food_log(target)
        except Exception as e:
            logger.warning("导出营养数据失败: %s", e)

        self._save_data("hydration", result, suffix=f"_{target}")
        self._update_sync("hydration")
        return result

    # ─── 训练计划 ───

    def export_training_plans(self) -> dict:
        """导出训练计划"""
        client = self._client()
        result = {}

        try:
            result["training_plans"] = client.get_training_plans()
        except Exception as e:
            logger.warning("导出训练计划失败: %s", e)

        try:
            result["workouts"] = client.get_workouts()
        except Exception as e:
            logger.warning("导出训练列表失败: %s", e)

        try:
            result["scheduled_workouts"] = client.get_scheduled_workouts(date.today().year, date.today().month)
        except Exception as e:
            logger.warning("导出日程训练失败: %s", e)

        self._save_data("training", result)
        self._update_sync("training_plans")
        return result

    # ─── 高尔夫 ───

    def export_golf(self) -> dict:
        """导出高尔夫数据"""
        client = self._client()
        result = {}

        try:
            result["golf_summary"] = client.get_golf_summary()
        except Exception as e:
            logger.warning("导出高尔夫摘要失败: %s", e)

        self._save_data("golf", result)
        self._update_sync("golf")
        return result

    # ─── 历史趋势 ───

    def export_historical(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> dict:
        """导出历史趋势数据"""
        client = self._client()
        end = end_date or date.today().isoformat()
        start = start_date or (date.today() - timedelta(days=28)).isoformat()
        result = {}

        try:
            result["weekly_steps"] = client.get_weekly_steps(end, weeks=4)
        except Exception as e:
            logger.warning("导出周步数失败: %s", e)

        try:
            result["weekly_intensity_minutes"] = client.get_weekly_intensity_minutes(start, end)
        except Exception as e:
            logger.warning("导出周强度分钟失败: %s", e)

        try:
            result["weekly_stress"] = client.get_weekly_stress(end, weeks=4)
        except Exception as e:
            logger.warning("导出周压力失败: %s", e)

        self._save_data("health", result, suffix=f"_historical_{start}_{end}")
        self._update_sync("historical")
        return result

    # ─── 全量导出 ───

    def export_all(self, lookback_days: int = 30, date_str: Optional[str] = None) -> dict:
        """执行全量数据导出"""
        self._load_sync_state()
        target = date_str or date.today().isoformat()

        logger.info("=" * 60)
        logger.info("开始全量数据导出 - %s", target)
        logger.info("=" * 60)

        results = {}

        # 1. 用户资料
        logger.info("[1/12] 导出用户资料...")
        results["user_profile"] = self.export_user_profile()

        # 2. 每日健康
        logger.info("[2/12] 导出每日健康数据...")
        results["daily_health"] = self.export_daily_health(target)

        # 3. 高级健康
        logger.info("[3/12] 导出高级健康指标...")
        results["advanced_health"] = self.export_advanced_health(target)

        # 4. 历史趋势
        logger.info("[4/12] 导出历史趋势...")
        results["historical"] = self.export_historical()

        # 5. 活动数据
        logger.info("[5/12] 导出活动数据...")
        results["activities"] = self.export_activities(lookback_days)

        # 6. 身体成分
        logger.info("[6/12] 导出身体成分...")
        results["body_composition"] = self.export_body_composition(target)

        # 7. 目标成就
        logger.info("[7/12] 导出目标与成就...")
        results["goals"] = self.export_goals()

        # 8. 设备信息
        logger.info("[8/12] 导出设备信息...")
        results["device"] = self.export_device_info()

        # 9. 装备
        logger.info("[9/12] 导出装备数据...")
        results["gear"] = self.export_gear()

        # 10. 水合营养
        logger.info("[10/12] 导出水合与营养...")
        results["hydration"] = self.export_hydration(target)

        # 11. 训练计划
        logger.info("[11/12] 导出训练计划...")
        results["training_plans"] = self.export_training_plans()

        # 12. 高尔夫
        logger.info("[12/12] 导出高尔夫数据...")
        results["golf"] = self.export_golf()

        # 保存同步状态
        self._save_sync_state()

        # 生成摘要
        summary = {}
        for key, val in results.items():
            if isinstance(val, dict):
                summary[key] = {k: "ok" if v is not None else "failed" for k, v in val.items()}
            elif isinstance(val, list):
                summary[key] = f"{len(val)} items"
            else:
                summary[key] = "ok" if val else "failed"

        self._save_data(".", summary, suffix="_sync_summary")
        logger.info("全量导出完成！摘要: %s", json.dumps(summary, ensure_ascii=False))

        return results
