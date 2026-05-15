"""全面测试 Garmin Connect 导出/导入功能"""
import os
import sys
import json
from pathlib import Path
from datetime import date, timedelta

# Setup
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from auth import GarminAuth
from garminconnect import Garmin

auth = GarminAuth()
client = auth.login()
today = date.today().isoformat()
start = (date.today() - timedelta(days=30)).isoformat()

results = {}

def test_api(category, name, func):
    """测试单个 API 调用"""
    key = f"{category}.{name}"
    try:
        data = func()
        has_data = bool(data) if data is not None else False
        if isinstance(data, list):
            size_info = f"{len(data)} items"
        elif isinstance(data, dict):
            size_info = f"{len(data)} keys"
        elif isinstance(data, bytes):
            size_info = f"{len(data)} bytes"
        else:
            size_info = "empty"
        status = f"OK (data={has_data}, {size_info})"
        results[key] = status
        print(f"  {name}: {status}")
        return data
    except Exception as e:
        status = f"FAIL: {e}"
        results[key] = status
        print(f"  {name}: {status}")
        return None

# ============================================================
# [1/12] 用户资料
# ============================================================
print("=" * 60)
print("[1/12] 用户资料")
test_api("user_profile", "get_user_profile", lambda: client.get_user_profile())
test_api("user_profile", "get_userprofile_settings", lambda: client.get_userprofile_settings())

# ============================================================
# [2/12] 每日健康数据
# ============================================================
print("=" * 60)
print("[2/12] 每日健康数据")
for name, method in [
    ("heart_rate", client.get_heart_rates),
    ("steps", client.get_steps_data),
    ("sleep", client.get_sleep_data),
    ("stress", client.get_stress_data),
    ("body_battery", client.get_body_battery),
    ("floors", client.get_floors),
    ("respiration", client.get_respiration_data),
    ("spo2", client.get_spo2_data),
    ("hrv", client.get_hrv_data),
]:
    test_api("daily_health", name, lambda m=method: m(today))

# ============================================================
# [3/12] 高级健康指标
# ============================================================
print("=" * 60)
print("[3/12] 高级健康指标")
for name, method in [
    ("training_readiness", client.get_training_readiness),
    ("training_status", client.get_training_status),
    ("body_composition", client.get_body_composition),
    ("all_day_stress", client.get_all_day_stress),
    ("hrv_data", client.get_hrv_data),
    ("rhr", client.get_rhr_day),
    ("stats_and_body", client.get_stats_and_body),
    ("intensity_minutes", client.get_intensity_minutes_data),
    ("hill_score", client.get_hill_score),
    ("endurance_score", client.get_endurance_score),
    ("fitnessage", client.get_fitnessage_data),
    ("lifestyle_logging", client.get_lifestyle_logging_data),
    ("max_metrics", client.get_max_metrics),
    ("morning_training_readiness", client.get_morning_training_readiness),
]:
    test_api("advanced_health", name, lambda m=method: m(today))

# Date range methods
for name, method in [
    ("race_predictions_no_params", lambda: client.get_race_predictions()),
    ("race_predictions_with_params", lambda: client.get_race_predictions(start, today, "daily")),
    ("running_tolerance", lambda: client.get_running_tolerance(start, today)),
]:
    test_api("advanced_health", name, method)

# ============================================================
# [4/12] 历史趋势
# ============================================================
print("=" * 60)
print("[4/12] 历史趋势")
test_api("historical", "weekly_steps", lambda: client.get_weekly_steps(today, weeks=4))
test_api("historical", "weekly_intensity_minutes", lambda: client.get_weekly_intensity_minutes(start, today))
test_api("historical", "weekly_stress", lambda: client.get_weekly_stress(today, weeks=4))

# ============================================================
# [5/12] 活动数据
# ============================================================
print("=" * 60)
print("[5/12] 活动数据")
activities = test_api("activities", "get_activities", lambda: client.get_activities(0, 50))
activity_id = None
if activities and isinstance(activities, list) and len(activities) > 0:
    activity_id = str(activities[0].get("activityId", ""))
    print(f"    Latest activity: {activities[0].get('activityName', '?')} ID={activity_id}")
    test_api("activities", "get_activity_detail", lambda: client.get_activity(activity_id))
    test_api("activities", "download_original", lambda: client.download_activity(activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL))
    test_api("activities", "download_gpx", lambda: client.download_activity(activity_id, dl_fmt=Garmin.ActivityDownloadFormat.GPX))
    test_api("activities", "download_tcx", lambda: client.download_activity(activity_id, dl_fmt=Garmin.ActivityDownloadFormat.TCX))
