#!/usr/bin/env python3
"""暮省：复盘报告生成（原内置「每日复盘」，2026-10 迁移为插件）。

数据经 $ZENTRAY_PLUGIN_DATA_DIR 上两级定位 DATA_DIR：settings.json 取 AI
profile、复盘风格与 save_local 参数预设；active_tasks.json 取高优先任务；
archive/YYYY-MM-DD.log 取当日执行记录。报告写入 DATA_DIR/reviews/
review-YYYY-MM-DD.md（同日多次自增 -N，旧名 YYYY-MM-DD.md 计为第 1 篇，
历史面板直接可查）。调度（周期/时刻/周几/几号/跳过公休日）由应用侧触发器
按参数预设执行，脚本本身只管生成。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

KIND = "review"  # settings.json 中 ai.review（风格所在）
PID = "musheng"
DEFAULT_TIME = "23:30"

_FALLBACK_PROMPT = "你是一个效率教练。请根据用户待办情况输出 Markdown。"


def emit(line: str) -> None:
    print(line, flush=True)


def http_post(url: str, data: bytes, headers: dict, timeout: int) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _ai_config(settings: dict) -> tuple[str, str, str]:
    """env AI_API_KEY/AI_API_BASE_URL/AI_MODEL_NAME > settings.json 活跃 profile。"""
    ai = (settings.get("ai") or {}) if isinstance(settings, dict) else {}
    p = {}
    profiles = [x for x in (ai.get("api_profiles") or []) if isinstance(x, dict)]
    if profiles:
        active = ai.get("active_api_id")
        p = next((x for x in profiles if x.get("id") == active), profiles[0])
    key = os.environ.get("AI_API_KEY") or p.get("api_key") or ""
    base = (os.environ.get("AI_API_BASE_URL") or p.get("base_url")
            or "https://api.openai.com/v1").strip()
    model = (os.environ.get("AI_MODEL_NAME") or p.get("model") or "gpt-4o").strip()
    return key, base, model


def _active_style(settings: dict) -> tuple[str, str]:
    """复盘风格（设置-AI 维护）：active_style_id 命中 → toxic → 首个。"""
    job = ((settings.get("ai") or {}).get(KIND) or {})
    styles = [s for s in (job.get("styles") or []) if isinstance(s, dict)]
    sid = job.get("active_style_id")
    for s in styles:
        if s.get("id") == sid and (s.get("system_prompt") or "").strip():
            return s.get("name") or sid, s["system_prompt"]
    for s in styles:
        if s.get("id") == "toxic" and (s.get("system_prompt") or "").strip():
            return s.get("name") or "toxic", s["system_prompt"]
    if styles and (styles[0].get("system_prompt") or "").strip():
        return styles[0].get("name") or "默认", styles[0]["system_prompt"]
    return "默认", _FALLBACK_PROMPT


def _flag(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _save_local(settings: dict) -> bool:
    """参数预设 save_local（缺省 true，与 manifest 默认一致）。"""
    ops = (settings.get("ops") or {}) if isinstance(settings, dict) else {}
    presets = ops.get("param_presets") or {}
    v = (presets.get(PID) or {}).get("save_local") if isinstance(presets, dict) else None
    return True if v is None else _flag(v)


def _next_filename(reviews: Path, today: str) -> tuple[str, int]:
    """同日多次生成自增序号：review-DATE.md / review-DATE-N.md（旧名 DATE.md 计 1）。"""
    existing = 0
    for p in reviews.iterdir():
        name = p.name
        if name == f"{today}.md":
            existing = max(existing, 1)
        elif name == f"review-{today}.md":
            existing = max(existing, 1)
        elif name.startswith(f"review-{today}-") and name.endswith(".md"):
            mid = name[len(f"review-{today}-"):-3]
            if mid.isdigit():
                existing = max(existing, int(mid))
    seq = existing + 1
    return (f"review-{today}.md", 1) if seq == 1 else (f"review-{today}-{seq}.md", seq)


def _ai_chat(cfg: tuple[str, str, str], system_prompt: str, prompt: str, post) -> str:
    key, base, model = cfg
    if not key:
        return ""
    try:
        body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
        }).encode("utf-8")
        status, resp = post(
            base.rstrip("/") + "/chat/completions", body,
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            45,
        )
        if status != 200:
            return ""
        return (json.loads(resp.decode("utf-8"))["choices"][0]["message"]["content"]
                or "").strip()
    except Exception:
        return ""


def run(data_dir: Path, post=http_post, now=None, out=emit) -> int:
    now = now or dt.datetime.now()
    today = now.strftime("%Y-%m-%d")
    settings = _load_json(data_dir / "settings.json") or {}
    tasks = _load_json(data_dir / "active_tasks.json") or []

    log_file = data_dir / "archive" / f"{today}.log"
    log_content = ""
    if log_file.exists():
        log_content = log_file.read_text(encoding="utf-8")

    high = [t for t in tasks
            if isinstance(t, dict) and t.get("priority") == "high"]
    pending_str = "\n".join(
        f"- [{t.get('category') or '工作'}] {t.get('title') or 'Untitled'} "
        f"(Deadline: {t.get('deadline')})"
        for t in high
    )

    prompt = (f"以下是我今天（{today}）的待办执行归档记录：\n"
              f"{log_content if log_content else '今天一条都没做，烂透了。'}\n\n"
              f"以下是明天死线迫在眉睫的紧急高危任务：\n"
              f"{pending_str if pending_str else '暂无紧急任务。'}\n\n"
              f"请为我生成一份每日总结与明日规划。")
    style_name, system_prompt = _active_style(settings)
    ai_reply = _ai_chat(_ai_config(settings), system_prompt, prompt, post)

    report = f"# 📅 ZenTray 禅定复盘 ({today})\n\n"
    report += f"> ⏱️ 生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')} (防折叠标识)\n\n"
    if ai_reply:
        report += f"## 🤖 AI 教练锐评（{style_name}）\n{ai_reply}\n\n"
    else:
        report += "## 🤖 AI 教练锐评\n（生成失败或未配置 API Key）\n\n"
    report += "## 📌 高优先任务\n" + (pending_str or "暂无") + "\n"

    filename = ""
    if _save_local(settings):
        reviews = data_dir / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        filename, _ = _next_filename(reviews, today)
        (reviews / filename).write_text(report, encoding="utf-8")

    if ai_reply:
        out(f"RESULT ok 已生成今日复盘（{style_name}）{filename and '→ ' + filename}")
    else:
        out(f"RESULT ok AI 未生成（未配置 Key 或调用失败），已写高优先任务 {filename}".strip())
    return 0


def main() -> int:
    if "ZENTRAY_PLUGIN_DATA_DIR" not in os.environ:
        emit("LOG 未检测到 ZENTRAY_PLUGIN_DATA_DIR，回退当前目录（仅调试）")
        data_dir = Path.cwd()
    else:
        data_dir = Path(os.environ["ZENTRAY_PLUGIN_DATA_DIR"]).resolve().parent.parent
    return run(data_dir)


if __name__ == "__main__":
    sys.exit(main())
