"""Install local WorkBuddy/OpenClaw/Hermes/MCP integration files."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
HOME = Path.home()


SKILL_TEXT = f"""---
name: garmin-fitness
description: Use Garmin CN data, MCP tools, Obsidian memory, and coach workflows to review recovery, load, training, gear, and plans.
---

# Garmin Fitness Coach

Project path:

```powershell
Set-Location {PROJECT_DIR}
```

Preferred MCP tool:

```text
garmin.fitness_review
```

Fallback CLI:

```powershell
python main.py fitness-coach review --cn --sync-mode quick --lookback 7 --weeks 4
```

Deep comprehensive review:

```powershell
python main.py fitness-coach review --cn --deep
```

Rules:
- CN only unless user explicitly changes config.
- Do not invent missing Garmin metrics.
- Do not delete Garmin data unless user gives exact destructive request.
- Treat `--import-plan` as a real Garmin write.
- Write summaries and manual review to Obsidian.
- Keep raw JSON in `data/`, SQLite in `data/garmin_warehouse.sqlite`, metric cache in `data/metrics/metric_cache.json`.
"""


WORKBUDDY_TEXT = f"""# Garmin Fitness WorkBuddy Automation

Project:

```text
{PROJECT_DIR}
```

Daily quick review:

```powershell
Set-Location {PROJECT_DIR}
python main.py fitness-coach review --cn --sync-mode quick --lookback 7 --weeks 4
```

Weekly review:

```powershell
Set-Location {PROJECT_DIR}
python main.py fitness-coach review --cn --sync-mode smart --lookback 30 --weeks 4
```

Deep comprehensive review:

```powershell
Set-Location {PROJECT_DIR}
python main.py fitness-coach review --cn --deep
```

Import generated plan into Garmin only when explicitly requested:

```powershell
python main.py fitness-coach review --cn --import-plan --weeks 4
```

Outputs:
- JSON to terminal
- Obsidian reports in `obsidian/Daily/`
- plan in `obsidian/Training Plan.md`
- recovery notes in `obsidian/Recovery Log.md`
- metric cache in `data/metrics/metric_cache.json`
- data inventory in `data/metrics/data_inventory.json`
"""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def install_skills() -> None:
    write_text(PROJECT_DIR / ".workbuddy" / "automations" / "garmin-fitness" / "memory.md", WORKBUDDY_TEXT)
    write_text(PROJECT_DIR / ".workbuddy" / "memory" / "MEMORY.md", WORKBUDDY_TEXT)
    write_text(HOME / ".openclaw" / "skills" / "garmin-fitness" / "SKILL.md", SKILL_TEXT)
    write_text(HOME / ".hermes" / "skills" / "garmin-fitness" / "SKILL.md", SKILL_TEXT)


def install_mcp_json() -> None:
    path = HOME / ".mcp.json"
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = {}
    servers = payload.setdefault("mcpServers", {})
    servers["garmin-cn"] = {
        "type": "stdio",
        "command": "python",
        "args": [str(PROJECT_DIR / "main.py"), "mcp"],
        "env": {"GARMIN_DATA_DIR": str(PROJECT_DIR / "data")},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def install_hermes_config() -> None:
    path = HOME / ".hermes" / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join([
        "mcp_servers:",
        "  garmin-cn:",
        "    type: stdio",
        "    command: python",
        "    args:",
        f"      - {PROJECT_DIR / 'main.py'}",
        "      - mcp",
        "    env:",
        f"      GARMIN_DATA_DIR: {PROJECT_DIR / 'data'}",
        "",
    ])
    path.write_text(text, encoding="utf-8")


def main() -> None:
    install_skills()
    install_mcp_json()
    install_hermes_config()
    print(f"Installed integrations for project: {PROJECT_DIR}")
    print(f"Open Obsidian vault: {PROJECT_DIR / 'obsidian'}")


if __name__ == "__main__":
    main()
