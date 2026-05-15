# Garmin CN Fitness Coach

Garmin CN Fitness Coach is a local-first automation toolkit for Garmin Connect China.

It combines:
- Garmin Connect CN data export/import
- MCP tools for AI agents
- rule-based fitness coach workflows
- Obsidian long-term memory
- SQLite warehouse
- daily/weekly/monthly/deep review reports
- WorkBuddy / OpenClaw / Hermes skill integration

Sensitive user data is not meant to be committed. Keep `.env`, `data/`, `obsidian/`, `logs/`, and `.workbuddy/` local.

## Features

- CN-only Garmin login through `connect.garmin.cn`
- Export health, activities, training, device, gear, goals, hydration, golf, profile, and historical metrics
- Export Garmin official analysis data when available: Training Readiness, Training Status, HRV Status, VO2 Max, Race Predictions, Running Tolerance, Endurance Score, Hill Score, Fitness Age, Body Battery, Stress, RHR, Sleep, Intensity Minutes
- Import workouts, schedule workouts, add weight, hydration, blood pressure, body composition, and activity files
- MCP server with 145 tools, including `garmin.fitness_review`
- Coach reports: morning, evening, weekly, monthly, alerts, plan, gear, race confidence
- Deep review mode: full export, at least 365-day activity lookback, 8-week plan, data inventory
- Obsidian reports and manual review templates
- Local SQLite warehouse and metric cache

## Install

```powershell
git clone <YOUR_REPO_URL> garmin-cn-fitness-coach
cd garmin-cn-fitness-coach
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`:

```text
GARMIN_EMAIL=your_email@example.com
GARMIN_PASSWORD=your_password_here
GARMIN_IS_CN=true
GARMIN_API_KEY=change-me-to-a-random-string
```

Optional browser-cookie fallback:

```text
GARMIN_JWT_WEB=
GARMIN_CSRF_TOKEN=
```

Only fill those if password login cannot establish a CN web session.

## First Run

```powershell
python main.py diagnose --cn
python main.py fitness-coach review --cn --sync-mode quick --lookback 7 --weeks 4
```

If you only want to test local report generation without network:

```powershell
python main.py fitness-coach review --cn --sync-mode none --weeks 4
```

## Daily Use

Morning/evening quick review:

```powershell
python main.py fitness-coach review --cn --sync-mode quick --lookback 7 --weeks 4
```

Weekly review:

```powershell
python main.py fitness-coach review --cn --sync-mode smart --lookback 30 --weeks 4
```

Deep comprehensive review:

```powershell
python main.py fitness-coach review --cn --deep
```

Deep mode forces:
- full export
- at least 365 days of activity lookback
- at least 8 weeks of training plan generation
- SQLite refresh
- metric cache refresh
- data inventory generation
- Obsidian report writes

## Garmin Workout Import

Default review does not write workouts to Garmin.

Import only quality and long-run workouts:

```powershell
python main.py fitness-coach review --cn --sync-mode smart --lookback 30 --weeks 4 --import-plan
```

Also import easy runs:

```powershell
python main.py fitness-coach review --cn --sync-mode smart --lookback 30 --weeks 4 --import-plan --include-easy-workouts
```

## Obsidian

Open this folder as an Obsidian vault:

```text
<PROJECT_DIR>/obsidian
```

The app writes:

```text
obsidian/Coach Memory.md
obsidian/Training Plan.md
obsidian/Recovery Log.md
obsidian/Daily/YYYY-MM-DD Morning.md
obsidian/Daily/YYYY-MM-DD Evening.md
obsidian/Daily/YYYY-MM-DD Weekly.md
obsidian/Daily/YYYY-MM-DD Monthly.md
obsidian/Daily/YYYY-MM-DD Manual Review.md
```

Manual review fields:
- RPE
- pain/discomfort
- subjective sleep quality
- stress/mood
- actual training completed
- tomorrow adjustment

Log recovery notes:

```powershell
python main.py fitness-coach log-recovery --cn --note "your recovery note"
```

## MCP

Start MCP server:

```powershell
python main.py mcp
```

Example MCP config:

```json
{
  "mcpServers": {
    "garmin-cn": {
      "type": "stdio",
      "command": "python",
      "args": ["<PROJECT_DIR>/main.py", "mcp"],
      "env": {
        "GARMIN_DATA_DIR": "<PROJECT_DIR>/data"
      }
    }
  }
}
```

Main tool:

```text
garmin.fitness_review
```

Recommended args:

```json
{
  "lookback_days": 7,
  "weeks": 4,
  "sync": true,
  "sync_mode": "quick",
  "deep": false,
  "no_write": false,
  "import_plan": false,
  "include_easy_workouts": false
}
```

## WorkBuddy / OpenClaw / Hermes

Install local integration files:

```powershell
python install_integrations.py
```

This writes:
- WorkBuddy project automation memory under `.workbuddy/`
- OpenClaw skill under `<YOUR_HOME>/.openclaw/skills/garmin-fitness/`
- Hermes skill under `<YOUR_HOME>/.hermes/skills/garmin-fitness/`
- Hermes MCP config under `<YOUR_HOME>/.hermes/config.yaml`
- optional global MCP config under `<YOUR_HOME>/.mcp.json`

Then ask your agent:

```text
Use garmin-fitness to review today's Garmin status, analyze recovery/load/training risk, and write to Obsidian.
```

For full review:

```text
Use garmin-fitness deep mode for a comprehensive Garmin review and data coverage check.
```

## Data Storage

Do not commit personal data.

Local-only paths:

```text
.env
data/
obsidian/
logs/
.workbuddy/
```

Public-safe paths:

```text
*.py
requirements.txt
config/config.yaml
.env.example
docs/
integrations/
```

## Project Structure

```text
auth.py                 Garmin auth
cn_client.py            Garmin CN API client
exporter.py             export JSON data
importer.py             import workouts/body data
coach.py                coach algorithms
fitness_workflow.py     unified review workflow
metrics_cache.py        cached summaries and trends
data_inventory.py       export coverage inventory
warehouse.py            SQLite warehouse
mcp_server.py           MCP stdio server
api_server.py           FastAPI server
main.py                 CLI
integrations/           skills and agent instructions
docs/                   setup and operation docs
```

## Privacy Checklist Before GitHub

Run searches for your own real identifiers, for example your email address, account name, device IDs, activity IDs, local username, and token values:

```powershell
rg -n "<YOUR_REAL_EMAIL>|<YOUR_LOCAL_USERNAME>|<YOUR_DEVICE_ID>|<YOUR_ACTIVITY_ID>|<YOUR_TOKEN_FRAGMENT>" -S .
```

Expected: no real email, password, token, device ID, activity ID, or personal path in public files.

The `.gitignore` already excludes generated/private folders.
