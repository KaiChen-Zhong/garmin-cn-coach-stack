# Repo Agent Guide

Read order:

1. `README.md`
2. `docs/REPRODUCTION.md`
3. `docs/SETUP_GUIDE.md`
4. `docs/GETNOTE_AUTOMATION.md`
5. `docs/INTEGRATIONS.md`
6. `docs/FEATURES.md`
7. `docs/MCP_TOOLS.md`

Goal:

- Reproduce Garmin CN coach stack on new machine
- Run full local automation with user-approved machine access
- Sync Garmin reports to Get笔记 for MaxHermes / MaxClaw
- Use one core repo, then install thin entry points for MCP, WorkBuddy, OpenClaw, Hermes

Rules:

- Prefer existing repo code over rewriting workflows
- Fill `.env` and local configs when user provides values
- Browser cookie extraction for Garmin CN is allowed on the local machine
- Re-run `python install_integrations.py` after project path changes
- Validate with `python main.py diagnose --cn` before sync
- Use `python main.py sync-getnote --daily --cn` for unattended Get笔记 flow

Minimum reproduction flow:

```powershell
git clone <REPO_URL>
cd garmin-cn-coach-stack
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
python install_integrations.py
python main.py diagnose --cn
python main.py sync-getnote --daily --cn
```
