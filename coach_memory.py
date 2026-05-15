"""Obsidian-style long-term memory for fitness coaching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import json


@dataclass
class CoachMemory:
    root: Path = Path("obsidian")

    @property
    def coach_memory(self) -> Path:
        return self.root / "Coach Memory.md"

    @property
    def training_plan(self) -> Path:
        return self.root / "Training Plan.md"

    @property
    def recovery_log(self) -> Path:
        return self.root / "Recovery Log.md"

    @property
    def daily_dir(self) -> Path:
        return self.root / "Daily"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_file(
            self.coach_memory,
            "# Coach Memory\n\n## Athlete\n- Goal: Unknown\n- Race: Unknown\n- Risk notes: none\n\n## Preferences\n- CN Garmin data only\n",
        )
        self._ensure_file(
            self.training_plan,
            "# Training Plan\n\n## Current Block\n- Focus: base fitness\n- Long run: unset\n- Quality sessions: unset\n",
        )
        self._ensure_file(
            self.recovery_log,
            "# Recovery Log\n\n## Active Issues\n- none\n\n## Log\n",
        )

    def _ensure_file(self, path: Path, text: str) -> None:
        if not path.exists():
            path.write_text(text, encoding="utf-8")

    def read_all(self) -> dict[str, str]:
        self.ensure()
        return {
            "coach_memory": self.coach_memory.read_text(encoding="utf-8"),
            "training_plan": self.training_plan.read_text(encoding="utf-8"),
            "recovery_log": self.recovery_log.read_text(encoding="utf-8"),
        }

    def active_risk_penalty(self) -> int:
        text = self.read_all()["recovery_log"].lower()
        if "active issues\n- none" in text or "active issues\r\n- none" in text:
            return 0
        risk_words = ("injury", "pain", "疼", "痛", "伤", "不适", "康复")
        hits = sum(1 for word in risk_words if word in text)
        return min(25, hits * 5)

    def append_recovery(self, note: str, when: str | None = None) -> None:
        self.ensure()
        stamp = when or datetime.now().isoformat(timespec="seconds")
        with self.recovery_log.open("a", encoding="utf-8") as f:
            f.write(f"\n- {stamp}: {note}\n")

    def write_daily_report(self, kind: str, report: dict, target: str | None = None) -> Path:
        self.ensure()
        target = target or date.today().isoformat()
        path = self.daily_dir / f"{target} {kind}.md"
        lines = [
            f"# {target} {kind}",
            "",
            f"- Score: {report.get('score', 'n/a')}",
            f"- Verdict: {report.get('verdict', '')}",
            "",
            "## Summary",
            report.get("summary", ""),
            "",
            "## Actions",
        ]
        for item in report.get("actions", []):
            lines.append(f"- {item}")
        lines.extend(["", "## Evidence"])
        for key, value in (report.get("evidence") or {}).items():
            lines.append(f"- {key}: {value}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def write_training_plan(self, plan: dict) -> Path:
        self.ensure()
        lines = [
            "# Training Plan",
            "",
            f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
            f"- Start: {plan.get('start_date', '')}",
            f"- Weeks: {plan.get('weeks', '')}",
            f"- Focus: {plan.get('focus', '')}",
            "",
            "## Guardrails",
        ]
        for item in plan.get("guardrails", []):
            lines.append(f"- {item}")
        lines.extend(["", "## Weekly Plan"])
        for week in plan.get("weekly_plan", []):
            lines.extend([
                "",
                f"### Week {week.get('week')} ({week.get('start')} ~ {week.get('end')})",
                f"- Target: {week.get('target_distance_km')} km / {week.get('target_minutes')} min",
                f"- Long run: {week.get('long_run_km')} km",
            ])
            for session in week.get("sessions", []):
                lines.append(f"- {session.get('day')}: {session.get('type')} - {session.get('detail')}")
        self.training_plan.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return self.training_plan

    def write_manual_review(self, report: dict, target: str | None = None) -> Path:
        self.ensure()
        target = target or date.today().isoformat()
        path = self.daily_dir / f"{target} Manual Review.md"
        lines = [
            f"# {target} Manual Review",
            "",
            "## 自动摘要",
            report.get("summary", ""),
            "",
            "## 今日状态",
            f"- Readiness: {report.get('today', {}).get('morning', {}).get('score', 'n/a')}",
            f"- Race confidence: {report.get('today', {}).get('confidence', {}).get('score', 'n/a')}",
            f"- Alerts: {report.get('today', {}).get('alerts', {}).get('count', 'n/a')}",
            "",
            "## AI 教练提示词",
            report.get("llm_prompt", ""),
            "",
            "## 手动复盘",
            "- 主观疲劳 RPE:",
            "- 疼痛/不适:",
            "- 睡眠主观质量:",
            "- 压力/情绪:",
            "- 今日训练实际完成:",
            "- 明日调整:",
            "",
            "## 证据 JSON",
            "```json",
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            "```",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
