"""AI 场景化能力：文本解析 / 图片 OCR / 任务建议。

模型接入复用 settings 的 active API profile（OpenAI 兼容 /chat/completions）。
ZENTRAY_AI_FAKE=1 时返回确定性 fixture，不联网，供回归与演示。
设计文档：docs/AI-FEATURES.md
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

FEAT_PARSE = "smart_parse"
FEAT_OCR = "image_ocr"
FEAT_SUGGEST = "task_suggest"

# 建议类型 → 前端呈现/应用方式
SUGGEST_TYPES = ("priority", "deadline", "split", "review", "clean")

_DRAFT_SCHEMA_DESC = """{
  "title": "任务标题（必填，一句话）",
  "category": "分类名称，从给定列表选最贴切的；不确定则返回空字符串",
  "priority": "high|medium|low",
  "deadline": "YYYY-MM-DD 或空字符串",
  "reminder_time": "HH:MM 24小时制 或空字符串",
  "details": "补充说明，可为空字符串",
  "subtasks": ["可执行的小步骤", "..."]
}"""


class AIAssistError(Exception):
    """用户可读的 AI 调用失败；feature 用于前端定位是哪个能力。"""

    def __init__(self, message: str, feature: str = ""):
        super().__init__(message)
        self.feature = feature


def _fake_mode() -> bool:
    return os.environ.get("ZENTRAY_AI_FAKE", "").strip() not in ("", "0", "false", "False")


def _strip_fences(text: str) -> str:
    """剥掉 ```json ... ``` 围栏与前后杂质，取第一个 JSON 对象/数组。"""
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        s, e = text.find(opener), text.rfind(closer)
        if s != -1 and e > s:
            return text[s : e + 1]
    return text


def _normalize_priority(v) -> str:
    v = str(v or "medium").lower()
    return v if v in ("high", "medium", "low") else "medium"


def _normalize_date(v) -> str:
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", str(v or ""))
    if not m:
        return ""
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _normalize_time(v) -> str:
    m = re.match(r"^(\d{1,2}):(\d{2})", str(v or ""))
    if not m:
        return ""
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _clean_draft(raw: dict) -> dict:
    subs = raw.get("subtasks") or []
    if isinstance(subs, str):
        subs = [s.strip() for s in re.split(r"[\n;；]", subs) if s.strip()]
    return {
        "title": str(raw.get("title") or "").strip()[:100],
        "category": str(raw.get("category") or "").strip(),
        "priority": _normalize_priority(raw.get("priority")),
        "deadline": _normalize_date(raw.get("deadline")),
        "reminder_time": _normalize_time(raw.get("reminder_time")),
        "details": str(raw.get("details") or "").strip(),
        "subtasks": [str(s).strip()[:100] for s in subs if str(s).strip()][:20],
    }


def _clean_suggestions(raw) -> List[dict]:
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        t = str(item.get("type") or "review")
        if t not in SUGGEST_TYPES:
            t = "review"
        s = {
            "type": t,
            "target_title": str(item.get("target_title") or "").strip()[:100],
            "text": str(item.get("text") or "").strip(),
            "patch": {},
        }
        patch = item.get("patch") or {}
        if t == "priority" and _normalize_priority(patch.get("priority")):
            s["patch"]["priority"] = _normalize_priority(patch.get("priority"))
        elif t == "deadline" and _normalize_date(patch.get("deadline")):
            s["patch"]["deadline"] = _normalize_date(patch.get("deadline"))
        elif t == "split":
            subs = patch.get("subtask_titles") or []
            if isinstance(subs, list):
                s["patch"]["subtask_titles"] = [str(x).strip()[:100] for x in subs if str(x).strip()][:10]
        if s["text"]:
            out.append(s)
    return out[:8]


class AIAssistService:
    """三个场景方法共用 _chat；无 Key / 网络失败 / 返回不合法统一抛 AIAssistError。"""

    # ---- 基础通道 ----

    @classmethod
    def _chat(cls, messages: List[dict], *, feature: str, max_tokens: int = 1400) -> str:
        from zentray.services.settings_manager import SettingsManager

        ai = SettingsManager().ai
        profile = ai.active_profile()
        if not profile or not profile.api_key:
            raise AIAssistError("未配置 API Key，请先在 设置 → AI 能力 → 模型接入 中配置", feature)

        headers = {
            "Authorization": f"Bearer {profile.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": profile.model or "gpt-4o",
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        try:
            base = (profile.base_url or "https://api.openai.com/v1").rstrip("/")
            resp = requests.post(
                f"{base}/chat/completions", json=payload, headers=headers, timeout=60
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except AIAssistError:
            raise
        except requests.HTTPError as e:
            # 透出服务端错误信息（如 GLM 1113 余额不足），别只给 429 Client Error
            detail = _http_error_detail(e.response)
            logger.warning("AI assist error (%s): %s", feature, detail)
            raise AIAssistError(f"模型调用失败：{detail}", feature) from e
        except Exception as e:
            logger.warning("AI assist error (%s): %s", feature, e)
            raise AIAssistError(f"模型调用失败：{e}", feature) from e

    @classmethod
    def _chat_json(cls, messages: List[dict], *, feature: str):
        text = cls._chat(messages, feature=feature)
        try:
            return json.loads(_strip_fences(text))
        except Exception as e:
            logger.warning("AI assist json parse failed (%s): %r", feature, text[:200])
            raise AIAssistError("模型返回格式异常，请重试", feature) from e

    # ---- 场景一：文本 → 任务草稿 ----

    @classmethod
    def parse_text(cls, text: str, category_names: List[str], today: str) -> dict:
        text = (text or "").strip()
        if not text:
            raise AIAssistError("请输入要解析的内容", FEAT_PARSE)
        if _fake_mode():
            return _fake_draft(text, category_names)

        sys_prompt = (
            "你是待办事项解析器。把用户输入解析为一个结构化任务草稿，只输出 JSON，不要任何解释。"
            f"JSON 结构：{_DRAFT_SCHEMA_DESC}\n"
            f'今天日期：{today}。相对日期（如"后天"）换算成绝对日期。'
            f'category 只能从这些名称里选：{"、".join(category_names) if category_names else "（无分类可选，返回空字符串）"}。'
            "subtasks 拆成 2~6 条可执行小步骤；没有就返回空数组。"
        )
        raw = cls._chat_json(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": text},
            ],
            feature=FEAT_PARSE,
        )
        if isinstance(raw, list):
            raw = raw[0] if raw else {}
        draft = _clean_draft(raw if isinstance(raw, dict) else {})
        if not draft["title"]:
            draft["title"] = text[:50]
        return draft

    # ---- 场景二：图片 → 任务草稿（可多条） ----

    @classmethod
    def parse_image(
        cls, data_url: str, category_names: List[str], today: str
    ) -> List[dict]:
        data_url = (data_url or "").strip()
        if not data_url.startswith("data:image/"):
            raise AIAssistError("图片格式不受支持", FEAT_OCR)
        if len(data_url) > 12 * 1024 * 1024:
            raise AIAssistError("图片过大（>9MB），请压缩后重试", FEAT_OCR)
        if _fake_mode():
            return [_fake_draft("（图片识别）整理发布会物料", category_names)]

        sys_prompt = (
            "你是待办事项 OCR 解析器。从图片中识别出待办/任务信息，整理为任务草稿数组，只输出 JSON。"
            f'JSON 结构：{{"drafts": [{_DRAFT_SCHEMA_DESC}]}}（1~5 条，无任务线索则返回空数组）。'
            f'今天日期：{today}。图片里的相对日期换算成绝对日期。'
            f'category 只能从这些名称里选：{"、".join(category_names) if category_names else "（无分类可选，返回空字符串）"}。'
            "图片中的标题/正文/截止时间/清单项都要利用；清单项作为 subtasks。"
        )
        raw = cls._chat_json(
            [
                {"role": "system", "content": sys_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请识别图片中的待办事项"},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            feature=FEAT_OCR,
        )
        if isinstance(raw, dict):
            drafts = raw.get("drafts") or []
        elif isinstance(raw, list):
            drafts = raw
        else:
            drafts = []
        return [d for d in (_clean_draft(x) for x in drafts if isinstance(x, dict)) if d["title"]]

    # ---- 场景三：任务列表 → 建议 ----

    @classmethod
    def suggest(cls, tasks_summary: List[dict], today: str, focus_title: str = "") -> List[dict]:
        if not tasks_summary:
            raise AIAssistError("当前没有活跃任务，先添加一个再让 AI 建议", FEAT_SUGGEST)
        if _fake_mode():
            return _fake_suggestions(tasks_summary)

        lines = []
        for i, t in enumerate(tasks_summary[:60], 1):
            seg = f'{i}. {t["title"]} [分类:{t["category"] or "无"} 优先:{t["priority"]}'
            if t["deadline"]:
                seg += f' 截止:{t["deadline"]}'
            if t["subtask_total"]:
                seg += f' 子任务:{t["subtask_done"]}/{t["subtask_total"]}'
            lines.append(seg + "]")
        sys_prompt = (
            "你是效率教练，基于用户的活跃任务列表给出少量高价值建议，只输出 JSON。"
            'JSON 结构：{"suggestions": [{"type": "priority|deadline|split|review|clean", '
            '"target_title": "针对哪个任务（照抄列表中的标题，review/clean 可为空）", '
            '"text": "给用户看的一句话建议（中文，具体、可行动）", '
            '"patch": {"priority": "high"} 或 {"deadline": "YYYY-MM-DD"} 或 {"subtask_titles": ["..."]}}]}。'
            f"今天日期：{today}。"
            "规则：最多 5 条；priority/deadline/split 必须给 patch（split 给 subtask_titles 2~5 条）；"
            "review/clean 是清单式提醒（如过期扎堆、高优过载）不给 patch；"
            "没有值得建议的就返回空数组，不要凑数。"
        )
        user = "任务列表：\n" + "\n".join(lines)
        if focus_title:
            user += f"\n\n用户当前重点关注：「{focus_title}」，优先围绕它给建议。"
        raw = cls._chat_json(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user},
            ],
            feature=FEAT_SUGGEST,
        )
        items = raw.get("suggestions") if isinstance(raw, dict) else raw
        return _clean_suggestions(items)


# ---------------- fake fixtures ----------------


def _http_error_detail(resp) -> str:
    """HTTP 错误透出服务端 message（OpenAI 兼容 error.message），取不到退回状态码。"""
    try:
        msg = ((resp.json() or {}).get("error") or {}).get("message")
    except Exception:
        msg = None
    return f"HTTP {resp.status_code}：{msg}" if msg else f"HTTP {resp.status_code} {getattr(resp, 'reason', '')}".rstrip()


def _fake_draft(text: str, category_names: List[str]) -> dict:
    cat = next((c for c in category_names if text and c in text), category_names[0] if category_names else "")
    return {
        "title": (text or "AI 解析任务")[:40] or "AI 解析任务",
        "category": cat,
        "priority": "medium",
        "deadline": "",
        "reminder_time": "",
        "details": "（演示数据）ZENTRAY_AI_FAKE 模式生成的任务草稿。",
        "subtasks": ["第一步：确认内容", "第二步：执行", "第三步：收尾"],
    }


def _fake_suggestions(tasks_summary: List[dict]) -> List[dict]:
    first = tasks_summary[0]
    late = next((t for t in tasks_summary if t["deadline"] and t["deadline"] < __import__("datetime").date.today().isoformat()), None)
    out = [
        {
            "type": "split",
            "target_title": first["title"],
            "text": "这条任务颗粒度偏大，建议拆成子任务逐步推进。",
            "patch": {"subtask_titles": ["梳理现状", "列出行动项", "逐项执行"]},
        },
        {
            "type": "review",
            "target_title": "",
            "text": f"当前共 {len(tasks_summary)} 条活跃任务，高优任务建议控制在 3 条以内。",
            "patch": {},
        },
    ]
    if late:
        out.insert(
            0,
            {
                "type": "priority",
                "target_title": late["title"],
                "text": "已过期的事项建议提到高优先尽快清掉。",
                "patch": {"priority": "high"},
            },
        )
    return out
