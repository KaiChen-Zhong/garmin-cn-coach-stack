"""
Garmin Connect REST API 服务
- 提供外部系统访问接口
- 训练创建/安排/删除
- 数据查询
- 健康数据写入
"""

import os
import json
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from auth import GarminAuth, get_client
from exporter import GarminExporter
from importer import GarminImporter
from coach import FitnessCoach
from fitness_workflow import run_fitness_review
from warehouse import refresh_warehouse, warehouse_status

logger = logging.getLogger(__name__)

# ─── FastAPI 应用 ───

app = FastAPI(
    title="Garmin Connect 自动化 API",
    description="佳明数据导出与训练计划导入的 REST API 服务",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── API Key 验证 ───

API_KEY = os.getenv("GARMIN_API_KEY", "")


def verify_api_key(x_api_key: str = Header(default="")):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return True


# ─── Pydantic 模型 ───

class WorkoutStepModel(BaseModel):
    type: str = Field(..., description="步骤类型: warmup | interval | recovery | cooldown | repeat")
    duration: int = Field(300, description="持续时间(秒)")
    target_type: Optional[str] = Field(None, description="目标类型")
    target_value: Optional[float] = Field(None, description="目标值")
    repeat_count: Optional[int] = Field(None, description="重复次数(仅repeat类型)")
    steps: Optional[list["WorkoutStepModel"]] = Field(None, description="子步骤(仅repeat类型)")


class CreateWorkoutRequest(BaseModel):
    workout_type: str = Field(..., description="训练类型: running | cycling | swimming | walking | hiking | multisport | fitness_equipment")
    name: str = Field("Custom Workout", description="训练名称")
    estimated_duration: int = Field(1800, description="预估时长(秒)")
    steps: list[WorkoutStepModel] = Field(default_factory=list, description="训练步骤")
    schedule_date: Optional[str] = Field(None, description="安排日期 YYYY-MM-DD")


class ScheduleWorkoutRequest(BaseModel):
    workout_id: str = Field(..., description="训练ID")
    date: str = Field(..., description="安排日期 YYYY-MM-DD")


class ManualActivityRequest(BaseModel):
    name: str = Field(..., description="活动名称")
    activity_type: str = Field(..., description="活动类型: running, cycling, etc.")
    start_time: str = Field(..., description="开始时间 ISO格式")
    duration_sec: int = Field(..., description="持续秒数")
    distance_meters: float = Field(0, description="距离(米)")
    description: str = Field("", description="描述")


class WeightRequest(BaseModel):
    weight_kg: float = Field(..., description="体重(kg)")
    unit: str = Field("kg", description="单位")


class BodyCompositionRequest(BaseModel):
    weight_kg: float = Field(..., description="体重(kg)")
    percent_fat: Optional[float] = Field(None, description="体脂率")
    percent_hydration: Optional[float] = Field(None, description="水合率")
    muscle_mass: Optional[float] = Field(None, description="肌肉量")
    bone_mass: Optional[float] = Field(None, description="骨量")
    metabolic_age: Optional[float] = Field(None, description="代谢年龄")


class HydrationRequest(BaseModel):
    value_ml: float = Field(..., description="饮水量(ml)")
    target_ml: float = Field(2500.0, description="目标饮水量(ml)")


class BloodPressureRequest(BaseModel):
    systolic: float = Field(..., description="收缩压")
    diastolic: float = Field(..., description="舒张压")
    pulse: float = Field(..., description="脉搏")
    notes: str = Field("", description="备注")


class QuickRunRequest(BaseModel):
    name: str = Field("Easy Run", description="训练名称")
    warmup_min: int = Field(10, description="热身分钟")
    intervals: int = Field(3, description="间歇组数")
    interval_min: float = Field(5, description="间歇分钟")
    recovery_min: float = Field(2, description="恢复分钟")
    cooldown_min: int = Field(5, description="放松分钟")
    hr_zone: int = Field(4, description="心率区间")
    schedule_date: Optional[str] = Field(None, description="安排日期")


class CoachRequest(BaseModel):
    date: Optional[str] = Field(None, description="目标日期 YYYY-MM-DD")
    note: Optional[str] = Field(None, description="恢复日志内容")
    no_write: bool = Field(False, description="不写入 Obsidian")
    weeks: int = Field(4, description="训练计划周数")
    lookback_days: int = Field(30, description="复盘同步回溯天数")
    sync: bool = Field(True, description="复盘前同步 Garmin")
    sync_mode: str = Field("smart", description="同步模式: smart | quick | full | none")
    import_plan: bool = Field(False, description="是否把训练计划导入 Garmin")
    include_easy_workouts: bool = Field(False, description="导入计划时包含 easy run")
    deep: bool = Field(False, description="深度复盘：强制 full + 365天活动 + 8周计划 + 数据覆盖清单")


# ─── 认证端点 ───

@app.get("/api/v1/auth/status", tags=["认证"])
async def auth_status():
    """检查认证状态"""
    try:
        client = get_client()
        profile = client.get_user_profile()
        return {"authenticated": True, "user": profile.get("displayName", "unknown")}
    except Exception as e:
        return {"authenticated": False, "error": str(e)}


@app.post("/api/v1/auth/login", tags=["认证"])
async def login():
    """重新登录"""
    try:
        auth = GarminAuth()
        client = auth.login()
        return {"status": "ok", "message": "登录成功"}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.post("/api/v1/auth/refresh", tags=["认证"])
async def refresh_token():
    """刷新 Token"""
    try:
        auth = GarminAuth()
        auth.refresh_token()
        return {"status": "ok", "message": "Token 刷新成功"}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


# ─── 数据导出端点 ───

@app.get("/api/v1/health/{target_date}", tags=["数据导出"])
async def get_health_data(target_date: str):
    """获取指定日期的健康数据"""
    try:
        exporter = GarminExporter()
        data = exporter.export_daily_health(target_date)
        return {"date": target_date, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/health/{target_date}/advanced", tags=["数据导出"])
async def get_advanced_health(target_date: str):
    """获取指定日期的高级健康指标"""
    try:
        exporter = GarminExporter()
        data = exporter.export_advanced_health(target_date)
        return {"date": target_date, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/activities", tags=["数据导出"])
async def get_activities(lookback_days: int = Query(30, description="回溯天数")):
    """获取活动列表"""
    try:
        exporter = GarminExporter()
        data = exporter.export_activities(lookback_days)
        return {"count": len(data), "activities": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/activities/{activity_id}", tags=["数据导出"])
async def get_activity_detail(activity_id: str):
    """获取活动详情"""
    try:
        exporter = GarminExporter()
        data = exporter.export_activity_details(activity_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/body-composition/{target_date}", tags=["数据导出"])
async def get_body_composition(target_date: str):
    """获取身体成分数据"""
    try:
        exporter = GarminExporter()
        data = exporter.export_body_composition(target_date)
        return {"date": target_date, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/goals", tags=["数据导出"])
async def get_goals():
    """获取目标与成就"""
    try:
        exporter = GarminExporter()
        data = exporter.export_goals()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/device", tags=["数据导出"])
async def get_device_info():
    """获取设备信息"""
    try:
        exporter = GarminExporter()
        data = exporter.export_device_info()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/gear", tags=["数据导出"])
async def get_gear():
    """获取装备数据"""
    try:
        exporter = GarminExporter()
        data = exporter.export_gear()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/hydration/{target_date}", tags=["数据导出"])
async def get_hydration(target_date: str):
    """获取水合与营养数据"""
    try:
        exporter = GarminExporter()
        data = exporter.export_hydration(target_date)
        return {"date": target_date, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/training-plans", tags=["数据导出"])
async def get_training_plans():
    """获取训练计划"""
    try:
        exporter = GarminExporter()
        data = exporter.export_training_plans()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/golf", tags=["数据导出"])
async def get_golf():
    """获取高尔夫数据"""
    try:
        exporter = GarminExporter()
        data = exporter.export_golf()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/user/profile", tags=["数据导出"])
async def get_user_profile():
    """获取用户资料"""
    try:
        exporter = GarminExporter()
        data = exporter.export_user_profile()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/sync/full", tags=["数据导出"])
async def full_sync(lookback_days: int = Query(30, description="活动回溯天数")):
    """执行全量数据同步"""
    try:
        exporter = GarminExporter()
        results = exporter.export_all(lookback_days=lookback_days)
        return {"status": "ok", "results": {k: "synced" for k in results}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 训练导入端点 ───

@app.post("/api/v1/workouts", tags=["训练导入"])
async def create_workout(req: CreateWorkoutRequest):
    """创建训练计划"""
    try:
        importer = GarminImporter()
        workout_data = {
            "name": req.name,
            "estimated_duration": req.estimated_duration,
            "steps": [s.model_dump() for s in req.steps],
        }
        result = importer.create_workout(req.workout_type, workout_data)

        if req.schedule_date and result:
            workout_id = result.get("workoutId")
            if workout_id:
                importer.schedule_workout(workout_id, req.schedule_date)

        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/workouts/schedule", tags=["训练导入"])
async def schedule_workout(req: ScheduleWorkoutRequest):
    """安排训练到指定日期"""
    try:
        importer = GarminImporter()
        result = importer.schedule_workout(req.workout_id, req.date)
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/workouts/{workout_id}", tags=["训练导入"])
async def delete_workout(workout_id: str):
    """删除训练"""
    try:
        importer = GarminImporter()
        success = importer.delete_workout(workout_id)
        return {"status": "ok" if success else "failed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/workouts", tags=["训练导入"])
async def list_workouts():
    """获取训练列表"""
    try:
        importer = GarminImporter()
        data = importer.get_workouts()
        return {"count": len(data), "workouts": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/workouts/quick-run", tags=["训练导入"])
async def quick_run(req: QuickRunRequest):
    """快捷创建跑步训练"""
    try:
        importer = GarminImporter()
        result = importer.quick_run(
            name=req.name,
            warmup_min=req.warmup_min,
            intervals=req.intervals,
            interval_min=req.interval_min,
            recovery_min=req.recovery_min,
            cooldown_min=req.cooldown_min,
            hr_zone=req.hr_zone,
            schedule_date=req.schedule_date,
        )
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/activities/manual", tags=["训练导入"])
async def create_manual_activity(req: ManualActivityRequest):
    """创建手动活动"""
    try:
        importer = GarminImporter()
        result = importer.create_manual_activity(
            name=req.name,
            activity_type=req.activity_type,
            start_time=req.start_time,
            duration_sec=req.duration_sec,
            distance_meters=req.distance_meters,
            description=req.description,
        )
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 健康数据写入端点 ───

@app.post("/api/v1/health/weight", tags=["健康数据写入"])
async def add_weight(req: WeightRequest):
    """添加体重记录"""
    try:
        importer = GarminImporter()
        result = importer.add_weight(req.weight_kg, req.unit)
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/health/body-composition", tags=["健康数据写入"])
async def add_body_composition(req: BodyCompositionRequest):
    """添加身体成分记录"""
    try:
        importer = GarminImporter()
        result = importer.add_body_composition(
            weight_kg=req.weight_kg,
            percent_fat=req.percent_fat,
            percent_hydration=req.percent_hydration,
            muscle_mass=req.muscle_mass,
            bone_mass=req.bone_mass,
            metabolic_age=req.metabolic_age,
        )
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/health/hydration", tags=["健康数据写入"])
async def add_hydration(req: HydrationRequest):
    """添加水合数据"""
    try:
        importer = GarminImporter()
        result = importer.add_hydration(req.value_ml, req.target_ml)
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/health/blood-pressure", tags=["健康数据写入"])
async def add_blood_pressure(req: BloodPressureRequest):
    """添加血压记录"""
    try:
        importer = GarminImporter()
        result = importer.add_blood_pressure(
            systolic=req.systolic,
            diastolic=req.diastolic,
            pulse=req.pulse,
            notes=req.notes,
        )
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 教练与仓库 ───

@app.post("/api/v1/coach/morning", tags=["教练"])
async def coach_morning(req: CoachRequest):
    try:
        coach = FitnessCoach(data_dir="./data")
        return coach.morning(req.date, write_memory=not req.no_write)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/coach/evening", tags=["教练"])
async def coach_evening(req: CoachRequest):
    try:
        coach = FitnessCoach(data_dir="./data")
        return coach.evening(req.date, write_memory=not req.no_write)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/coach/weekly", tags=["教练"])
async def coach_weekly(req: CoachRequest):
    try:
        coach = FitnessCoach(data_dir="./data")
        return coach.weekly(req.date, write_memory=not req.no_write)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/coach/monthly", tags=["教练"])
async def coach_monthly(req: CoachRequest):
    try:
        coach = FitnessCoach(data_dir="./data")
        return coach.monthly(req.date, write_memory=not req.no_write)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/coach/alerts", tags=["教练"])
async def coach_alerts(target_date: str = Query(default_factory=lambda: date.today().isoformat())):
    try:
        coach = FitnessCoach(data_dir="./data")
        return coach.alerts(target_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/coach/plan", tags=["教练"])
async def coach_plan(req: CoachRequest):
    try:
        coach = FitnessCoach(data_dir="./data")
        return coach.plan(req.date, weeks=req.weeks, write_memory=not req.no_write)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/coach/gear", tags=["教练"])
async def coach_gear(target_date: str = Query(default_factory=lambda: date.today().isoformat())):
    try:
        coach = FitnessCoach(data_dir="./data")
        return coach.gear_report(target_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/coach/review", tags=["教练"])
async def coach_review(req: CoachRequest):
    try:
        return run_fitness_review(
            target=req.date,
            data_dir="./data",
            lookback_days=req.lookback_days,
            weeks=req.weeks,
            sync=req.sync,
            sync_mode="none" if not req.sync else req.sync_mode,
            write_memory=not req.no_write,
            import_plan=req.import_plan,
            include_easy_workouts=req.include_easy_workouts,
            is_cn=True,
            deep=req.deep,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/coach/confidence", tags=["教练"])
async def coach_confidence(target_date: str = Query(default_factory=lambda: date.today().isoformat())):
    try:
        coach = FitnessCoach(data_dir="./data")
        return coach.race_confidence(target_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/coach/recovery", tags=["教练"])
async def coach_recovery(req: CoachRequest):
    try:
        if not req.note:
            raise HTTPException(status_code=400, detail="note required")
        coach = FitnessCoach(data_dir="./data")
        coach.memory.append_recovery(req.note, req.date)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/warehouse/refresh", tags=["仓库"])
async def warehouse_refresh():
    try:
        return refresh_warehouse()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/warehouse/status", tags=["仓库"])
async def warehouse_info():
    try:
        return warehouse_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 启动入口 ───

def start_server(host: str = "127.0.0.1", port: int = 8190):
    """启动 API 服务"""
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_server()
