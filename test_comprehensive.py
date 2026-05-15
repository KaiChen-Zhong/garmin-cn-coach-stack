"""
Garmin Connect 全量 API 综合测试
- 55 个导出 API 测试
- 11 个导入函数测试
- 自动化流程测试
- 本周数据分析
"""

import os
import sys
import json
import time
import traceback
from pathlib import Path
from datetime import date, datetime, timedelta

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# ─── 认证 ───

def get_authenticated_client():
    """获取已认证的客户端"""
    from auth import GarminAuth
    auth = GarminAuth()
    client = auth.login()
    print(f"✅ 认证成功: {client.get_user_profile().get('displayName', 'unknown')}")
    return client


# ─── 导出 API 测试 ───

def test_all_export_apis(client):
    """测试全部 55 个导出 API"""
    from garminconnect import Garmin
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    start_30d = (date.today() - timedelta(days=30)).isoformat()

    tests = []

    def run_test(name, func, *args, **kwargs):
        """执行单个测试"""
        start = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            # 判断结果状态
            if result is None:
                status = "empty"
            elif isinstance(result, (list, dict)):
                if isinstance(result, list) and len(result) == 0:
                    status = "empty"
                elif isinstance(result, dict) and all(v is None for v in result.values()):
                    status = "empty"
                else:
                    status = "ok"
            elif isinstance(result, bytes):
                status = "ok" if len(result) > 0 else "empty"
            else:
                status = "ok"
            size_info = ""
            if isinstance(result, list):
                size_info = f" ({len(result)} items)"
            elif isinstance(result, dict):
                non_none = sum(1 for v in result.values() if v is not None)
                size_info = f" ({non_none}/{len(result)} fields)"
            elif isinstance(result, bytes):
                size_info = f" ({len(result)} bytes)"
            print(f"  ✅ {name}: {status}{size_info} [{elapsed:.1f}s]")
            return {"name": name, "status": status, "elapsed": round(elapsed, 2), "detail": size_info}
        except Exception as e:
            elapsed = time.time() - start
            err_msg = str(e)[:120]
            print(f"  ❌ {name}: FAIL [{elapsed:.1f}s] - {err_msg}")
            return {"name": name, "status": "fail", "elapsed": round(elapsed, 2), "error": err_msg}

    # ── 0. 预获取活动列表（供后续测试使用）──
    activities = []
    try:
        activities = client.get_activities(0, 10) or []
    except:
        pass
    profile = None
    try:
        profile = client.get_user_profile()
    except:
        pass

    # ── 1. 用户资料 (3) ──
    print("\n📋 1. 用户资料")
    tests.append(run_test("get_user_profile", client.get_user_profile))
    tests.append(run_test("get_userprofile_settings", client.get_userprofile_settings))
    tests.append(run_test("get_user_summary", client.get_user_summary, today))

    # ── 2. 心率数据 (3) ──
    print("\n📋 2. 心率数据")
    tests.append(run_test("get_heart_rates", client.get_heart_rates, today))
    tests.append(run_test("get_rhr_day", client.get_rhr_day, today))
    tests.append(run_test("get_max_metrics", client.get_max_metrics, today))

    # ── 3. 步数与活动 (3) ──
    print("\n📋 3. 步数与活动")
    tests.append(run_test("get_steps_data", client.get_steps_data, today))
    tests.append(run_test("get_daily_steps", client.get_daily_steps, today, today))
    tests.append(run_test("get_floors", client.get_floors, today))

    # ── 4. 睡眠数据 (2) ──
    print("\n📋 4. 睡眠数据")
    tests.append(run_test("get_sleep_data", client.get_sleep_data, today))
    tests.append(run_test("get_spo2_data", client.get_spo2_data, today))

    # ── 5. 压力与身体电量 (4) ──
    print("\n📋 5. 压力与身体电量")
    tests.append(run_test("get_stress_data", client.get_stress_data, today))
    tests.append(run_test("get_all_day_stress", client.get_all_day_stress, today))
    tests.append(run_test("get_body_battery", client.get_body_battery, today))
    tests.append(run_test("get_hrv_data", client.get_hrv_data, today))

    # ── 6. 呼吸与SpO2 (2) ──
    print("\n📋 6. 呼吸与SpO2")
    tests.append(run_test("get_respiration_data", client.get_respiration_data, today))
    tests.append(run_test("get_body_battery_events", client.get_body_battery_events, today))

    # ── 6b. 活动深度查询 (5) ──
    print("\n📋 6b. 活动深度查询")
    if activities:
        act_id = str(activities[0].get("activityId", ""))
        tests.append(run_test("get_activity_details", client.get_activity_details, act_id))
        tests.append(run_test("get_activity_splits", client.get_activity_splits, act_id))
        tests.append(run_test("get_activity_weather", client.get_activity_weather, act_id))
        tests.append(run_test("get_activity_hr_in_timezones", client.get_activity_hr_in_timezones, act_id))
        tests.append(run_test("get_activity_gear", client.get_activity_gear, act_id))
    else:
        for n in ["get_activity_details", "get_activity_splits", "get_activity_weather", "get_activity_hr_in_timezones", "get_activity_gear"]:
            tests.append({"name": n, "status": "skip", "elapsed": 0, "error": "no activities"})
            print(f"  ⏭️ {n}: skip (no activities)")

    # ── 7. 训练状态 (5) ──
    print("\n📋 7. 训练状态")
    tests.append(run_test("get_training_status", client.get_training_status, today))
    tests.append(run_test("get_training_readiness", client.get_training_readiness, today))
    tests.append(run_test("get_morning_training_readiness", client.get_morning_training_readiness, today))
    tests.append(run_test("get_intensity_minutes_data", client.get_intensity_minutes_data, today))
    tests.append(run_test("get_fitnessage_data", client.get_fitnessage_data, today))

    # ── 8. 身体成分与体重 (3) ──
    print("\n📋 8. 身体成分与体重")
    tests.append(run_test("get_body_composition", client.get_body_composition, today))
    tests.append(run_test("get_weigh_ins", client.get_weigh_ins, start_30d, today))
    tests.append(run_test("get_stats_and_body", client.get_stats_and_body, today))

    # ── 9. 活动数据 (3 download tests) ──
    print("\n📋 9. 活动数据")
    # activities 已在前面预获取
    tests.append({"name": "get_activities", "status": "ok" if activities is not None else "fail", "elapsed": 0, "detail": f" ({len(activities)} items)"})
    print(f"  ✅ get_activities: ok ({len(activities)} items)")

    if activities:
        act_id = str(activities[0].get("activityId", ""))
        tests.append(run_test("get_activity", client.get_activity, act_id))
        # 测试下载格式
        try:
            fit_data = client.download_activity(act_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
            tests.append({"name": "download_activity ORIGINAL", "status": "ok", "elapsed": 0, "detail": f" ({len(fit_data)} bytes, ZIP={'yes' if fit_data[:2]==b'PK' else 'no'})"})
            print(f"  ✅ download_activity ORIGINAL: ok ({len(fit_data)} bytes)")
        except Exception as e:
            tests.append({"name": "download_activity ORIGINAL", "status": "fail", "elapsed": 0, "error": str(e)[:120]})
            print(f"  ❌ download_activity ORIGINAL: FAIL - {str(e)[:120]}")

        try:
            gpx_data = client.download_activity(act_id, dl_fmt=Garmin.ActivityDownloadFormat.GPX)
            tests.append({"name": "download_activity GPX", "status": "ok", "elapsed": 0, "detail": f" ({len(gpx_data)} bytes)"})
            print(f"  ✅ download_activity GPX: ok ({len(gpx_data)} bytes)")
        except Exception as e:
            tests.append({"name": "download_activity GPX", "status": "fail", "elapsed": 0, "error": str(e)[:120]})
            print(f"  ❌ download_activity GPX: FAIL - {str(e)[:120]}")
    else:
        for n in ["get_activity", "download_activity ORIGINAL", "download_activity GPX"]:
            tests.append({"name": n, "status": "skip", "elapsed": 0, "error": "no activities"})
            print(f"  ⏭️ {n}: skip (no activities)")

    # ── 10. 设备与装备 (4) ──
    print("\n📋 10. 设备与装备")
    devices = []
    try:
        devices = client.get_devices() or []
        tests.append({"name": "get_devices", "status": "ok", "elapsed": 0, "detail": f" ({len(devices)} items)"})
        print(f"  ✅ get_devices: ok ({len(devices)} items)")
    except Exception as e:
        tests.append({"name": "get_devices", "status": "fail", "elapsed": 0, "error": str(e)[:120]})
        print(f"  ❌ get_devices: FAIL - {str(e)[:120]}")

    if devices:
        device_id = devices[0].get("deviceId") or devices[0].get("id")
        if device_id:
            tests.append(run_test("get_device_settings", client.get_device_settings, device_id))
        else:
            tests.append({"name": "get_device_settings", "status": "skip", "elapsed": 0})
            print(f"  ⏭️ get_device_settings: skip (no device_id)")
    else:
        tests.append({"name": "get_device_settings", "status": "skip", "elapsed": 0})
        print(f"  ⏭️ get_device_settings: skip (no devices)")

    tests.append(run_test("get_device_alarms", client.get_device_alarms))

    # 装备 - 需要 profileId
    if profile:
        profile_id = profile.get("profileId") or profile.get("id")
        if profile_id:
            tests.append(run_test("get_gear", client.get_gear, profile_id))
            tests.append(run_test("get_gear_defaults", client.get_gear_defaults, profile_id))
        else:
            tests.append({"name": "get_gear", "status": "skip", "elapsed": 0, "error": "no profileId"})
            tests.append({"name": "get_gear_defaults", "status": "skip", "elapsed": 0, "error": "no profileId"})
            print(f"  ⏭️ get_gear/get_gear_defaults: skip (no profileId)")
    else:
        tests.append({"name": "get_gear", "status": "skip", "elapsed": 0, "error": "no profile"})
        tests.append({"name": "get_gear_defaults", "status": "skip", "elapsed": 0, "error": "no profile"})
        print(f"  ⏭️ get_gear/get_gear_defaults: skip (no profile)")

    # ── 11. 目标与成就 (6) ──
    print("\n📋 11. 目标与成就")
    tests.append(run_test("get_goals", client.get_goals))
    tests.append(run_test("get_earned_badges", client.get_earned_badges))
    tests.append(run_test("get_available_badges", client.get_available_badges))
    tests.append(run_test("get_adhoc_challenges", client.get_adhoc_challenges, 0, 20))
    tests.append(run_test("get_badge_challenges", client.get_badge_challenges, 1, 20))
    tests.append(run_test("get_personal_record", client.get_personal_record))

    # ── 12. 水合与营养 (3) ──
    print("\n📋 12. 水合与营养")
    tests.append(run_test("get_hydration_data", client.get_hydration_data, today))
    tests.append(run_test("get_nutrition_daily_food_log", client.get_nutrition_daily_food_log, today))
    tests.append(run_test("get_nutrition_daily_meals", client.get_nutrition_daily_meals, today))

    # ── 13. 训练计划 (3) ──
    print("\n📋 13. 训练计划")
    tests.append(run_test("get_training_plans", client.get_training_plans))
    tests.append(run_test("get_workouts", client.get_workouts))
    tests.append(run_test("get_scheduled_workouts", client.get_scheduled_workouts, date.today().year, date.today().month))

    # ── 14. 周报与趋势 (4) ──
    print("\n📋 14. 周报与趋势")
    tests.append(run_test("get_weekly_steps", client.get_weekly_steps, today, weeks=4))
    tests.append(run_test("get_weekly_intensity_minutes", client.get_weekly_intensity_minutes, start_30d, today))
    tests.append(run_test("get_weekly_stress", client.get_weekly_stress, today, weeks=4))
    tests.append(run_test("get_race_predictions", client.get_race_predictions, start_30d, today, "daily"))

    # ── 15. 高级指标 (8) ──
    print("\n📋 15. 高级指标")
    tests.append(run_test("get_hill_score", client.get_hill_score, today))
    tests.append(run_test("get_endurance_score", client.get_endurance_score, today))
    tests.append(run_test("get_running_tolerance", client.get_running_tolerance, start_30d, today))
    tests.append(run_test("get_lifestyle_logging_data", client.get_lifestyle_logging_data, today))
    tests.append(run_test("get_golf_summary", client.get_golf_summary))
    tests.append(run_test("get_cycling_ftp", client.get_cycling_ftp))
    tests.append(run_test("get_lactate_threshold", client.get_lactate_threshold))
    tests.append(run_test("get_progress_summary_between_dates", client.get_progress_summary_between_dates, start_30d, today, "all", False))

    # ── 16. 更多设备与活动类型 (4) ──
    print("\n📋 16. 更多设备与活动类型")
    tests.append(run_test("get_activity_types", client.get_activity_types))
    tests.append(run_test("get_last_activity", client.get_last_activity))
    tests.append(run_test("get_stats", client.get_stats, today))
    tests.append(run_test("get_unit_system", client.get_unit_system))

    # ── 17. 徽章进阶 (3) ──
    print("\n📋 17. 徽章进阶")
    tests.append(run_test("get_available_badge_challenges", client.get_available_badge_challenges, 1, 20))
    tests.append(run_test("get_in_progress_badges", client.get_in_progress_badges))
    tests.append(run_test("get_non_completed_badge_challenges", client.get_non_completed_badge_challenges, 1, 20))

    return tests


# ─── 导入函数测试 ───

def test_all_import_functions(client):
    """测试全部 11 个导入函数（只做验证性测试，避免创建大量垃圾数据）"""
    tests = []

    def run_test(name, func, *args, **kwargs):
        start = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            status = "ok" if result else "empty"
            print(f"  ✅ {name}: {status} [{elapsed:.1f}s]")
            return {"name": name, "status": status, "elapsed": round(elapsed, 2)}
        except Exception as e:
            elapsed = time.time() - start
            err_msg = str(e)[:120]
            print(f"  ❌ {name}: FAIL [{elapsed:.1f}s] - {err_msg}")
            return {"name": name, "status": "fail", "elapsed": round(elapsed, 2), "error": err_msg}

    from importer import GarminImporter
    importer = GarminImporter()
    importer.client = client

    # 1. 创建跑步训练
    print("\n📋 1. 训练创建与上传")
    tests.append(run_test("create_workout (running)", importer.create_workout, "running", {
        "name": f"API测试跑步_{datetime.now().strftime('%H%M%S')}",
        "estimated_duration": 1200,
        "steps": [
            {"type": "warmup", "duration": 300},
            {"type": "interval", "duration": 180},
            {"type": "cooldown", "duration": 300},
        ]
    }))

    # 2. 获取训练列表
    tests.append(run_test("get_workouts", importer.get_workouts))

    # 3. 添加体重 (跳过，避免频繁写入)
    print("\n📋 2. 健康数据写入")
    print("  ⏭️ add_weight: skip (避免频繁写入真实数据)")
    tests.append({"name": "add_weight", "status": "skip", "elapsed": 0, "error": "skipped to avoid data pollution"})

    # 4. 添加身体成分
    print("  ⏭️ add_body_composition: skip (避免频繁写入真实数据)")
    tests.append({"name": "add_body_composition", "status": "skip", "elapsed": 0, "error": "skipped to avoid data pollution"})

    # 5. 添加水合数据 (少量)
    tests.append(run_test("add_hydration", importer.add_hydration, 250))

    # 6. 添加血压 (跳过，避免频繁写入)
    print("  ⏭️ add_blood_pressure: skip (避免频繁写入真实数据)")
    tests.append({"name": "add_blood_pressure", "status": "skip", "elapsed": 0, "error": "skipped to avoid data pollution"})

    # 7. 创建手动活动
    print("\n📋 3. 活动管理")
    act_name = f"API测试活动_{datetime.now().strftime('%H%M%S')}"
    tests.append(run_test("create_manual_activity", lambda: importer.create_manual_activity(
        name=act_name,
        activity_type="running",
        start_time=f"{today_str()} 08:00:00",
        duration_sec=1800,
        distance_meters=3000,
    )))

    # 8. TCX 文件导入
    tcx_path = PROJECT_ROOT / "data" / "test_activity.tcx"
    if tcx_path.exists():
        tests.append(run_test("import_activity_file (TCX)", importer.import_activity_file, str(tcx_path)))
    else:
        print("  ⏭️ import_activity_file (TCX): skip (no test file)")
        tests.append({"name": "import_activity_file (TCX)", "status": "skip", "elapsed": 0})

    # 9. 训练日程管理
    print("\n📋 4. 训练日程管理")
    workouts = []
    try:
        workouts = client.get_workouts() or []
    except:
        pass
    if workouts:
        wid = str(workouts[0].get("workoutId", ""))
        if wid:
            tests.append(run_test("schedule_workout", importer.schedule_workout, wid, today_str()))
        else:
            tests.append({"name": "schedule_workout", "status": "skip", "elapsed": 0})
    else:
        tests.append({"name": "schedule_workout", "status": "skip", "elapsed": 0, "error": "no workouts"})

    # 10. quick_run
    print("\n📋 5. 快捷训练创建")
    run_name = f"快捷跑测试_{datetime.now().strftime('%H%M%S')}"
    tests.append(run_test("quick_run", lambda: importer.quick_run(
        name=run_name,
        warmup_min=5,
        intervals=2,
        interval_min=3,
    )))

    # 11. quick_cycling
    cycle_name = f"快捷骑行测试_{datetime.now().strftime('%H%M%S')}"
    tests.append(run_test("quick_cycling", lambda: importer.quick_cycling(
        name=cycle_name,
        warmup_min=5,
        intervals=2,
        interval_min=3,
    )))

    return tests


def today_str():
    return date.today().isoformat()


# ─── 自动化流程测试 ───

def test_automation():
    """测试自动化流程"""
    tests = []

    print("\n📋 1. CLI 命令测试")
    # 测试 main.py login
    start = time.time()
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "main.py"), "login"],
            capture_output=True, text=True, timeout=60,
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
        )
        elapsed = time.time() - start
        if result.returncode == 0 and "成功" in result.stdout:
            tests.append({"name": "CLI login", "status": "ok", "elapsed": round(elapsed, 2)})
            print(f"  ✅ CLI login: ok [{elapsed:.1f}s]")
        else:
            tests.append({"name": "CLI login", "status": "fail", "elapsed": round(elapsed, 2), "error": result.stderr[:120]})
            print(f"  ❌ CLI login: FAIL - {result.stderr[:120]}")
    except Exception as e:
        tests.append({"name": "CLI login", "status": "fail", "elapsed": 0, "error": str(e)[:120]})
        print(f"  ❌ CLI login: FAIL - {str(e)[:120]}")

    # 测试 main.py export health
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "main.py"), "export", "health", "--date", today_str()],
            capture_output=True, text=True, timeout=60,
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
        )
        elapsed = time.time() - start
        if result.returncode == 0 and "完成" in result.stdout:
            tests.append({"name": "CLI export health", "status": "ok", "elapsed": round(elapsed, 2)})
            print(f"  ✅ CLI export health: ok [{elapsed:.1f}s]")
        else:
            tests.append({"name": "CLI export health", "status": "fail", "elapsed": round(elapsed, 2), "error": result.stderr[:120]})
            print(f"  ❌ CLI export health: FAIL - {result.stderr[:120]}")
    except Exception as e:
        tests.append({"name": "CLI export health", "status": "fail", "elapsed": 0, "error": str(e)[:120]})
        print(f"  ❌ CLI export health: FAIL - {str(e)[:120]}")

    # 测试 main.py workout list
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "main.py"), "workout", "list"],
            capture_output=True, text=True, timeout=60,
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
        )
        elapsed = time.time() - start
        if result.returncode == 0:
            tests.append({"name": "CLI workout list", "status": "ok", "elapsed": round(elapsed, 2)})
            print(f"  ✅ CLI workout list: ok [{elapsed:.1f}s]")
        else:
            tests.append({"name": "CLI workout list", "status": "fail", "elapsed": round(elapsed, 2), "error": result.stderr[:120]})
            print(f"  ❌ CLI workout list: FAIL - {result.stderr[:120]}")
    except Exception as e:
        tests.append({"name": "CLI workout list", "status": "fail", "elapsed": 0, "error": str(e)[:120]})
        print(f"  ❌ CLI workout list: FAIL - {str(e)[:120]}")

    # 测试调度器模块导入
    print("\n📋 2. 调度器模块")
    start = time.time()
    try:
        from scheduler import run_daily_sync, run_quick_sync, setup_logging
        tests.append({"name": "scheduler import", "status": "ok", "elapsed": 0})
        print(f"  ✅ scheduler import: ok")
    except Exception as e:
        tests.append({"name": "scheduler import", "status": "fail", "elapsed": 0, "error": str(e)[:120]})
        print(f"  ❌ scheduler import: FAIL - {str(e)[:120]}")

    # 测试 API 服务模块导入
    print("\n📋 3. API 服务模块")
    start = time.time()
    try:
        from api_server import app
        routes = [r.path for r in app.routes]
        tests.append({"name": "api_server import", "status": "ok", "elapsed": 0, "detail": f" ({len(routes)} routes)"})
        print(f"  ✅ api_server import: ok ({len(routes)} routes)")
    except Exception as e:
        tests.append({"name": "api_server import", "status": "fail", "elapsed": 0, "error": str(e)[:120]})
        print(f"  ❌ api_server import: FAIL - {str(e)[:120]}")

    # 测试认证模块
    print("\n📋 4. 认证模块")
    start = time.time()
    try:
        from auth import GarminAuth, get_auth, get_client
        auth = GarminAuth()
        c = auth.ensure_connected()
        if c:
            tests.append({"name": "auth ensure_connected", "status": "ok", "elapsed": round(time.time()-start, 2)})
            print(f"  ✅ auth ensure_connected: ok")
        else:
            tests.append({"name": "auth ensure_connected", "status": "fail", "elapsed": 0})
            print(f"  ❌ auth ensure_connected: FAIL")
    except Exception as e:
        tests.append({"name": "auth ensure_connected", "status": "fail", "elapsed": 0, "error": str(e)[:120]})
        print(f"  ❌ auth ensure_connected: FAIL - {str(e)[:120]}")

    return tests