else:
    print("    No activities found, skipping detail tests")

# ============================================================
# [6/12] 身体成分
# ============================================================
print("=" * 60)
print("[6/12] 身体成分")
test_api("body_composition", "get_body_composition", lambda: client.get_body_composition(today))
test_api("body_composition", "get_weigh_ins", lambda: client.get_weigh_ins(today, today))

# ============================================================
# [7/12] 目标与成就
# ============================================================
print("=" * 60)
print("[7/12] 目标与成就")
test_api("goals", "get_goals", lambda: client.get_goals())
test_api("goals", "get_earned_badges", lambda: client.get_earned_badges())
test_api("goals", "get_adhoc_challenges", lambda: client.get_adhoc_challenges(0, 20))
test_api("goals", "get_personal_record", lambda: client.get_personal_record())
test_api("goals", "get_badge_challenges", lambda: client.get_badge_challenges(1, 20))
test_api("goals", "get_available_badges", lambda: client.get_available_badges())

# ============================================================
# [8/12] 设备信息
# ============================================================
print("=" * 60)
print("[8/12] 设备信息")
devices = test_api("device", "get_devices", lambda: client.get_devices())
device_id = None
if devices and isinstance(devices, list) and len(devices) > 0:
    device_id = devices[0].get("deviceId") or devices[0].get("id")
    print(f"    Device: {devices[0].get('productDisplayName', '?')} ID={device_id}")
    test_api("device", "get_device_settings", lambda: client.get_device_settings(device_id))
else:
    print("    No devices found, skipping device settings")
test_api("device", "get_device_alarms", lambda: client.get_device_alarms())

# ============================================================
# [9/12] 装备
# ============================================================
print("=" * 60)
print("[9/12] 装备")
profile = None
try:
    profile = client.get_user_profile()
except:
    pass
profile_id = None
if isinstance(profile, dict):
    profile_id = profile.get("profileId") or profile.get("id")
print(f"    profile_id = {profile_id}")
if profile_id:
    test_api("gear", "get_gear", lambda: client.get_gear(profile_id))
    test_api("gear", "get_gear_defaults", lambda: client.get_gear_defaults(profile_id))
else:
    print("    No profileId, skipping gear tests")
    results["gear.get_gear"] = "SKIP: no profileId"
    results["gear.get_gear_defaults"] = "SKIP: no profileId"

# ============================================================
# [10/12] 水合与营养
# ============================================================
print("=" * 60)
print("[10/12] 水合与营养")
test_api("hydration", "get_hydration_data", lambda: client.get_hydration_data(today))
test_api("hydration", "get_nutrition_daily_food_log", lambda: client.get_nutrition_daily_food_log(today))

# ============================================================
# [11/12] 训练计划
# ============================================================
print("=" * 60)
print("[11/12] 训练计划")
test_api("training", "get_training_plans", lambda: client.get_training_plans())
test_api("training", "get_workouts", lambda: client.get_workouts())
test_api("training", "get_scheduled_workouts", lambda: client.get_scheduled_workouts(date.today().year, date.today().month))

# ============================================================
# [12/12] 高尔夫
# ============================================================
print("=" * 60)
print("[12/12] 高尔夫")
test_api("golf", "get_golf_summary", lambda: client.get_golf_summary())

# ============================================================
# Summary
# ============================================================
print("=" * 60)
print("测试汇总")
ok_count = sum(1 for v in results.values() if v.startswith("OK"))
fail_count = sum(1 for v in results.values() if v.startswith("FAIL"))
skip_count = sum(1 for v in results.values() if v.startswith("SKIP"))
print(f"总计: {len(results)} 个API测试 | OK: {ok_count} | FAIL: {fail_count} | SKIP: {skip_count}")

# Save results
output_path = PROJECT_ROOT / "data" / "test_results_all_apis.json"
output_path.parent.mkdir(parents=True, exist_ok=True)
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"结果已保存到: {output_path}")
