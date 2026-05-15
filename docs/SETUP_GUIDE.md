# Setup Guide

This guide uses placeholders:

- `<PROJECT_DIR>`: local clone path
- `<YOUR_HOME>`: user home directory

## 1. Install

```powershell
git clone <YOUR_REPO_URL> garmin-cn-coach-stack
cd garmin-cn-coach-stack
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

## 2. Verify Garmin CN

```powershell
python main.py diagnose --cn
```

Expected:

- authenticated account profile
- device list, if available
- latest activity, if available

## 3. Run Reviews

Daily quick review:

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

Local-only review:

```powershell
python main.py fitness-coach review --cn --sync-mode none --weeks 4
```

## 4. Obsidian

Open this folder as an Obsidian vault:

```text
<PROJECT_DIR>/obsidian
```

Generated files:

```text
obsidian/Coach Memory.md
obsidian/Training Plan.md
obsidian/Recovery Log.md
obsidian/Daily/YYYY-MM-DD Manual Review.md
```

Manual review fields:

- RPE
- pain/discomfort
- subjective sleep quality
- stress/mood
- actual training completed
- tomorrow adjustment

Recovery note:

```powershell
python main.py fitness-coach log-recovery --cn --note "your recovery note"
```

## 5. MCP

Start server:

```powershell
python main.py mcp
```

Example config:

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

Main MCP tool:

```text
garmin.fitness_review
```

## 6. WorkBuddy / OpenClaw / Hermes

Install local integration files:

```powershell
python install_integrations.py
```

It writes:

```text
<PROJECT_DIR>/.workbuddy/automations/garmin-fitness/memory.md
<YOUR_HOME>/.openclaw/skills/garmin-fitness/SKILL.md
<YOUR_HOME>/.hermes/skills/garmin-fitness/SKILL.md
<YOUR_HOME>/.hermes/config.yaml
<YOUR_HOME>/.mcp.json
```

Ask your agent:

```text
Use garmin-fitness to review today's Garmin status, analyze recovery/load/training risk, and write to Obsidian.
```

Deep prompt:

```text
Use garmin-fitness deep mode for a comprehensive Garmin review and data coverage check.
```

## 7. Garmin Workout Import

Default review does not import workouts.

Import quality and long-run workouts:

```powershell
python main.py fitness-coach review --cn --sync-mode smart --lookback 30 --weeks 4 --import-plan
```

Also import easy runs:

```powershell
python main.py fitness-coach review --cn --sync-mode smart --lookback 30 --weeks 4 --import-plan --include-easy-workouts
```

## 8. Privacy

Never commit:

```text
.env
data/
obsidian/
logs/
.workbuddy/
```

Before publishing:

```powershell
rg -n "<YOUR_REAL_EMAIL>|<YOUR_LOCAL_USERNAME>|<YOUR_DEVICE_ID>|<YOUR_ACTIVITY_ID>|<YOUR_TOKEN_FRAGMENT>" -S .
```
