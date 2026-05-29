"""
Garmin Connect 自动化 - CLI 入口
提供命令行操作接口
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import date

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def cmd_login(args):
    """登录并验证"""
    from auth import GarminAuth
    auth = GarminAuth(is_cn=_region_override(args))
    client = auth.login()
    profile = client.get_user_profile()
    print(f"✅ 登录成功！用户: {profile.get('displayName', 'unknown')}")


def _region_override(args):
    if getattr(args, "cn", False):
        return True
    if getattr(args, "global_region", False):
        return False
    return None


def add_region_flags(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--cn", action="store_true", help="强制使用 connect.garmin.cn")
    group.add_argument("--global", dest="global_region", action="store_true", help="强制使用 connect.garmin.com")


def cmd_diagnose(args):
    """只读诊断账号、区服、设备、最近活动"""
    from auth import GarminAuth

    regions = [True, False] if args.both else [_region_override(args)]
    for is_cn in regions:
        auth = GarminAuth(is_cn=is_cn)
        label = "garmin.cn" if auth.is_cn else "garmin.com"
        print(f"\n[{label}]")
        try:
            print(json.dumps(auth.diagnostic_snapshot(), ensure_ascii=False, indent=2))
        except Exception as e:
            print(json.dumps({"status": "failed", "error": str(e)}, ensure_ascii=False, indent=2))


def cmd_sync(args):
    """执行数据同步"""
    from scheduler import run_daily_sync, run_quick_sync, setup_logging

    setup_logging(level=args.log_level)
    data_dir = args.data_dir or str(PROJECT_ROOT / "data")

    if args.quick:
        result = run_quick_sync(data_dir, is_cn=_region_override(args))
    else:
        lookback = args.lookback or 30
        result = run_daily_sync(data_dir, lookback, is_cn=_region_override(args))

    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_export(args):
    """导出数据"""
    from auth import GarminAuth
    from exporter import GarminExporter
    from warehouse import refresh_warehouse

    auth = GarminAuth(is_cn=_region_override(args))
    exporter = GarminExporter(data_dir=args.data_dir or str(PROJECT_ROOT / "data"), auth=auth)

    category = args.category
    target = args.date or date.today().isoformat()

    if category == "health":
        result = exporter.export_daily_health(target)
    elif category == "advanced_health":
        result = exporter.export_advanced_health(target)
    elif category == "activities":
        result = exporter.export_activities(args.lookback or 30)
    elif category == "body":
        result = exporter.export_body_composition(target)
    elif category == "goals":
        result = exporter.export_goals()
    elif category == "device":
        result = exporter.export_device_info()
    elif category == "gear":
        result = exporter.export_gear()
    elif category == "hydration":
        result = exporter.export_hydration(target)
    elif category == "training":
        result = exporter.export_training_plans()
    elif category == "golf":
        result = exporter.export_golf()
    elif category == "profile":
        result = exporter.export_user_profile()
    elif category == "all":
        result = exporter.export_all(lookback_days=args.lookback or 30, date_str=target)
    else:
        print(f"❌ 未知类别: {category}")
        print("可用: health, advanced_health, activities, body, goals, device, gear, hydration, training, golf, profile, all")
        return

    refresh_warehouse(
        data_dir=args.data_dir or str(PROJECT_ROOT / "data"),
        db_path=str(Path(args.data_dir or PROJECT_ROOT / "data") / "garmin_warehouse.sqlite"),
    )
    print(f"✅ {category} 数据导出完成")


def cmd_workout(args):
    """训练操作"""
    from auth import GarminAuth
    from importer import GarminImporter
    importer = GarminImporter(auth=GarminAuth(is_cn=_region_override(args)))

    if args.action == "list":
        workouts = importer.get_workouts()
        for w in workouts:
            name = w.get("workoutName", "unnamed")
            wtype = w.get("sportType", {}).get("sportTypeKey", "?")
            print(f"  - [{wtype}] {name}")

    elif args.action == "create":
        if args.quick_run:
            result = importer.quick_run(
                name=args.name or "Easy Run",
                schedule_date=args.schedule,
            )
        elif args.quick_cycling:
            result = importer.quick_cycling(
                name=args.name or "Cycling Workout",
                schedule_date=args.schedule,
            )
        else:
            result = importer.create_workout(
                args.type or "running",
                {"name": args.name or "Custom Workout", "steps": []},
            )

        if result:
            wid = result.get("workoutId", "?")
            print(f"✅ 训练创建成功 (ID: {wid})")
        else:
            print("❌ 训练创建失败")

    elif args.action == "delete":
        if importer.delete_workout(args.workout_id):
            print(f"✅ 训练 {args.workout_id} 已删除")
        else:
            print("❌ 删除失败")

    elif args.action == "import":
        results = importer.import_workout_plan_from_file(args.file)
        for r in results:
            status = "✅" if r["success"] else "❌"
            print(f"  {status} {r['name']} ({r['type']}) - {r['date']}")

    else:
        print(f"❌ 未知操作: {args.action}")
        print("可用: list, create, delete, import")


def cmd_weight(args):
    """添加体重"""
    from auth import GarminAuth
    from importer import GarminImporter
    importer = GarminImporter(auth=GarminAuth(is_cn=_region_override(args)))
    result = importer.add_weight(args.weight)
    if result:
        print(f"✅ 体重记录添加成功: {args.weight} kg")
    else:
        print("❌ 添加失败")


def cmd_hydration(args):
    """添加水合数据"""
    from auth import GarminAuth
    from importer import GarminImporter
    importer = GarminImporter(auth=GarminAuth(is_cn=_region_override(args)))
    result = importer.add_hydration(args.ml, args.target)
    if result:
        print(f"✅ 水合数据添加成功: {args.ml} ml")
    else:
        print("❌ 添加失败")


def cmd_coach(args):
    """教练分析"""
    from coach import FitnessCoach

    coach = FitnessCoach(data_dir=args.data_dir or str(PROJECT_ROOT / "data"))
    target = args.date or date.today().isoformat()

    if args.action == "morning":
        report = coach.morning(target, write_memory=not args.no_write)
    elif args.action == "evening":
        report = coach.evening(target, write_memory=not args.no_write)
    elif args.action == "weekly":
        report = coach.weekly(target, write_memory=not args.no_write)
    elif args.action == "monthly":
        report = coach.monthly(target, write_memory=not args.no_write)
    elif args.action == "alerts":
        report = coach.alerts(target)
    elif args.action == "plan":
        report = coach.plan(target, weeks=args.weeks, write_memory=not args.no_write)
    elif args.action == "gear":
        report = coach.gear_report(target)
    elif args.action == "review":
        from fitness_workflow import run_fitness_review
        report = run_fitness_review(
            target=target,
            data_dir=args.data_dir or str(PROJECT_ROOT / "data"),
            lookback_days=args.lookback,
            weeks=args.weeks,
            sync=not args.no_sync,
            sync_mode="none" if args.no_sync else args.sync_mode,
            write_memory=not args.no_write,
            import_plan=args.import_plan,
            include_easy_workouts=args.include_easy_workouts,
            is_cn=_region_override(args),
            deep=args.deep,
        )
    elif args.action == "confidence":
        report = coach.race_confidence(target)
    elif args.action == "log-recovery":
        if not args.note:
            print("❌ 需要 --note")
            return
        coach.memory.append_recovery(args.note, args.date)
        report = {"status": "ok", "note": args.note}
    else:
        print(f"❌ 未知操作: {args.action}")
        return

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def cmd_warehouse(args):
    """仓库管理"""
    from warehouse import refresh_warehouse, warehouse_status

    if args.action == "refresh":
        result = refresh_warehouse(
            data_dir=args.data_dir or str(PROJECT_ROOT / "data"),
            db_path=args.db or str(PROJECT_ROOT / "data" / "garmin_warehouse.sqlite"),
        )
    elif args.action == "status":
        result = warehouse_status(args.db or str(PROJECT_ROOT / "data" / "garmin_warehouse.sqlite"))
    else:
        print(f"❌ 未知操作: {args.action}")
        return

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def cmd_mcp(args):
    """启动 MCP 服务器"""
    from mcp_server import serve_stdio
    serve_stdio()


def cmd_serve(args):
    """启动 API 服务"""
    from api_server import start_server
    print(f"🚀 启动 Garmin API 服务: http://{args.host}:{args.port}")
    print(f"📖 API 文档: http://{args.host}:{args.port}/docs")
    start_server(host=args.host, port=args.port)


def cmd_sync_getnote(args):
    """运行 Garmin 复盘并写入 Get笔记"""
    from fitness_workflow import run_fitness_review
    from getnote_client import save_garmin_review_to_getnote

    deep = args.mode == "deep"
    sync_mode = "full" if deep else args.sync_mode
    lookback = max(args.lookback, 365) if deep else args.lookback
    weeks = max(args.weeks, 8) if deep else args.weeks
    report = run_fitness_review(
        target=args.date,
        data_dir=args.data_dir or str(PROJECT_ROOT / "data"),
        lookback_days=lookback,
        weeks=weeks,
        sync=not args.no_sync,
        sync_mode=sync_mode,
        write_memory=not args.no_write,
        import_plan=args.import_plan,
        include_easy_workouts=args.include_easy_workouts,
        is_cn=_region_override(args),
        deep=deep,
    )
    title_prefix = {
        "daily": "Garmin 今日复盘",
        "weekly": "Garmin 周复盘",
        "deep": "Garmin 深度复盘",
    }.get(args.mode, "Garmin 今日复盘")
    target = report.get("date") or date.today().isoformat()
    title = args.title or f"{title_prefix} {target}"
    tags = [tag.strip() for tag in (args.tags or "Garmin,训练复盘,恢复,AI教练").split(",") if tag.strip()]
    result = save_garmin_review_to_getnote(report, title=title, tags=tags)
    print(json.dumps({
        "status": "ok",
        "getnote": result,
        "summary": report.get("summary"),
        "date": target,
    }, ensure_ascii=False, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(
        description="Garmin Connect 自动化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py login                              # 登录验证
  python main.py sync                               # 全量同步
  python main.py sync --quick                       # 快速同步(仅今日健康)
  python main.py export health                      # 导出今日健康数据
  python main.py export activities --lookback 7     # 导出近7天活动
  python main.py export all                         # 全量导出
  python main.py workout list                       # 列出训练
  python main.py workout create --quick-run --schedule 2026-05-16  # 快捷创建跑步训练
  python main.py workout import plan.json           # 从文件导入训练计划
  python main.py weight 65.5                        # 记录体重
  python main.py hydration 1500                     # 记录饮水
  python main.py coach morning --cn                 # 生成晨报
  python main.py coach evening --cn                 # 生成晚报
  python main.py warehouse refresh                  # 刷新 SQLite 仓库
  python main.py sync-getnote --daily --cn          # 复盘并写入 Get笔记
  python main.py mcp                                # 启动 MCP stdio 服务
  python main.py serve                              # 启动API服务
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # login
    login_parser = subparsers.add_parser("login", help="登录验证")
    add_region_flags(login_parser)

    # diagnose
    diagnose_parser = subparsers.add_parser("diagnose", help="只读诊断账号/区服/设备/最近活动")
    add_region_flags(diagnose_parser)
    diagnose_parser.add_argument("--both", action="store_true", help="同时测试 CN 和 global")

    # sync
    sync_parser = subparsers.add_parser("sync", help="数据同步")
    sync_parser.add_argument("--quick", action="store_true", help="快速同步")
    sync_parser.add_argument("--lookback", type=int, default=30, help="回溯天数")
    sync_parser.add_argument("--data-dir", type=str, help="数据目录")
    sync_parser.add_argument("--log-level", type=str, default="INFO", help="日志级别")
    add_region_flags(sync_parser)

    # export
    export_parser = subparsers.add_parser("export", help="数据导出")
    export_parser.add_argument("category", type=str, help="导出类别")
    export_parser.add_argument("--date", type=str, help="目标日期 YYYY-MM-DD")
    export_parser.add_argument("--lookback", type=int, default=30, help="回溯天数")
    export_parser.add_argument("--data-dir", type=str, help="数据目录")
    add_region_flags(export_parser)

    # workout
    workout_parser = subparsers.add_parser("workout", help="训练操作")
    workout_parser.add_argument("action", type=str, help="操作: list|create|delete|import")
    workout_parser.add_argument("--type", type=str, help="训练类型")
    workout_parser.add_argument("--name", type=str, help="训练名称")
    workout_parser.add_argument("--schedule", type=str, help="安排日期")
    workout_parser.add_argument("--quick-run", action="store_true", help="快捷跑步训练")
    workout_parser.add_argument("--quick-cycling", action="store_true", help="快捷骑行训练")
    workout_parser.add_argument("--workout-id", type=str, help="训练ID")
    workout_parser.add_argument("--file", type=str, help="训练计划文件路径")
    add_region_flags(workout_parser)

    # weight
    weight_parser = subparsers.add_parser("weight", help="记录体重")
    weight_parser.add_argument("weight", type=float, help="体重(kg)")
    add_region_flags(weight_parser)

    # hydration
    hydration_parser = subparsers.add_parser("hydration", help="记录饮水")
    hydration_parser.add_argument("ml", type=float, help="饮水量(ml)")
    hydration_parser.add_argument("--target", type=float, default=2500.0, help="目标(ml)")
    add_region_flags(hydration_parser)

    # coach
    coach_parser = subparsers.add_parser("coach", aliases=["fitness-coach"], help="训练教练分析")
    coach_parser.add_argument("action", type=str, help="操作: morning|evening|weekly|monthly|alerts|plan|gear|review|confidence|log-recovery")
    coach_parser.add_argument("--date", type=str, help="目标日期 YYYY-MM-DD")
    coach_parser.add_argument("--note", type=str, help="恢复日志内容")
    coach_parser.add_argument("--weeks", type=int, default=4, help="训练计划周数")
    coach_parser.add_argument("--lookback", type=int, default=30, help="复盘同步回溯天数")
    coach_parser.add_argument("--sync-mode", choices=["smart", "quick", "full", "none"], default="smart", help="复盘同步模式")
    coach_parser.add_argument("--deep", action="store_true", help="深度复盘：强制 full + 365天活动 + 8周计划 + 数据覆盖清单")
    coach_parser.add_argument("--no-sync", action="store_true", help="复盘时不重新拉取 Garmin 数据")
    coach_parser.add_argument("--import-plan", action="store_true", help="把生成计划导入 Garmin 日程")
    coach_parser.add_argument("--include-easy-workouts", action="store_true", help="导入计划时包含 easy run")
    coach_parser.add_argument("--data-dir", type=str, help="数据目录")
    coach_parser.add_argument("--no-write", action="store_true", help="只读，不写 Obsidian 记忆")
    add_region_flags(coach_parser)

    # warehouse
    warehouse_parser = subparsers.add_parser("warehouse", help="SQLite 仓库")
    warehouse_parser.add_argument("action", type=str, help="操作: refresh|status")
    warehouse_parser.add_argument("--data-dir", type=str, help="数据目录")
    warehouse_parser.add_argument("--db", type=str, help="数据库路径")

    # mcp
    subparsers.add_parser("mcp", help="启动 MCP stdio 服务")

    # serve
    serve_parser = subparsers.add_parser("serve", help="启动API服务")
    serve_parser.add_argument("--host", type=str, default="127.0.0.1", help="监听地址")
    serve_parser.add_argument("--port", type=int, default=8190, help="监听端口")

    # sync-getnote
    getnote_parser = subparsers.add_parser("sync-getnote", help="运行 Garmin 复盘并写入 Get笔记")
    getnote_mode = getnote_parser.add_mutually_exclusive_group()
    getnote_mode.add_argument("--daily", action="store_const", dest="mode", const="daily", help="今日复盘")
    getnote_mode.add_argument("--weekly", action="store_const", dest="mode", const="weekly", help="周复盘标题")
    getnote_mode.add_argument("--deep", action="store_const", dest="mode", const="deep", help="深度复盘")
    getnote_parser.set_defaults(mode="daily")
    getnote_parser.add_argument("--date", type=str, help="目标日期 YYYY-MM-DD")
    getnote_parser.add_argument("--lookback", type=int, default=7, help="回溯天数")
    getnote_parser.add_argument("--weeks", type=int, default=4, help="训练计划周数")
    getnote_parser.add_argument("--sync-mode", choices=["smart", "quick", "full", "none"], default="quick", help="同步模式")
    getnote_parser.add_argument("--data-dir", type=str, help="数据目录")
    getnote_parser.add_argument("--title", type=str, help="Get笔记标题")
    getnote_parser.add_argument("--tags", type=str, help="逗号分隔标签")
    getnote_parser.add_argument("--no-sync", action="store_true", help="不重新拉取 Garmin 数据")
    getnote_parser.add_argument("--no-write", action="store_true", help="不写 Obsidian")
    getnote_parser.add_argument("--import-plan", action="store_true", help="把训练计划导入 Garmin 日程")
    getnote_parser.add_argument("--include-easy-workouts", action="store_true", help="导入计划时包含 easy run")
    add_region_flags(getnote_parser)

    args = parser.parse_args()

    if args.command == "login":
        cmd_login(args)
    elif args.command == "diagnose":
        cmd_diagnose(args)
    elif args.command == "sync":
        cmd_sync(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "workout":
        cmd_workout(args)
    elif args.command == "weight":
        cmd_weight(args)
    elif args.command == "hydration":
        cmd_hydration(args)
    elif args.command in ("coach", "fitness-coach"):
        cmd_coach(args)
    elif args.command == "warehouse":
        cmd_warehouse(args)
    elif args.command == "mcp":
        cmd_mcp(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "sync-getnote":
        cmd_sync_getnote(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
