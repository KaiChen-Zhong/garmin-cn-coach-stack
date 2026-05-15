# Reproduction Guide

This repo is designed to be copied onto another machine and rebuilt from public docs plus local secrets.

## What Git gives you

- core Python implementation
- CLI
- MCP server
- WorkBuddy / OpenClaw / Hermes integration templates
- public docs

## What stays local

- `.env`
- `data/`
- `obsidian/`
- `logs/`
- `.workbuddy/`
- `~/.openclaw/skills/garmin-fitness/`
- `~/.hermes/skills/garmin-fitness/`
- `~/.hermes/config.yaml`
- `~/.mcp.json`

## Rebuild on new machine

1. Clone repo
2. Create venv
3. Install requirements
4. Copy `.env.example` to `.env`
5. Fill your Garmin CN credentials locally
6. Run `python install_integrations.py`
7. Run `python main.py diagnose --cn`
8. Run `python main.py fitness-coach review --cn --deep`

## If you want same history

Copy these folders from old machine to new one before running deep review:

- `data/`
- `obsidian/`
- `.workbuddy/`
- `logs/`

Then rerun:

```powershell
python install_integrations.py
python main.py fitness-coach review --cn --deep
```

## Agent behavior

If an LLM reads this repo, it should:

- read `AGENTS.md` first
- read `README.md` and `docs/SETUP_GUIDE.md`
- ask user for local-only secrets
- never invent missing values
- prefer `python install_integrations.py` over manual file edits for integration setup

