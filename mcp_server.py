"""Minimal MCP stdio server for Garmin CN coach and data tools."""

from __future__ import annotations

import json
import sys
import base64
import inspect
from typing import Any

from garminconnect import Garmin

from auth import GarminAuth
from cn_client import GarminCnClient
from coach import FitnessCoach
from exporter import GarminExporter
from fitness_workflow import run_fitness_review
from importer import GarminImporter
from warehouse import refresh_warehouse, warehouse_status


def _tool(name: str, description: str, input_schema: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "description": description, "inputSchema": input_schema}


STATIC_TOOLS = [
    _tool("garmin.diagnose", "Return CN account snapshot", {"type": "object", "properties": {"cn": {"type": "boolean"}}, "required": []}),
    _tool("garmin.export_all", "Export Garmin data", {"type": "object", "properties": {"lookback_days": {"type": "integer"}, "date": {"type": "string"}}, "required": []}),
    _tool("garmin.coach_morning", "Build morning coaching report", {"type": "object", "properties": {"date": {"type": "string"}, "no_write": {"type": "boolean"}}, "required": []}),
    _tool("garmin.coach_evening", "Build evening coaching report", {"type": "object", "properties": {"date": {"type": "string"}, "no_write": {"type": "boolean"}}, "required": []}),
    _tool("garmin.coach_weekly", "Build weekly coaching report", {"type": "object", "properties": {"date": {"type": "string"}, "no_write": {"type": "boolean"}}, "required": []}),
    _tool("garmin.coach_monthly", "Build monthly coaching report", {"type": "object", "properties": {"date": {"type": "string"}, "no_write": {"type": "boolean"}}, "required": []}),
    _tool("garmin.coach_alerts", "Detect training, recovery, HRV, RHR, sleep, ACWR, and gear alerts", {"type": "object", "properties": {"date": {"type": "string"}}, "required": []}),
    _tool("garmin.coach_plan", "Generate adaptive running plan and optionally write Obsidian Training Plan", {"type": "object", "properties": {"date": {"type": "string"}, "weeks": {"type": "integer"}, "no_write": {"type": "boolean"}}, "required": []}),
    _tool("garmin.coach_gear", "Analyze gear mileage and replacement risk", {"type": "object", "properties": {"date": {"type": "string"}}, "required": []}),
    _tool("garmin.fitness_review", "Sync Garmin CN, analyze today/current week/previous week/recent month, write Obsidian, optionally import plan", {"type": "object", "properties": {"date": {"type": "string"}, "lookback_days": {"type": "integer"}, "weeks": {"type": "integer"}, "sync": {"type": "boolean"}, "sync_mode": {"type": "string"}, "deep": {"type": "boolean"}, "no_write": {"type": "boolean"}, "import_plan": {"type": "boolean"}, "include_easy_workouts": {"type": "boolean"}}, "required": []}),
    _tool("garmin.coach_confidence", "Return race confidence score", {"type": "object", "properties": {"date": {"type": "string"}}, "required": []}),
    _tool("garmin.refresh_warehouse", "Refresh SQLite warehouse from export JSON", {"type": "object", "properties": {"data_dir": {"type": "string"}, "db_path": {"type": "string"}}, "required": []}),
    _tool("garmin.warehouse_status", "Inspect warehouse status", {"type": "object", "properties": {"db_path": {"type": "string"}}, "required": []}),
    _tool("garmin.workout_list", "List workouts", {"type": "object", "properties": {}, "required": []}),
    _tool("garmin.quick_run", "Create quick running workout", {"type": "object", "properties": {"name": {"type": "string"}, "schedule_date": {"type": "string"}}, "required": []}),
    _tool("garmin.add_weight", "Add weight log", {"type": "object", "properties": {"weight_kg": {"type": "number"}}, "required": ["weight_kg"]}),
]


def _json_type(annotation: Any, default: Any = inspect._empty) -> dict[str, Any]:
    if annotation in (int, "int") or isinstance(default, int) and not isinstance(default, bool):
        return {"type": "integer"}
    if annotation in (float, "float") or isinstance(default, float):
        return {"type": "number"}
    if annotation in (bool, "bool") or isinstance(default, bool):
        return {"type": "boolean"}
    if annotation in (dict, "dict"):
        return {"type": "object"}
    if annotation in (list, "list"):
        return {"type": "array"}
    return {"type": "string"}


def _schema_from_signature(fn: Any) -> dict[str, Any]:
    try:
        sig = inspect.signature(fn)
    except Exception:
        return {"type": "object", "properties": {}, "required": []}
    props: dict[str, Any] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name == "self" or param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        props[name] = _json_type(param.annotation, param.default)
        if param.default is inspect._empty:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


def _method_tools() -> list[dict[str, Any]]:
    names = set()
    for cls in (Garmin, GarminCnClient):
        for name, value in inspect.getmembers(cls, predicate=inspect.isfunction):
            if not name.startswith("_"):
                names.add(name)
    blocked = {"login", "resume_login", "logout", "connectwebproxy", "connectapi", "download"}
    tools = []
    for name in sorted(names - blocked):
        fn = getattr(Garmin, name, None) or getattr(GarminCnClient, name, None)
        desc = (inspect.getdoc(fn) or f"Garmin CN method {name}").splitlines()[0] if fn else f"Garmin CN method {name}"
        tools.append(_tool(f"garmin.{name}", desc, _schema_from_signature(fn) if fn else {"type": "object", "properties": {}, "required": []}))
    return tools


