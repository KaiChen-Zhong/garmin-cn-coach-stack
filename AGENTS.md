# Repo Agent Guide

Read order:

1. `README.md`
2. `docs/REPRODUCTION.md`
3. `docs/SETUP_GUIDE.md`
4. `docs/INTEGRATIONS.md`
5. `docs/FEATURES.md`
6. `docs/MCP_TOOLS.md`

Goal:

- Reproduce Garmin CN coach stack on new machine
- Keep secrets local
- Use one core repo, then install thin entry points for MCP, WorkBuddy, OpenClaw, Hermes

Rules:

- Do not assume any secret exists in Git
- Ask user for local values when `.env` needs filling
- Never write personal data into tracked files
- Re-run `python install_integrations.py` after project path changes
- Validate with `python main.py diagnose --cn` before deep sync

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
python main.py fitness-coach review --cn --deep
```