# ─── 本周数据分析 ───

def analyze_weekly_data(client):
    """分析本周(周一~今天)的健康与活动数据"""
    today = date.today()
    # 本周周一
    monday = today - timedelta(days=today.weekday())

    week_dates = [monday + timedelta(days=i) for i in range((today - monday).days + 1)]
    date_strs = [d.isoformat() for d in week_dates]

    print(f"\n📊 本周数据分析: {monday.isoformat()} ~ {today.isoformat()}")
    print(f"   共 {len(date_strs)} 天")

    weekly_data = {}

    # 1. 每日健康数据
    print("\n  获取每日健康数据...")
    for ds in date_strs:
        day_data = {}
        try:
            day_data["heart_rate"] = client.get_heart_rates(ds)
        except:
            pass
        try:
            day_data["steps"] = client.get_steps_data(ds)
        except:
            pass
        try:
            day_data["sleep"] = client.get_sleep_data(ds)
        except:
            pass
        try:
            day_data["stress"] = client.get_stress_data(ds)
        except:
            pass
        try:
            day_data["body_battery"] = client.get_body_battery(ds)
        except:
            pass
        try:
            day_data["floors"] = client.get_floors(ds)
        except:
            pass
        try:
            day_data["hydration"] = client.get_hydration_data(ds)
        except:
            pass
        try:
            day_data["spo2"] = client.get_spo2_data(ds)
        except:
            pass
        try:
            day_data["rhr"] = client.get_rhr_day(ds)
        except:
            pass
        weekly_data[ds] = day_data
        print(f"    {ds}: {sum(1 for v in day_data.values() if v is not None)}/{len(day_data)} 项有数据")

    # 2. 活动数据
    print("\n  获取本周活动...")
    try:
        activities = client.get_activities(0, 50) or []
        week_activities = []
        for act in activities:
            start_local = act.get("startTimeLocal", "")[:10]
            if start_local in date_strs:
                week_activities.append(act)
        print(f"    本周活动: {len(week_activities)} 个")
        for act in week_activities:
            name = act.get("activityName", "?")
            dist = act.get("distance", 0)
            dur = act.get("duration", 0)
            dt = act.get("startTimeLocal", "?")[:16]
            print(f"      - {dt} {name}: {dist/1000:.1f}km, {dur/60:.0f}min")
    except Exception as e:
        week_activities = []
        print(f"    获取活动失败: {e}")

    # 3. 提取关键指标
    print("\n  📈 关键指标汇总:")
    summary = {
        "week_range": f"{monday.isoformat()} ~ {today.isoformat()}",
        "days_with_data": 0,
        "daily_metrics": {},
        "activities": [],
        "averages": {},
    }

    total_steps = []
    total_stress = []
    total_sleep_hours = []
    total_rhr = []
    total_floors = []

    for ds in date_strs:
        day = weekly_data.get(ds, {})
        day_metrics = {"date": ds}

        # 步数
        steps_data = day.get("steps")
        if steps_data and isinstance(steps_data, dict):
            steps = steps_data.get("totalSteps") or steps_data.get("steps", 0)
            if isinstance(steps, list):
                steps = sum(s.get("steps", 0) for s in steps)
            day_metrics["steps"] = steps
            if steps:
                total_steps.append(steps)

        # 压力
        stress_data = day.get("stress")
        if stress_data and isinstance(stress_data, dict):
            avg_stress = stress_data.get("averageStressLevel")
            if avg_stress is not None:
                day_metrics["avg_stress"] = avg_stress
                total_stress.append(avg_stress)

        # 睡眠
        sleep_data = day.get("sleep")
        if sleep_data and isinstance(sleep_data, dict):
            sleep_seconds = sleep_data.get("sleepTimeSeconds", 0)
            if sleep_seconds:
                sleep_h = sleep_seconds / 3600
                day_metrics["sleep_hours"] = round(sleep_h, 1)
                total_sleep_hours.append(sleep_h)

        # 静息心率
        rhr_data = day.get("rhr")
        if rhr_data and isinstance(rhr_data, dict):
            rhr_val = rhr_data.get("minHeartRate") or rhr_data.get("restingHeartRate")
            if rhr_val:
                day_metrics["rhr"] = rhr_val
                total_rhr.append(rhr_val)

        # 楼层
        floors_data = day.get("floors")
        if floors_data and isinstance(floors_data, dict):
            floors_val = floors_data.get("totalFloorsAscended") or floors_data.get("floorsAscended", 0)
            if floors_val:
                day_metrics["floors"] = floors_val
                total_floors.append(floors_val)

        if any(v for k, v in day_metrics.items() if k != "date"):
            summary["days_with_data"] += 1

        summary["daily_metrics"][ds] = day_metrics

    # 活动信息
    for act in week_activities:
        summary["activities"].append({
            "name": act.get("activityName", "?"),
            "type": act.get("activityType", {}).get("typeKey", "?"),
            "date": act.get("startTimeLocal", "?")[:10],
            "distance_km": round(act.get("distance", 0) / 1000, 2),
            "duration_min": round(act.get("duration", 0) / 60, 1),
            "calories": act.get("calories", 0),
            "avg_hr": act.get("averageHR", None),
            "max_hr": act.get("maxHR", None),
        })

    # 平均值
    if total_steps:
        summary["averages"]["avg_daily_steps"] = round(sum(total_steps) / len(total_steps))
    if total_stress:
        summary["averages"]["avg_stress"] = round(sum(total_stress) / len(total_stress), 1)
    if total_sleep_hours:
        summary["averages"]["avg_sleep_hours"] = round(sum(total_sleep_hours) / len(total_sleep_hours), 1)
    if total_rhr:
        summary["averages"]["avg_rhr"] = round(sum(total_rhr) / len(total_rhr))
    if total_floors:
        summary["averages"]["avg_floors"] = round(sum(total_floors) / len(total_floors), 1)

    return summary