TOOLS = STATIC_TOOLS + [tool for tool in _method_tools() if tool["name"] not in {x["name"] for x in STATIC_TOOLS}]


def _result(data: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(_sanitize(data), ensure_ascii=False, default=str)}]}


def _sanitize(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"type": "bytes", "size": len(value), "base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    if isinstance(value, tuple):
        return [_sanitize(v) for v in value]
    return value


def _handle_tool(name: str, args: dict[str, Any]) -> Any:
    auth = GarminAuth(is_cn=True)
    if name == "garmin.diagnose":
        return auth.diagnostic_snapshot()
    if name == "garmin.export_all":
        exporter = GarminExporter(auth=auth)
        return exporter.export_all(lookback_days=int(args.get("lookback_days") or 30), date_str=args.get("date"))
    if name == "garmin.coach_morning":
        return FitnessCoach().morning(args.get("date"), write_memory=not args.get("no_write", False))
    if name == "garmin.coach_evening":
        return FitnessCoach().evening(args.get("date"), write_memory=not args.get("no_write", False))
    if name == "garmin.coach_weekly":
        return FitnessCoach().weekly(args.get("date"), write_memory=not args.get("no_write", False))
    if name == "garmin.coach_monthly":
        return FitnessCoach().monthly(args.get("date"), write_memory=not args.get("no_write", False))
    if name == "garmin.coach_alerts":
        return FitnessCoach().alerts(args.get("date"))
    if name == "garmin.coach_plan":
        return FitnessCoach().plan(args.get("date"), weeks=int(args.get("weeks") or 4), write_memory=not args.get("no_write", False))
    if name == "garmin.coach_gear":
        return FitnessCoach().gear_report(args.get("date"))
    if name == "garmin.fitness_review":
        return run_fitness_review(
            target=args.get("date"),
            lookback_days=int(args.get("lookback_days") or 30),
            weeks=int(args.get("weeks") or 4),
            sync=args.get("sync", True),
            sync_mode="none" if args.get("sync") is False else args.get("sync_mode", "smart"),
            write_memory=not args.get("no_write", False),
            import_plan=args.get("import_plan", False),
            include_easy_workouts=args.get("include_easy_workouts", False),
            is_cn=True,
            deep=args.get("deep", False),
        )
    if name == "garmin.coach_confidence":
        return FitnessCoach().race_confidence(args.get("date"))
    if name == "garmin.refresh_warehouse":
        return refresh_warehouse(args.get("data_dir") or "./data", args.get("db_path") or "./data/garmin_warehouse.sqlite")
    if name == "garmin.warehouse_status":
        return warehouse_status(args.get("db_path") or "./data/garmin_warehouse.sqlite")
    if name == "garmin.workout_list":
        importer = GarminImporter(auth=auth)
        return importer.get_workouts()
    if name == "garmin.quick_run":
        importer = GarminImporter(auth=auth)
        return importer.quick_run(name=args.get("name") or "Easy Run", schedule_date=args.get("schedule_date"))
    if name == "garmin.add_weight":
        importer = GarminImporter(auth=auth)
        return importer.add_weight(float(args["weight_kg"]))
    if name.startswith("garmin."):
        method_name = name.split(".", 1)[1]
        client = auth.ensure_connected()
        method = getattr(client, method_name)
        return method(**args)
    raise ValueError(f"unknown tool {name}")


def _read_messages():
    buf = sys.stdin.buffer
    while True:
        headers = {}
        line = buf.readline()
        if not line:
            return
        while line not in (b"\r\n", b"\n", b""):
            key, value = line.decode("utf-8").split(":", 1)
            headers[key.strip().lower()] = value.strip()
            line = buf.readline()
        if not headers:
            continue
        length = int(headers.get("content-length", "0"))
        payload = buf.read(length)
        if not payload:
            return
        yield json.loads(payload.decode("utf-8"))


def _send(obj: dict[str, Any]) -> None:
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("utf-8"))
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def serve_stdio() -> None:
    for msg in _read_messages():
        method = msg.get("method")
        msg_id = msg.get("id")
        try:
            if method == "initialize":
                _send({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "garmin-cn-coach", "version": "1.0.0"},
                        "capabilities": {"tools": {}},
                    },
                })
            elif method == "tools/list":
                _send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})
            elif method == "tools/call":
                params = msg.get("params") or {}
                name = params.get("name")
                args = params.get("arguments") or {}
                data = _handle_tool(name, args)
                _send({"jsonrpc": "2.0", "id": msg_id, "result": _result(data)})
            elif method == "ping":
                _send({"jsonrpc": "2.0", "id": msg_id, "result": {}})
            else:
                _send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Unknown method {method}"}})
        except Exception as e:
            _send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32000, "message": str(e)}})


if __name__ == "__main__":
    serve_stdio()
