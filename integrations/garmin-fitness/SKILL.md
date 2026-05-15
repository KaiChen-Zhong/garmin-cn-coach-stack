---
name: garmin-fitness
description: Use Garmin CN data, MCP tools, Obsidian memory, and coach workflows to review recovery, load, training, gear, and plans.
---

# Garmin Fitness Coach

Project path:

```powershell
Set-Location <PROJECT_DIR>
```

## Preferred Entry

Use MCP tool first when available:

```text
garmin.fitness_review
```

Arguments:
- `date`: optional `YYYY-MM-DD`
- `lookback_days`: default `30`
- `weeks`: default `4`
- `sync`: default `true`
- `sync_mode`: default `smart`; options `quick`, `smart`, `full`, `none`
- `deep`: default `false`; when true, force full export, at least 365 days, 8-week plan, data inventory
- `no_write`: default `false`
- `import_plan`: default `false`
- `include_easy_workouts`: default `false`

Fallback CLI:

```powershell
python main.py fitness-coach review --cn --lookback 30 --weeks 4
```

Sync modes:

```powershell
python main.py fitness-coach review --cn --sync-mode quick --lookback 7
python main.py fitness-coach review --cn --sync-mode smart --lookback 30
python main.py fitness-coach review --cn --sync-mode full --lookback 90
python main.py fitness-coach review --cn --sync-mode none
python main.py fitness-coach review --cn --deep
```

## Workflow

1. Sync latest Garmin CN data unless user says no sync.
2. Review today, current week, previous week, recent month.
3. Analyze readiness, sleep, HRV, RHR, Body Battery, ACWR, race confidence, gear mileage.
4. Generate training plan.
5. Write Obsidian files:
   - `obsidian/Daily/<date> Manual Review.md`
   - `obsidian/Daily/<date> Morning.md`
   - `obsidian/Daily/<date> Evening.md`
   - `obsidian/Daily/<date> Weekly.md`
   - `obsidian/Daily/<date> Monthly.md`
   - `obsidian/Training Plan.md`
   - `obsidian/Recovery Log.md`
6. Keep raw JSON in `data/`, SQLite in `data/garmin_warehouse.sqlite`, metric cache in `data/metrics/metric_cache.json`, inventory in `data/metrics/data_inventory.json`.
7. Use the returned `llm_prompt` and evidence JSON to produce final Chinese coach analysis.

## Garmin Import

Only import plan into Garmin when user explicitly asks:

```powershell
python main.py fitness-coach review --cn --import-plan --weeks 4
```

Default import sends only `quality` and `long_run` workouts. Add easy runs only when user asks:

```powershell
python main.py fitness-coach review --cn --import-plan --include-easy-workouts
```

## Manual Review

Ask user to fill:
- RPE
- pain / discomfort
- subjective sleep quality
- stress / mood
- actual completed training
- tomorrow adjustment

If pain or illness exists, log it:

```powershell
python main.py fitness-coach log-recovery --cn --note "..."
```

## Rules

- CN only.
- Do not invent missing Garmin metrics.
- Do not delete Garmin data unless user gives exact destructive request.
- Treat `--import-plan` as real Garmin write.
- If data sync fails, use local warehouse and say latest sync date.
