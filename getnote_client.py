"""Get笔记 OpenAPI client and Garmin report formatter."""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import requests


GETNOTE_BASE_URL = "https://openapi.biji.com"


class GetNoteClient:
    def __init__(
        self,
        api_key: str | None = None,
        client_id: str | None = None,
        base_url: str = GETNOTE_BASE_URL,
    ) -> None:
        self.api_key = api_key or os.getenv("GETNOTE_API_KEY", "").strip()
        self.client_id = client_id or os.getenv("GETNOTE_CLIENT_ID", "").strip()
        self.base_url = base_url.rstrip("/")
        if not self.api_key or not self.client_id:
            raise RuntimeError("GETNOTE_API_KEY and GETNOTE_CLIENT_ID are required")

    def save_note(self, title: str, content: str, tags: list[str] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "note_type": "plain_text",
            "title": title,
            "content": content,
        }
        if tags:
            payload["tags"] = tags
        response = requests.post(
            f"{self.base_url}/open/api/v1/resource/note/save",
            headers={
                "Authorization": self.api_key,
                "X-Client-ID": self.client_id,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        try:
            data = response.json()
        except ValueError:
            data = {"text": response.text}
        if response.status_code >= 400:
            raise RuntimeError(f"Get笔记 save failed {response.status_code}: {data}")
        return data


def save_garmin_review_to_getnote(
    report: dict[str, Any],
    title: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    target = str(report.get("date") or date.today().isoformat())
    note_title = title or f"Garmin 今日复盘 {target}"
    note_tags = tags or ["Garmin", "训练复盘", "恢复", "AI教练"]
    content = garmin_review_to_markdown(report)
    result = GetNoteClient().save_note(note_title, content, note_tags)
    return {
        "saved": True,
        "title": note_title,
        "tags": note_tags,
        "result": result,
    }


def garmin_review_to_markdown(report: dict[str, Any]) -> str:
    target = str(report.get("date") or date.today().isoformat())
    today = _as_dict(report.get("today"))
    morning = _as_dict(today.get("morning"))
    evening = _as_dict(today.get("evening"))
    alerts = _as_dict(today.get("alerts"))
    gear = _as_dict(today.get("gear"))
    confidence = _as_dict(today.get("confidence"))
    current_week = _as_dict(report.get("current_week"))
    previous_week = _as_dict(report.get("previous_week"))
    recent_month = _as_dict(report.get("recent_month"))
    training_plan = _as_dict(report.get("training_plan"))
    inventory = _as_dict(report.get("data_inventory"))
    metric_cache = _as_dict(report.get("metric_cache"))

    lines = [
        f"# Garmin 今日复盘 {target}",
        "",
        "## 总览",
        f"- 生成时间: {report.get('generated_at', '')}",
        f"- 分析模式: {report.get('analysis_mode', '')}",
        f"- 摘要: {report.get('summary', '')}",
        "",
        "## 今日状态",
        f"- 晨间准备度: {morning.get('score', 'n/a')}",
        f"- 晨间结论: {morning.get('summary', morning.get('message', ''))}",
        f"- 晚间结论: {evening.get('summary', evening.get('message', ''))}",
        f"- 比赛信心: {confidence.get('score', 'n/a')}",
        "",
        "## 训练负荷",
        f"- 本周: {current_week.get('summary', '')}",
        f"- 前一周: {previous_week.get('summary', '')}",
        f"- 近 30 天: {recent_month.get('summary', '')}",
        "",
        "## 风险提醒",
        f"- 预警数量: {alerts.get('count', 'n/a')}",
        f"- 预警详情: {_compact(alerts.get('alerts') or alerts.get('items') or alerts)}",
        f"- 装备风险: {_compact(gear)}",
        "",
        "## 今日建议",
        f"- 晨间建议: {_compact(morning.get('recommendations') or morning.get('advice') or morning)}",
        f"- 晚间建议: {_compact(evening.get('recommendations') or evening.get('advice') or evening)}",
        "",
        "## 训练计划",
        f"- 计划摘要: {training_plan.get('summary', '')}",
        f"- 计划内容: {_compact(training_plan.get('weeks') or training_plan.get('plan') or training_plan)}",
        "",
        "## 数据覆盖",
        f"- 指标缓存: {_compact(metric_cache.get('trends') or metric_cache)}",
        f"- 活动覆盖: {_compact(inventory.get('activities'))}",
        f"- 类别覆盖: {_compact(inventory.get('categories'))}",
        f"- 覆盖建议: {_compact(inventory.get('recommendation'))}",
        "",
        "## 后续追问提示",
        str(report.get("llm_prompt", "")).strip(),
    ]
    return "\n".join(lines).strip() + "\n"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _compact(value: Any, limit: int = 1200) -> str:
    text = str(value if value is not None else "")
    text = " ".join(text.split())
    if len(text) > limit:
        return text[:limit] + "..."
    return text
