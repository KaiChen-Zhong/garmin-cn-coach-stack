"""测试 Garmin Connect 导入模块 (importer.py)"""
import os
import sys
import json
from pathlib import Path
from datetime import date, datetime

# Setup
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from auth import GarminAuth
from importer import GarminImporter

auth = GarminAuth()
client = auth.login()
importer = GarminImporter()

results = {}

def test_import(name, func):
    """测试导入功能"""
    try:
        data = func()
        results[name] = {"status": "OK", "data": str(data)[:200] if data else "None"}
        print(f"  {name}: OK")
        return data
    except Exception as e:
        results[name] = {"status": "FAIL", "error": str(e)}
        print(f"  {name}: FAIL - {e}")
        return None

# ============================================================
# 1. 获取训练列表
# ============================================================
print("=" * 60)
print("[1] 训练列表查询")
test_import("get_workouts", lambda: importer.get_workouts())

# ============================================================
# 2. 创建跑步训练（quick_run）
# ============================================================
print("=" * 60)
print("[2] 创建跑步训练 (quick_run)")
test_import("quick_run", lambda: importer.quick_run(
    name="[测试] 自动跑步训练",
    warmup_min=5,
    intervals=2,
    interval_min=3,
    recovery_min=1,
    cooldown_min=3,
    hr_zone=3,
))

# ============================================================
# 3. 创建骑行训练（quick_cycling）
# ============================================================
print("=" * 60)
print("[3] 创建骑行训练 (quick_cycling)")
test_import("quick_cycling", lambda: importer.quick_cycling(
    name="[测试] 自动骑行训练",
    warmup_min=5,
    intervals=3,
    interval_min=2,
    recovery_min=1,
    cooldown_min=3,
))

# ============================================================
# 4. 添加体重记录
# ============================================================
print("=" * 60)
print("[4] 添加体重记录")
test_import("add_weight", lambda: importer.add_weight(70.0))

# ============================================================
# 5. 添加水合数据
# ============================================================
print("=" * 60)
print("[5] 添加水合数据")
test_import("add_hydration", lambda: importer.add_hydration(2000.0, 2500.0))

# ============================================================
# 6. 添加血压记录
# ============================================================
print("=" * 60)
print("[6] 添加血压记录")
test_import("add_blood_pressure", lambda: importer.add_blood_pressure(
    systolic=120, diastolic=80, pulse=72, notes="测试记录"
))

# ============================================================
# 7. 添加身体成分
# ============================================================
print("=" * 60)
print("[7] 添加身体成分")
test_import("add_body_composition", lambda: importer.add_body_composition(
    weight_kg=70.0,
    percent_fat=18.5,
    percent_hydration=55.0,
    muscle_mass=50.0,
    bone_mass=3.5,
))

# ============================================================
# 8. 创建手动活动
# ============================================================
print("=" * 60)
print("[8] 创建手动活动")
now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
test_import("create_manual_activity", lambda: importer.create_manual_activity(
    name="[测试] 手动跑步",
    activity_type="running",
    start_time=now_str,
    duration_sec=1800,
    distance_meters=3000.0,
    description="自动化测试创建",
))

# ============================================================
# 9. 批量导入训练计划
# ============================================================
print("=" * 60)
print("[9] 批量导入训练计划")
plan = [
    {
        "workout_type": "running",
        "name": "[测试] 周二间歇跑",
        "steps": [
            {"type": "warmup", "duration": 600},
            {"type": "interval", "duration": 300, "target_type": "heart.rate.zone", "target_value": 4},
            {"type": "recovery", "duration": 120},
            {"type": "cooldown", "duration": 300},
        ]
    },
    {
        "workout_type": "cycling",
        "name": "[测试] 周四骑行",
        "steps": [
            {"type": "warmup", "duration": 600},
            {"type": "interval", "duration": 300},
            {"type": "recovery", "duration": 120},
            {"type": "cooldown", "duration": 300},
        ]
    },
]
test_import("import_workout_plan", lambda: importer.import_workout_plan(plan))

# ============================================================
# 10. 测试训练日程管理（schedule/unschedule/delete）
# ============================================================
print("=" * 60)
print("[10] 训练日程管理")
# 先获取已有的 workouts
workouts = client.get_workouts() or []
if workouts:
    wid = str(workouts[0].get("workoutId", ""))
    if wid:
        print(f"    Using workout ID: {wid}")
        test_import("schedule_workout", lambda: importer.schedule_workout(wid, date.today().isoformat()))
    else:
        print("    No workout ID found, skipping schedule test")
        results["schedule_workout"] = {"status": "SKIP", "error": "No workout ID"}
else:
    print("    No workouts found, skipping schedule test")
    results["schedule_workout"] = {"status": "SKIP", "error": "No workouts"}

# ============================================================
# 11. 活动文件导入测试 (使用之前下载的FIT文件)
# ============================================================
print("=" * 60)
print("[11] 活动文件导入")
# 找到之前下载的FIT文件
fit_dir = PROJECT_ROOT / "data" / "activities" / "fit"
if fit_dir.exists():
    fit_files = list(fit_dir.glob("*.fit"))
    if fit_files:
        fit_path = str(fit_files[0])
        print(f"    Using FIT file: {fit_path}")
        test_import("import_activity_file", lambda: importer.import_activity_file(fit_path))
    else:
        print("    No FIT files found in data dir")
        # Try downloading one first
        activities = client.get_activities(0, 5)
        if activities:
            aid = str(activities[0]["activityId"])
            fit_data = client.download_activity(aid, dl_fmt=client.ActivityDownloadFormat.ORIGINAL)
            fit_dir.mkdir(parents=True, exist_ok=True)
            test_fit = fit_dir / f"{aid}.fit"
            with open(test_fit, "wb") as f:
                f.write(fit_data)
            print(f"    Downloaded FIT: {test_fit}")
            test_import("import_activity_file", lambda: importer.import_activity_file(str(test_fit)))
        else:
            results["import_activity_file"] = {"status": "SKIP", "error": "No activities to download"}
else:
    results["import_activity_file"] = {"status": "SKIP", "error": "No FIT dir"}

# ============================================================
# Summary
# ============================================================
print("=" * 60)
print("导入模块测试汇总")
ok_count = sum(1 for v in results.values() if v.get("status") == "OK")
fail_count = sum(1 for v in results.values() if v.get("status") == "FAIL")
skip_count = sum(1 for v in results.values() if v.get("status") == "SKIP")
print(f"总计: {len(results)} 项测试 | OK: {ok_count} | FAIL: {fail_count} | SKIP: {skip_count}")

# Save results
output_path = PROJECT_ROOT / "data" / "test_results_import.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"结果已保存到: {output_path}")
