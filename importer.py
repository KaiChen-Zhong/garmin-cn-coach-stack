"""
Garmin Connect 训练计划导入模块
- 7 种运动类型训练创建与上传
- 训练日程安排
- 体重/水合/血压/身体成分数据写入
- 活动文件导入 (FIT/TCX/GPX)
"""

import json
import re
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Union
from pathlib import Path

from auth import GarminAuth

logger = logging.getLogger(__name__)


class GarminImporter:
    """Garmin Connect 数据导入器"""

    def __init__(self, auth: Optional[GarminAuth] = None):
        self.auth = auth or GarminAuth()
        self.client = None

    def _ensure_client(self):
        if self.client is None:
            self.client = self.auth.ensure_connected()

    # ─── 训练创建与上传 ───

    def create_workout(self, workout_type: str, workout_data: dict) -> dict:
        """
        创建并上传训练计划

        workout_type: running | cycling | swimming | walking | hiking | other
        workout_data: 训练定义字典，包含名称、步骤等
        """
        self._ensure_client()

        try:
            from garminconnect.workout import (
                RunningWorkout, CyclingWorkout, SwimmingWorkout,
                WalkingWorkout, HikingWorkout,
                create_warmup_step, create_interval_step,
                create_recovery_step, create_cooldown_step,
                create_repeat_group,
            )
        except ImportError:
            logger.error("需要安装 workout 扩展: pip install garminconnect[workout]")
            return {}

        workout_classes = {
            "running": RunningWorkout,
            "cycling": CyclingWorkout,
            "swimming": SwimmingWorkout,
            "walking": WalkingWorkout,
            "hiking": HikingWorkout,
        }

        # 有专用上传方法的类型
        type_specific_upload = {
            "running": self.client.upload_running_workout,
            "cycling": self.client.upload_cycling_workout,
            "swimming": self.client.upload_swimming_workout,
            "walking": self.client.upload_walking_workout,
            "hiking": self.client.upload_hiking_workout,
        }

        cls = workout_classes.get(workout_type)
        upload_fn = type_specific_upload.get(workout_type)

        if not cls:
            logger.error("不支持的训练类型: %s", workout_type)
            return {}

        try:
            # 构建训练步骤
            segments = self._build_workout_segments(workout_data, workout_type)
            workout = cls(
                workoutName=workout_data.get("name", "Custom Workout"),
                estimatedDurationInSecs=workout_data.get("estimated_duration", 1800),
                workoutSegments=segments,
            )

            if upload_fn:
                result = upload_fn(workout)
            else:
                # 通用上传方法
                result = self.client.upload_workout(workout)

            logger.info("训练 '%s' 上传成功: %s", workout_data.get("name"), result)
            return result or {}

        except Exception as e:
            logger.error("上传训练失败: %s", e)
            return {}

    def _build_workout_segments(self, workout_data: dict, workout_type: str = "running") -> list:
        """根据训练定义构建训练步骤段"""
        from garminconnect.workout import (
            WorkoutSegment,
            create_warmup_step, create_interval_step,
            create_recovery_step, create_cooldown_step,
            create_repeat_group,
            SportType,
        )

        steps = []
        raw_steps = workout_data.get("steps", [])
        step_order = 1

        for step_def in raw_steps:
            step_type = step_def.get("type", "interval")
            duration_seconds = step_def.get("duration", 300)

            if step_type == "warmup":
                steps.append(create_warmup_step(
                    duration_seconds=duration_seconds,
                    step_order=step_order,
                ))
            elif step_type == "interval":
                steps.append(create_interval_step(
                    duration_seconds=duration_seconds,
                    step_order=step_order,
                ))
            elif step_type == "recovery":
                steps.append(create_recovery_step(
                    duration_seconds=duration_seconds,
                    step_order=step_order,
                ))
            elif step_type == "cooldown":
                steps.append(create_cooldown_step(
                    duration_seconds=duration_seconds,
                    step_order=step_order,
                ))
            elif step_type == "repeat":
                steps.append(create_repeat_group(
                    repeat_count=step_def.get("repeat_count", 2),
                    steps=self._build_workout_segments(step_def, workout_type),
                ))
            step_order += 1

        if not steps:
            # 默认：热身 + 3组间歇 + 放松
            steps = [
                create_warmup_step(duration_seconds=600, step_order=1),
                create_interval_step(duration_seconds=300, step_order=2),
                create_recovery_step(duration_seconds=120, step_order=3),
                create_interval_step(duration_seconds=300, step_order=4),
                create_recovery_step(duration_seconds=120, step_order=5),
                create_interval_step(duration_seconds=300, step_order=6),
                create_cooldown_step(duration_seconds=300, step_order=7),
            ]

        # SportType 映射
        sport_type_map = {
            "running": {"sportTypeId": SportType.RUNNING, "sportTypeKey": "running", "displayOrder": 1},
            "cycling": {"sportTypeId": SportType.CYCLING, "sportTypeKey": "cycling", "displayOrder": 1},
            "swimming": {"sportTypeId": SportType.SWIMMING, "sportTypeKey": "swimming", "displayOrder": 1},
            "walking": {"sportTypeId": SportType.WALKING, "sportTypeKey": "walking", "displayOrder": 1},
            "hiking": {"sportTypeId": SportType.HIKING, "sportTypeKey": "hiking", "displayOrder": 1},
        }
        sport_type = sport_type_map.get(workout_type, {"sportTypeId": SportType.RUNNING, "sportTypeKey": "running", "displayOrder": 1})

        return [WorkoutSegment(segmentOrder=1, sportType=sport_type, workoutSteps=steps)]

    # ─── 训练日程管理 ───

    def schedule_workout(self, workout_id: str, schedule_date: str) -> dict:
        """将训练安排到指定日期"""
        self._ensure_client()
        try:
            result = self.client.schedule_workout(workout_id, schedule_date)
            logger.info("训练 %s 已安排到 %s", workout_id, schedule_date)
            return result or {}
        except Exception as e:
            logger.error("安排训练失败: %s", e)
            return {}

    def unschedule_workout(self, workout_id: str, schedule_date: str) -> bool:
        """取消训练安排"""
        self._ensure_client()
        try:
            self.client.unschedule_workout(workout_id, schedule_date)
            logger.info("已取消训练 %s 在 %s 的安排", workout_id, schedule_date)
            return True
        except Exception as e:
            logger.error("取消训练安排失败: %s", e)
            return False

    def delete_workout(self, workout_id: str) -> bool:
        """删除训练"""
        self._ensure_client()
        try:
            self.client.delete_workout(workout_id)
            logger.info("已删除训练 %s", workout_id)
            return True
        except Exception as e:
            logger.error("删除训练失败: %s", e)
            return False

    def get_workouts(self) -> list:
        """获取训练列表"""
        self._ensure_client()
        try:
            return self.client.get_workouts() or []
        except Exception as e:
            logger.error("获取训练列表失败: %s", e)
            return []

    # ─── 快捷训练创建 ───

    def quick_run(
        self,
        name: str = "Easy Run",
        warmup_min: int = 10,
        intervals: int = 3,
        interval_min: float = 5,
        recovery_min: float = 2,
        cooldown_min: int = 5,
        hr_zone: int = 4,
        schedule_date: Optional[str] = None,
    ) -> dict:
        """快捷创建跑步训练"""
        workout_data = {
            "name": name,
            "estimated_duration": (warmup_min + intervals * (interval_min + recovery_min) + cooldown_min) * 60,
            "steps": [
                {"type": "warmup", "duration": warmup_min * 60},
                *[
                    step
                    for i in range(intervals)
                    for step in [
                        {"type": "interval", "duration": int(interval_min * 60), "target_type": "heart.rate.zone", "target_value": hr_zone},
                        {"type": "recovery", "duration": recovery_min * 60},
                    ]
                ],
                {"type": "cooldown", "duration": cooldown_min * 60},
            ],
        }
        result = self.create_workout("running", workout_data)

        if result and schedule_date:
            workout_id = result.get("workoutId")
            if workout_id:
                self.schedule_workout(workout_id, schedule_date)

        return result

    def quick_cycling(
        self,
        name: str = "Cycling Workout",
        warmup_min: int = 10,
        intervals: int = 4,
        interval_min: float = 3,
        recovery_min: float = 2,
        cooldown_min: int = 5,
        schedule_date: Optional[str] = None,
    ) -> dict:
        """快捷创建骑行训练"""
        workout_data = {
            "name": name,
            "estimated_duration": (warmup_min + intervals * (interval_min + recovery_min) + cooldown_min) * 60,
            "steps": [
                {"type": "warmup", "duration": warmup_min * 60},
                *[
                    step
                    for i in range(intervals)
                    for step in [
                        {"type": "interval", "duration": int(interval_min * 60)},
                        {"type": "recovery", "duration": recovery_min * 60},
                    ]
                ],
                {"type": "cooldown", "duration": cooldown_min * 60},
            ],
        }
        result = self.create_workout("cycling", workout_data)

        if result and schedule_date:
            workout_id = result.get("workoutId")
            if workout_id:
                self.schedule_workout(workout_id, schedule_date)

        return result

    def quick_swim(
        self,
        name: str = "Swimming Workout",
        warmup_meters: int = 200,
        main_set_meters: int = 1000,
        cooldown_meters: int = 200,
        schedule_date: Optional[str] = None,
    ) -> dict:
        """快捷创建游泳训练"""
        workout_data = {
            "name": name,
            "estimated_duration": 1800,
            "steps": [
                {"type": "warmup", "duration": warmup_meters},
                {"type": "interval", "duration": main_set_meters},
                {"type": "cooldown", "duration": cooldown_meters},
            ],
        }
        result = self.create_workout("swimming", workout_data)

        if result and schedule_date:
            workout_id = result.get("workoutId")
            if workout_id:
                self.schedule_workout(workout_id, schedule_date)

        return result

    # ─── 活动文件导入 ───

    def import_activity_file(self, file_path: str, no_strava: bool = True) -> dict:
        """
        导入活动文件 (FIT/TCX/GPX)

        no_strava: True = import_activity (不上传到 Strava)
                   False = upload_activity (同时上传到 Strava)
        """
        self._ensure_client()
        path = Path(file_path)

        if not path.exists():
            logger.error("文件不存在: %s", file_path)
            return {}

        try:
            if no_strava:
                result = self.client.import_activity(str(path))
            else:
                result = self.client.upload_activity(str(path))

            logger.info("活动文件导入成功: %s", file_path)
            return result or {}
        except Exception as e:
            logger.error("活动文件导入失败: %s", e)
            return {}

    def create_manual_activity(
        self,
        name: str,
        activity_type: str,
        start_time: str,
        duration_sec: int,
        distance_meters: float = 0,
        description: str = "",
        time_zone: str = "Asia/Shanghai",
    ) -> dict:
        """
        创建手动活动记录

        start_time: 格式 'YYYY-MM-DD HH:MM:SS'
        activity_type: Garmin type_key 如 'running', 'cycling', 'swimming' 等
        duration_sec: 持续时间（秒）
        distance_meters: 距离（米）
        """
        self._ensure_client()
        try:
            # garminconnect 0.3.3 API 签名:
            # create_manual_activity(start_datetime, time_zone, type_key, distance_km, duration_min, activity_name)
            distance_km = distance_meters / 1000.0
            duration_min = duration_sec / 60.0
            result = self.client.create_manual_activity(
                start_datetime=start_time,
                time_zone=time_zone,
                type_key=activity_type,
                distance_km=distance_km,
                duration_min=duration_min,
                activity_name=name,
            )
            logger.info("手动活动创建成功: %s", name)
            return result or {}
        except Exception as e:
            logger.error("手动活动创建失败: %s", e)
            return {}

    # ─── 健康数据写入 ───

    def add_weight(self, weight_kg: float, unit_key: str = "kg") -> dict:
        """添加体重记录"""
        self._ensure_client()
        try:
            result = self.client.add_weigh_in(weight=weight_kg, unitKey=unit_key)
            logger.info("体重记录添加成功: %.1f %s", weight_kg, unit_key)
            return result or {}
        except Exception as e:
            logger.error("添加体重记录失败: %s", e)
            return {}

    def add_body_composition(
        self,
        weight_kg: float,
        percent_fat: Optional[float] = None,
        percent_hydration: Optional[float] = None,
        visceral_fat_mass: Optional[float] = None,
        bone_mass: Optional[float] = None,
        muscle_mass: Optional[float] = None,
        basal_met: Optional[float] = None,
        active_met: Optional[float] = None,
        physique_rating: Optional[float] = None,
        metabolic_age: Optional[float] = None,
        timestamp: Optional[str] = None,
    ) -> dict:
        """添加身体成分记录"""
        self._ensure_client()
        try:
            # garminconnect 0.3.3 要求 timestamp 参数
            if timestamp is None:
                timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            result = self.client.add_body_composition(
                timestamp=timestamp,
                weight=weight_kg,
                percent_fat=percent_fat,
                percent_hydration=percent_hydration,
                visceral_fat_mass=visceral_fat_mass,
                bone_mass=bone_mass,
                muscle_mass=muscle_mass,
                basal_met=basal_met,
                active_met=active_met,
                physique_rating=physique_rating,
                metabolic_age=metabolic_age,
            )
            logger.info("身体成分记录添加成功")
            return result or {}
        except Exception as e:
            logger.error("添加身体成分失败: %s", e)
            return {}

    def add_hydration(self, value_ml: float, target_ml: float = 2500.0) -> dict:
        """添加水合数据"""
        self._ensure_client()
        try:
            result = self.client.add_hydration_data(value_in_ml=value_ml)
            logger.info("水合数据添加成功: %.0f ml", value_ml)
            return result or {}
        except Exception as e:
            logger.error("添加水合数据失败: %s", e)
            return {}

    def add_blood_pressure(
        self,
        systolic: int,
        diastolic: int,
        pulse: int,
        notes: str = "",
    ) -> dict:
        """添加血压记录（参数需为整数，systolic: 70-260, diastolic: 40-150）"""
        self._ensure_client()
        try:
            result = self.client.set_blood_pressure(
                systolic=int(systolic),
                diastolic=int(diastolic),
                pulse=int(pulse),
                notes=notes,
            )
            logger.info("血压记录添加成功: %d/%d mmHg", systolic, diastolic)
            return result or {}
        except Exception as e:
            logger.error("添加血压记录失败: %s", e)
            return {}

    # ─── 批量操作 ───

    def import_workout_plan(self, plan: list[dict]) -> list[dict]:
        """
        批量导入训练计划

        plan 格式:
        [
            {
                "workout_type": "running",
                "name": "晨跑",
                "schedule_date": "2026-05-16",
                "steps": [...]
            },
            ...
        ]
        """
        results = []
        for item in plan:
            workout_type = item.get("workout_type", "running")
            schedule_date = item.get("schedule_date")

            result = self.create_workout(workout_type, item)
            if result and schedule_date:
                workout_id = result.get("workoutId")
                if workout_id:
                    self.schedule_workout(workout_id, schedule_date)

            results.append({
                "name": item.get("name", "unnamed"),
                "type": workout_type,
                "date": schedule_date,
                "success": bool(result),
                "result": result,
            })

        logger.info("批量导入完成: %d 成功, %d 失败",
                     sum(1 for r in results if r["success"]),
                     sum(1 for r in results if not r["success"]))
        return results

    def import_workout_plan_from_file(self, file_path: str) -> list[dict]:
        """从 JSON 文件导入训练计划"""
        path = Path(file_path)
        if not path.exists():
            logger.error("训练计划文件不存在: %s", file_path)
            return []

        with open(path, "r", encoding="utf-8") as f:
            plan = json.load(f)

        return self.import_workout_plan(plan)

    def import_coach_plan(self, plan: dict, include_easy: bool = False) -> list[dict]:
        """把 FitnessCoach.plan() 生成的周计划导入 Garmin 训练日程。

        默认只导入 quality / long_run，避免把恢复、力量、休息日也塞进手表。
        """
        pending = self._coach_plan_to_workouts(plan, include_easy=include_easy)
        return self.import_workout_plan(pending)

    def _coach_plan_to_workouts(self, plan: dict, include_easy: bool = False) -> list[dict]:
        workouts = []
        day_offsets = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
        allowed = {"quality", "long_run"}
        if include_easy:
            allowed.update({"easy_run"})

        for week in plan.get("weekly_plan") or []:
            week_start = self._parse_date(week.get("start"))
            if not week_start:
                continue
            for session in week.get("sessions") or []:
                session_type = session.get("type")
                if session_type not in allowed:
                    continue
                target_weekday = day_offsets.get(session.get("day"), week_start.weekday())
                schedule_date = week_start + timedelta(days=(target_weekday - week_start.weekday()) % 7)
                workouts.append(self._session_to_workout(session, schedule_date.isoformat(), week.get("week")))
        return workouts

    def _session_to_workout(self, session: dict, schedule_date: str, week: int | None = None) -> dict:
        session_type = session.get("type") or "run"
        detail = session.get("detail") or ""
        minutes = self._minutes_from_detail(detail, default=45)
        prefix = f"W{week} " if week else ""
        name = f"{prefix}{session_type} {schedule_date}"

        if session_type == "quality":
            steps = [
                {"type": "warmup", "duration": 10 * 60},
                {"type": "interval", "duration": 8 * 60},
                {"type": "recovery", "duration": 3 * 60},
                {"type": "interval", "duration": 8 * 60},
                {"type": "cooldown", "duration": 10 * 60},
            ]
        else:
            body = max(10, minutes - 10)
            steps = [
                {"type": "warmup", "duration": 5 * 60},
                {"type": "interval", "duration": body * 60},
                {"type": "cooldown", "duration": 5 * 60},
            ]

        return {
            "workout_type": "running",
            "name": name,
            "description": detail,
            "estimated_duration": sum(step["duration"] for step in steps),
            "schedule_date": schedule_date,
            "steps": steps,
        }

    def _minutes_from_detail(self, detail: str, default: int = 45) -> int:
        km_match = re.search(r"(\d+(?:\.\d+)?)\s*km", detail, flags=re.IGNORECASE)
        if km_match:
            return int(max(20, float(km_match.group(1)) / 7.5 * 60))
        min_match = re.search(r"(\d+)\s*(?:分钟|min)", detail, flags=re.IGNORECASE)
        if min_match:
            return int(min_match.group(1))
        return default

    def _parse_date(self, value: str | None) -> date | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value[:10]).date()
        except Exception:
            return None