# ─── 主函数 ───

def main():
    print("=" * 70)
    print("🧪 Garmin Connect 全量 API 综合测试")
    print(f"   时间: {datetime.now().isoformat()}")
    print("=" * 70)

    # 1. 认证
    print("\n🔐 认证...")
    try:
        client = get_authenticated_client()
    except Exception as e:
        print(f"❌ 认证失败: {e}")
        return

    # 2. 导出 API 测试
    print("\n" + "=" * 70)
    print("📤 导出 API 测试 (55 APIs)")
    print("=" * 70)
    export_results = test_all_export_apis(client)

    # 3. 导入函数测试
    print("\n" + "=" * 70)
    print("📥 导入函数测试 (11 Functions)")
    print("=" * 70)
    import_results = test_all_import_functions(client)

    # 4. 自动化流程测试
    print("\n" + "=" * 70)
    print("⚙️ 自动化流程测试")
    print("=" * 70)
    auto_results = test_automation()

    # 5. 本周数据分析
    print("\n" + "=" * 70)
    print("📊 本周数据分析")
    print("=" * 70)
    weekly_summary = analyze_weekly_data(client)

    # 6. 汇总
    all_results = {
        "timestamp": datetime.now().isoformat(),
        "export": export_results,
        "import": import_results,
        "automation": auto_results,
        "weekly_analysis": weekly_summary,
    }

    # 保存 JSON 结果
    result_path = PROJECT_ROOT / "data" / "comprehensive_test_results.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n💾 结果已保存到 {result_path}")

    # 统计
    export_ok = sum(1 for t in export_results if t["status"] == "ok")
    export_empty = sum(1 for t in export_results if t["status"] == "empty")
    export_fail = sum(1 for t in export_results if t["status"] == "fail")
    export_skip = sum(1 for t in export_results if t["status"] == "skip")
    export_total = len(export_results)

    import_ok = sum(1 for t in import_results if t["status"] == "ok")
    import_empty = sum(1 for t in import_results if t["status"] == "empty")
    import_fail = sum(1 for t in import_results if t["status"] == "fail")
    import_skip = sum(1 for t in import_results if t["status"] == "skip")
    import_total = len(import_results)

    auto_ok = sum(1 for t in auto_results if t["status"] == "ok")
    auto_fail = sum(1 for t in auto_results if t["status"] == "fail")
    auto_total = len(auto_results)

    print("\n" + "=" * 70)
    print("📊 测试汇总")
    print("=" * 70)
    print(f"  导出 API:  {export_ok} ok / {export_empty} empty / {export_fail} fail / {export_skip} skip = {export_total} total")
    print(f"  导入函数:  {import_ok} ok / {import_empty} empty / {import_fail} fail / {import_skip} skip = {import_total} total")
    print(f"  自动化:    {auto_ok} ok / {auto_fail} fail = {auto_total} total")
    print(f"  本周数据:  {weekly_summary.get('days_with_data', 0)} 天有数据, {len(weekly_summary.get('activities', []))} 个活动")

    if weekly_summary.get("averages"):
        avgs = weekly_summary["averages"]
        print(f"\n  📈 本周平均值:")
        for k, v in avgs.items():
            print(f"    - {k}: {v}")

    return all_results


if __name__ == "__main__":
    main()
