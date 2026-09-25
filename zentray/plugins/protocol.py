"""插件 stdout 进度协议解析。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_PROGRESS_RE = re.compile(
    r"^PROGRESS\s+(\d+)\s*/\s*(\d+)\s*(.*)$",
    re.IGNORECASE,
)
_RESULT_RE = re.compile(
    r"^RESULT\s+(ok|fail)(?:\s+(.*))?$",
    re.IGNORECASE,
)
_LOG_RE = re.compile(r"^LOG\s+(.*)$", re.IGNORECASE)


@dataclass
class ProgressLine:
    current: int
    total: int
    message: str


@dataclass
class ParsedLine:
    kind: str  # progress | log | result | raw
    text: str
    progress: Optional[ProgressLine] = None
    result_ok: Optional[bool] = None


def parse_stdout_line(line: str) -> ParsedLine:
    """解析插件 stdout 单行。"""
    s = (line or "").rstrip("\n\r")
    if not s.strip():
        return ParsedLine(kind="raw", text="")

    m = _PROGRESS_RE.match(s.strip())
    if m:
        cur, total = int(m.group(1)), int(m.group(2))
        msg = (m.group(3) or "").strip()
        return ParsedLine(
            kind="progress",
            text=msg or f"{cur}/{total}",
            progress=ProgressLine(current=cur, total=total, message=msg),
        )

    m = _RESULT_RE.match(s.strip())
    if m:
        ok = m.group(1).lower() == "ok"
        reason = (m.group(2) or "").strip()
        text = "成功" if ok else (reason or "失败")
        return ParsedLine(kind="result", text=text, result_ok=ok)

    m = _LOG_RE.match(s.strip())
    if m:
        return ParsedLine(kind="log", text=m.group(1).strip())

    return ParsedLine(kind="raw", text=s.strip())


def format_tray_text(
    plugin_name: str,
    parsed: ParsedLine,
    *,
    max_len: int = 50,
) -> str:
    """生成托盘截断文案。"""
    if parsed.kind == "progress" and parsed.progress:
        p = parsed.progress
        body = f"{p.current}/{p.total}"
        if p.message:
            body = f"{body} {p.message}"
        text = f"⚡ {body}"
    else:
        text = f"⚡ {parsed.text or plugin_name}"
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text
