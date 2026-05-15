"""
每日自动化调度器
- 全量数据同步
- 训练计划推送
- 日志记录与错误告警
- 可被 WorkBuddy automation 调用
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import date, datetime
from typing import Optional

# 添加项目根目录到 sys.path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# 加载 .env 文件（优先于系统环境变量）
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from auth import GarminAuth
from exporter import GarminExporter
from importer import GarminImporter
from warehouse import refresh_warehouse


def setup_logging(log_dir: str = "./logs", level: str = "INFO"):
    """配置日志"""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    log_file = log_path / f"sync_{date.today().isoformat()}.log"

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def run_daily_sync(
    data_dir: str = "./data",
    lookback_days: int = 30,
    state_file: str = "./config/sync_state.json",
    is_cn: Optional[bool] = None,
):
    """执行每日数据同步"""
    logger = logging.getLogger("scheduler")
    logger.info("=" * 60)
    logger.info("每日同步开始 - %s", datetime.now().isoformat())
    logger.info("=" * 60)

    # 1. 认证
    try:
        auth = GarminAuth(is_cn=is_cn)
        client = auth.login()
        logger.info("认证成功")
    except Exception as e:
        logger.error("认证失败，同步终止: %s", e)
        return {"status": "auth_failed", "error": str(e)}

    # 2. 全量导出
    try:
        exporter = GarminExporter(data_dir=data_dir, auth=auth)
        results = exporter.export_all(lookback_days=lookback_days)
        refresh_warehouse(data_dir=data_dir, db_path=str(Path(data_dir) / "garmin_warehouse.sqlite"))
        logger.info("数据导出完成")
    except Exception as e:
        logger.error("数据导出失败: %s", e)
        results = {"status": "export_failed", "error": str(e)}

    # 3. 检查是否有待推送的训练计划
    plan_file = PROJECT_ROOT / "config" / "pending_workouts.json"
    if plan_file.exists():
        try:
            importer = GarminImporter(auth=auth)
            with open(plan_file, "r", encoding="utf-8") as f:
                pending = json.load(f)

            if pending:
                logger.info("发现 %d 个待推送训练计划", len(pending))
                plan_results = importer.import_workout_plan(pending)
                logger.info("训练计划推送完成")

                # 推送成功后清空待推送文件
                with open(plan_file, "w", encoding="utf-8") as f:
                    json.dump([], f)
            else:
                logger.info("无待推送训练计划")

        except Exception as e:
            logger.error("训练计划推送失败: %s", e)

    logger.info("每日同步完成 - %s", datetime.now().isoformat())
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


def run_quick_sync(data_dir: str = "./data", is_cn: Optional[bool] = None):
    """快速同步（仅当日健康数据）"""
    logger = logging.getLogger("scheduler")
    logger.info("快速同步开始 - %s", datetime.now().isoformat())

    try:
        auth = GarminAuth(is_cn=is_cn)
        client = auth.login()
    except Exception as e:
        logger.error("认证失败: %s", e)
        return {"status": "auth_failed", "error": str(e)}

    try:
        exporter = GarminExporter(data_dir=data_dir, auth=auth)
        today = date.today().isoformat()
        health = exporter.export_daily_health(today)
        refresh_warehouse(data_dir=data_dir, db_path=str(Path(data_dir) / "garmin_warehouse.sqlite"))
        logger.info("快速同步完成")
        return {"status": "ok", "date": today}
    except Exception as e:
        logger.error("快速同步失败: %s", e)
        return {"status": "failed", "error": str(e)}


if __name__ == "__main__":
    # 从命令行参数或环境变量读取配置
    data_dir = os.getenv("GARMIN_DATA_DIR", str(PROJECT_ROOT / "data"))
    lookback = int(os.getenv("GARMIN_LOOKBACK_DAYS", "30"))
    log_level = os.getenv("GARMIN_LOG_LEVEL", "INFO")

    setup_logging(level=log_level)

    # 判断是全量同步还是快速同步
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"

    if mode == "quick":
        result = run_quick_sync(data_dir)
    else:
        result = run_daily_sync(data_dir, lookback)

    print(json.dumps(result, ensure_ascii=False, indent=2))
