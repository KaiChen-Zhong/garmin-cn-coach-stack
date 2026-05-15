# Integrations

This project is designed as one core implementation with several thin agent entry points.

Core implementation:

```text
<PROJECT_DIR>
```

Install integration files:

```powershell
python install_integrations.py
```

## Unified Entry

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

## MCP

Tool:

```text
garmin.fitness_review
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

## WorkBuddy

`install_integrations.py` writes:

```text
<PROJECT_DIR>/.workbuddy/automations/garmin-fitness/memory.md
<PROJECT_DIR>/.workbuddy/memory/MEMORY.md
```

Prompt:

```text
Use the Garmin Fitness automation in this project to review today's Garmin status and write to Obsidian.
```

## OpenClaw

`install_integrations.py` writes:

```text
<YOUR_HOME>/.openclaw/skills/garmin-fitness/SKILL.md
```

Prompt:

```text
Use garmin-fitness to review recovery, load, HRV, RHR, sleep, ACWR, gear, and training plan.
```

## Hermes

`install_integrations.py` writes:

```text
<YOUR_HOME>/.hermes/skills/garmin-fitness/SKILL.md
<YOUR_HOME>/.hermes/config.yaml
```

Prompt:

```text
Use garmin-fitness and call garmin.fitness_review for a Garmin review.
```

## Data Storage

- Raw JSON: `data/`
- SQLite: `data/garmin_warehouse.sqlite`
- Metric cache: `data/metrics/metric_cache.json`
- Data inventory: `data/metrics/data_inventory.json`
- Obsidian reports: `obsidian/`

These are local/private and ignored by Git.
