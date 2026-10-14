#!/usr/bin/env python3
"""AI 资讯日报（ZenTray script 插件，api_version 2）——生成 HTML 报告（可含资讯图片）。

协议见 docs/plugins/PLUGIN_SPEC.md。仅用 Python 标准库。

- 聚合源（免 key，2026-09 实测可用）：Hacker News Algolia JSON API、
  TechCrunch / The Verge / MIT Tech Review / 量子位 的 AI 频道 RSS。
  机器之心 jiqizhixin RSS 已被重定向墙挡住，未收录。
- 图片：各源 RSS 均无 enclosure，按业界 lead-image 方案抓文章页
  og:image（fallback twitter:image / 首个内容图），下载到
  $ZENTRAY_PLUGIN_DATA_DIR/reports/img/ 本地引用（离线可看）。
- 可选 AI 摘要：$ZENTRAY_PLUGIN_DATA_DIR/config.json 顶层 "ai_summary": true
  时把「来源 ─ 标题」（不含任何凭证）POST 到 OpenAI 兼容端点
  （env AI_API_KEY/AI_API_BASE_URL/AI_MODEL_NAME > settings.json 活跃 profile，
  同主程序）；失败只降级为 ⚠ 提示，不影响报告生成。
- 中英对照：默认开启（"bilingual": false 可关），一次 AI 调用批量把全部
  标题+正文译成另一语言（中→英 / 英→中）。日报卡片标题一律以中文为主、
  另一语言以「译」行对照；详情页标题与正文均中英对照，并有按钮切换
  哪种语言在前；失败降级为仅原文。
- 分类：按标题关键词把条目分为 🤖 AI / 📱 数码 / 🌍 时政 三组渲染；
  AI 专属源外另有 The Verge 主站（数码）与 BBC 中文（时政）补量。
- 详情页：每条新闻的卡片整体可点，进入同目录 detail-<日期>-<序号>.html，
  含中英对照长摘要（可切换语言主次）、原文出处（文章 + 来源主页）、
  HN 讨论链接与同分类相关资讯。
- 配置可选，无 config.json 也能跑（全默认值）；键见 config.example.json。
- RESULT 为单行（stdout 协议按行解析）；报告路径写入文案。
"""
from __future__ import annotations

import html as _html
import json
import os
import re
import struct
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ZenTrayPlugin/ai-news-digest"
FETCH_TIMEOUT = 15     # 单请求超时（秒）
AI_TIMEOUT = 30        # AI 摘要端点超时（秒）
# 翻译走 Horizon 范式（Thysrael/Horizon，MIT）：逐条单方向小调用——无批量则
# 无输出截断与漏项；单条失败重试后只降级该条。旧批量方案三连坑：30s 超时、
# 12 条 JSON 拦腰截断（char 2628）、漏翻个别条目，均为批量 payload 自带病。
_TR_TIMEOUT = 45       # 单条翻译调用超时（秒）
_TR_RETRIES = 2        # 每条重试次数（不含首发）
_TR_BACKOFF = (2, 4)   # 重试间隔（秒），指数退避
_TR_DEADLINE = 240     # 全部翻译总预算（秒），plugin timeout_sec 360 留余量
MAX_IMAGE_BYTES = 2 * 1024 * 1024   # 单图上限
MAX_IMAGES = 8         # 最多抓图的条数
MIN_IMG_W, MIN_IMG_H = 400, 200   # 配图最小像素：拦截站标/logo 等占位小图
AI_SYS_PROMPT = "150 字内中文概括今日 AI 资讯主线（模型/产品/融资/政策分组），不逐条复述"
# 常见繁体独用字（新闻高频，逐字核验均有不同简体形——简繁通用的
# 行/大/冷/冰/雪 等绝不能收，误收会把纯简体标题判成繁体源）。
# shortcut: 非全集，生僻繁体字漏检可接受；放开第三方依赖后换 OpenCC t2s
_TRAD_CHARS = set("個們來對時說會後這裡為與體國際網絡數據雲電腦車馬鳥龍鳳漢語學習實現點線發達變錢銀動產應該當歸問間長樂萬專業無論覺視聽寫讀書報紙誌務員區處辦讓開關門協議蘭烏澤連亞歷譴東風氣飛兒貝醫藥劑檢驗測試證據樣權輕愛殺傷毀壞難濕溫熱凍結霧絲綢豐聞導億記錄認識譯詞給雙單質場廠機鐘價買賣費資財貧貼")


# 聚合源：type hn=Algolia JSON / rss=RSS2 或 Atom。lang 进报告标签，cat 为
# 分类落空时的默认归类。
SOURCES = [
    {"id": "hn", "name": "Hacker News", "type": "hn", "lang": "EN", "cat": "AI",
     "url": "https://hn.algolia.com/api/v1/search_by_date?query=AI&tags=story&hitsPerPage=50"},
    {"id": "techcrunch", "name": "TechCrunch AI", "type": "rss", "lang": "EN", "cat": "AI",
     "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"id": "verge", "name": "The Verge AI", "type": "rss", "lang": "EN", "cat": "AI",
     "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"id": "mittr", "name": "MIT Tech Review", "type": "rss", "lang": "EN", "cat": "AI",
     "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed/"},
    {"id": "qbitai", "name": "量子位", "type": "rss", "lang": "ZH", "cat": "AI",
     "url": "https://www.qbitai.com/feed"},
    {"id": "verge-main", "name": "The Verge", "type": "rss", "lang": "EN", "cat": "数码",
     "url": "https://www.theverge.com/rss/index.xml"},
    {"id": "bbc", "name": "BBC 中文", "type": "rss", "lang": "ZH", "cat": "时政",
     "url": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"},
]

# ---------- 分类（数码 / AI / 时政） ----------

CAT_ORDER = ("AI", "数码", "时政")
CAT_BADGE = {"AI": "🤖 AI", "数码": "📱 数码", "时政": "🌍 时政"}


def _cat_re(tokens: str) -> re.Pattern:
    # 英文词加 \b 防子串误命中（如 "ai" 命中 "said"），中文直接子串
    parts = [re.escape(t) if re.search(r"[一-鿿]", t) else rf"\b{re.escape(t)}\b"
             for t in tokens.split()]
    return re.compile("|".join(parts), re.I)


# ponytail: 关键词启发式（时政>数码>AI 依次判，全不中回退源默认类），
# 误判代价只是条目换了分组，不值得上模型分类
_CAT_RULES = (
    ("时政", _cat_re(
        "政策 监管 法案 国会 参议院 众议院 白宫 制裁 关税 选举 当选 法院 判决 裁决 "
        "外交 军事 议会 首脑 大选 执政 government election senate congress white house "
        "court ruling lawsuit tariff sanction sanctions banned regulator regulation "
        "policy minister parliament cabinet vote")),
    ("数码", _cat_re(
        "手机 芯片 显卡 笔记本 耳机 相机 平板 手表 折叠屏 发布会 充电 电池 内存 硬盘 "
        "iphone ipad macbook galaxy pixel airpods smartphone laptop headphone camera "
        "tablet wearable drone chip gpu battery console steam deck switch")),
    ("AI", _cat_re(
        "ai gpt llm openai anthropic gemini claude 模型 大模型 智能体 人工智能 机器学习 "
        "chatbot copilot midjourney sora deepseek qwen neural diffusion transformer agent "
        "grok xai llama mistral kimi 豆包 文心 智谱 千问 通义 "
        "融资 估值 基准 benchmark 推理 inference 训练 微调 fine-tune rag 多模态 具身")),
)


def classify(title: str, default: str | None = None) -> str | None:
    """命中关键词返回对应分组；全不中返回 default（None=无归属）。"""
    text = title or ""
    for cat, rx in _CAT_RULES:
        if rx.search(text):
            return cat
    return default

DEFAULT_CFG = {
    "window_hours": 48,      # 只收最近 N 小时
    "top_n": 12,             # 报告条数
    "min_hn_points": 30,     # HN 最低分（滤噪）
    "max_images": MAX_IMAGES,
    "ai_summary": False,
    "bilingual": True,       # 标题中英对照（一次 AI 批量翻译，失败降级仅原文）
    "extra_rss": [],         # 追加自定义 RSS/Atom URL
}


class SourceError(Exception):
    """单源失败（记 ⚠，不中断其它源）。"""


def emit(line: str) -> None:
    print(line, flush=True)


def _oneline(s: str) -> str:
    return re.sub(r"[\r\n]+", " ", s).strip()


def _scrub(text: str, *secrets) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


def http_get(url: str, timeout: int = FETCH_TIMEOUT) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def http_post(url: str, data: bytes, headers: dict, timeout: int) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


# ---------- 配置 ----------

def load_config(data_dir: Path) -> dict:
    cfg = dict(DEFAULT_CFG)
    p = data_dir / "config.json"
    try:
        user = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    if isinstance(user, dict):
        for k in DEFAULT_CFG:
            if k in user:
                cfg[k] = user[k]
    return cfg


# ---------- 抓取与解析（fetch 可注入，selftest 用假实现） ----------

def parse_time(value: str):
    v = (value or "").strip()
    if not v:
        return None
    try:
        return parsedate_to_datetime(v).astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass
    try:  # ISO（HN/Atom），兼容尾部 Z
        return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse_rss(data: bytes, source: dict, limit: int = 30) -> list[dict]:
    """RSS2 与 Atom 通吃：按本地标签名取节点（命名空间无关）。"""
    root = ET.fromstring(data)
    items = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        title = link = pub = desc = ""
        img = ""
        for ch in node:
            t = _local(ch.tag)
            if t == "title":
                title = _text(ch)
            elif t == "link":
                link = (ch.get("href") or _text(ch)).strip()
            elif t in ("pubdate", "published", "updated", "date"):
                pub = _text(ch)
            elif t in ("description", "summary"):
                desc = _text(ch)
            elif t in ("content", "encoded"):  # content:encoded
                desc = _text(ch) or desc
            elif t in ("thumbnail", "content") and ch.get("url"):
                img = ch.get("url")
        if title and link:
            items.append({"title": strip_html(title, 300), "url": link, "source": source["name"],
                          "lang": source.get("lang", ""), "points": 0,
                          "published": parse_time(pub), "summary": strip_html(desc),
                          "long": strip_html(desc, 1200), "image_hint": img})
        if len(items) >= limit:
            break
    return items


def parse_hn(data: bytes, source: dict) -> list[dict]:
    hits = json.loads(data.decode("utf-8", "replace")).get("hits") or []
    items = []
    for h in hits:
        if not h.get("title") or not h.get("url"):
            continue
        items.append({"title": h["title"], "url": h["url"], "source": source["name"],
                      "lang": source.get("lang", ""), "points": int(h.get("points") or 0),
                      "published": parse_time(h.get("created_at", "")),
                      "summary": strip_html(h.get("story_text") or ""),
                      "long": strip_html(h.get("story_text") or "", 1200),
                      "hn_id": h.get("objectID") or "", "image_hint": ""})
    return items


def fetch_source(source: dict, fetch) -> list[dict]:
    status, data = fetch(source["url"])
    if status != 200:
        raise SourceError(f"HTTP {status}")
    if source["type"] == "hn":
        return parse_hn(data, source)
    return parse_rss(data, source)


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(s: str, limit: int = 200) -> str:
    s = _WS_RE.sub(" ", _TAG_RE.sub(" ", _html.unescape(s or ""))).strip()
    return s[: limit - 1] + "…" if len(s) > limit else s


# ---------- 去重与选题 ----------

def _title_key(t: str) -> str:
    return re.sub(r"[^a-z0-9一-鿿]", "", t.lower())


def _url_key(u: str) -> str:
    p = urllib.parse.urlsplit(u)
    return (p.netloc.lower().removeprefix("www.") + re.sub(r"/+$", "", p.path)).lower()


def dedupe(items: list[dict]) -> list[dict]:
    seen_t, seen_u, out = set(), set(), []
    for it in items:
        tk, uk = _title_key(it["title"]), _url_key(it["url"])
        if tk in seen_t or (uk and uk in seen_u):
            continue
        seen_t.add(tk)
        if uk:
            seen_u.add(uk)
        out.append(it)
    return out


def select_top(items: list[dict], cfg: dict, now) -> list[dict]:
    """窗口过滤 + 打分：HN 分数主导，RSS 按新鲜度；每源至多占 1/2 席位防单源刷屏。"""
    win_start = now - timedelta(hours=int(cfg["window_hours"]))
    fresh = [it for it in items
             if it["published"] is None or it["published"] >= win_start]

    def score(it: dict) -> float:
        if it["points"] > 0:
            return min(it["points"], 500)
        age_h = 24.0
        if it["published"]:
            age_h = max((now - it["published"]).total_seconds() / 3600, 0)
        return max(30.0 - age_h, 1.0)  # 30h 内从 30 线性衰减到 1

    fresh.sort(key=score, reverse=True)
    top_n = max(1, int(cfg["top_n"]))
    # 席位按源名（item 里只有名）：额外源/自定义 RSS 同样受限，防单源刷屏
    quota = {it["source"]: max(top_n // 2, 1) for it in fresh}
    picked, counts = [], {}
    for it in fresh:
        c = counts.get(it["source"], 0)
        if c >= quota.get(it["source"], top_n):
            continue
        counts[it["source"]] = c + 1
        picked.append(it)
        if len(picked) >= top_n:
            break
    return picked


# ---------- 图片：og:image / 首图抓取 + 本地下载 ----------

_META_RE = re.compile(
    r"<meta[^>]+(?:property|name)=['\"](?:og:image|twitter:image)['\"][^>]*>", re.I)
_CONTENT_RE = re.compile(r"content=['\"]([^'\"]+)['\"]", re.I)
_IMG_RE = re.compile(r"<img[^>]+src=['\"]([^'\"]+)['\"]", re.I)
_BAD_IMG = re.compile(r"(logo|icon|avatar|sprite|spacer|\.svg($|\?)|data:)", re.I)


def safe_url(u: str) -> str:
    """只放行 http(s) 链接（防 javascript: 注入报告）。"""
    return u if urllib.parse.urlsplit(u).scheme in ("http", "https") else ""


def extract_image(page_html: str, base_url: str) -> str:
    for m in _META_RE.finditer(page_html):
        for c in _CONTENT_RE.finditer(m.group(0)):
            u = safe_url(urllib.parse.urljoin(base_url, c.group(1)))
            # og:image 也常被站方填成 logo/图标：与首图同规则过滤
            if u and not _BAD_IMG.search(u):
                return u
    for m in _IMG_RE.finditer(page_html):
        u = safe_url(urllib.parse.urljoin(base_url, m.group(1)))
        if u and not _BAD_IMG.search(u):
            return u
    return ""


_EXT_BY_TYPE = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                "image/gif": ".gif"}


def _img_dims(data: bytes) -> tuple[int, int]:
    """从魔数读像素宽高（PNG/GIF/JPEG）；解析不出返回 (0,0) 表示不设限。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data[:4] == b"GIF8" and len(data) >= 10:
        return struct.unpack("<HH", data[6:10])
    if data[:2] == b"\xff\xd8":          # JPEG：逐段找 SOF 帧头
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            m = data[i + 1]
            if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:   # 无长度段
                i += 2
                continue
            ln = int.from_bytes(data[i + 2:i + 4], "big")
            if ln < 2:
                break
            if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                     0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + ln
    return 0, 0


def download_image(url: str, img_dir: Path, fetch) -> str:
    """下载到 img_dir，返回相对文件名；类型/大小不符返回空串。"""
    try:
        status, data = fetch(url)
    except Exception:
        return ""
    if status != 200 or not data or len(data) > MAX_IMAGE_BYTES:
        return ""
    ctype = ""
    # 不引第三方库：从 URL 扩展名与 JPEG/PNG/GIF/WebP 魔数双路判定
    ext = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = _EXT_BY_TYPE.get(ctype, "")
    if data[:3] == b"\xff\xd8\xff":
        ext, ctype = ".jpg", "image/jpeg"
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        ext, ctype = ".png", "image/png"
    elif data[:4] == b"GIF8":
        ext, ctype = ".gif", "image/gif"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        ext, ctype = ".webp", "image/webp"
    if not ext:
        return ""
    w, h = _img_dims(data)
    if w and h and (w < MIN_IMG_W or h < MIN_IMG_H):
        return ""   # 站标/占位小图：宁可无图，不放废图
    import hashlib
    name = hashlib.sha256((url + str(len(data))).encode()).hexdigest()[:16] + ext
    img_dir.mkdir(parents=True, exist_ok=True)
    (img_dir / name).write_bytes(data)
    return name


def collect_images(items: list[dict], img_dir: Path, fetch) -> dict:
    """给前 max_images 条抓图：RSS 自带 image_hint 优先，否则抓文章页提取。"""
    got = {}
    for it in items[: max(1, int(MAX_IMAGES))]:
        cand = safe_url(it.get("image_hint") or "")
        if cand and _BAD_IMG.search(cand):
            cand = ""   # RSS 自带 image 也常是站标/logo
        if not cand:
            try:
                status, data = fetch(it["url"])
                page = data.decode("utf-8", "replace") if status == 200 else ""
            except Exception:
                page = ""
            cand = extract_image(page, it["url"]) if page else ""
        if cand:
            local = download_image(cand, img_dir, fetch)
            if local:
                got[it["url"]] = local
    return got


# ---------- AI 摘要（OpenAI 兼容，env > settings.json 活跃 profile） ----------

def _load_settings_profile() -> dict | None:
    sf = Path(os.environ.get("ZENTRAY_PLUGIN_DATA_DIR", ".")).parent.parent / "settings.json"
    try:
        ai = json.loads(sf.read_text(encoding="utf-8")).get("ai") or {}
    except (OSError, ValueError):
        return None
    profiles = [p for p in (ai.get("api_profiles") or []) if isinstance(p, dict)]
    if not profiles:
        return ai if (ai.get("api_key") or ai.get("base_url") or ai.get("model")) else None
    active = ai.get("active_api_id")
    for p in profiles:
        if p.get("id") == active:
            return p
    return profiles[0]


def ai_config() -> tuple[str, str, str]:
    p = _load_settings_profile() or {}
    key = os.environ.get("AI_API_KEY") or p.get("api_key") or ""
    base = (os.environ.get("AI_API_BASE_URL") or p.get("base_url")
            or "https://api.openai.com/v1").strip()
    model = (os.environ.get("AI_MODEL_NAME") or p.get("model") or "gpt-4o").strip()
    return key, base, model


def ai_summarize(items: list[dict], post=http_post) -> str:
    key, base, model = ai_config()
    if not key:
        raise RuntimeError("未配置 AI_API_KEY")
    lines = "\n".join(f"- [{it['source']}] {it['title']}" for it in items)
    body = json.dumps({"model": model, "messages": [
        {"role": "system", "content": AI_SYS_PROMPT},
        {"role": "user", "content": lines},
    ]}).encode("utf-8")
    status, resp = post(base.rstrip("/") + "/chat/completions", body,
                        {"Content-Type": "application/json",
                         "Authorization": f"Bearer {key}"}, AI_TIMEOUT)
    if status != 200:
        raise RuntimeError(f"HTTP {status}")
    return (json.loads(resp.decode("utf-8", "replace"))
            ["choices"][0]["message"]["content"] or "").strip()


# ---------- 中英对照（一次批量翻译标题+正文） ----------

_CJK_RE = re.compile(r"[一-鿿]")


def is_zh(text: str) -> bool:
    # 含 CJK 即视为中文侧：占比启发式会把「联想天禧…SWE-bench-Live 全球第一」
    # 这类英文专有名词较长的中文标题误判成英文，中文原标题反被降为「译」行
    return bool(_CJK_RE.search(text or ""))


def _has_trad(text: str) -> bool:
    return any(ch in _TRAD_CHARS for ch in (text or ""))


def _translate_one(it: dict, post, key: str, base: str, model: str,
                   *, json_mode: bool = True, insist_jian: bool = False) -> dict:
    """单条翻译一次小调用；返回 {"t","s"}。失败抛错由调用方重试/降级。"""
    target = ("English" if is_zh(it["title"]) and not _has_trad(it["title"])
              else "简体中文")   # 繁体源（BBC 中文部分文章）译简体，译文作主标题
    sys_prompt = (f"你是新闻翻译引擎。把用户给出的新闻标题与正文译成{target}，"
                  "保留专有名词与数字，不添删内容。"
                  '只输出一个 JSON 对象：{"t": "标题译文", "s": "正文译文"}。')
    user = f"TITLE: {it['title']}\nBODY: {it.get('long') or it.get('summary') or ''}"
    if insist_jian:
        user += "\n注意：上一版译文出现了繁体字，本次必须全部改用简体中文。"
    req: dict = {"model": model, "temperature": 0, "messages": [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user}]}
    if json_mode:   # API 级 JSON 模式：模型无法在 JSON 外说废话
        req["response_format"] = {"type": "json_object"}
        req["max_tokens"] = 8192
    status, resp = post(base.rstrip("/") + "/chat/completions",
                        json.dumps(req).encode("utf-8"),
                        {"Content-Type": "application/json",
                         "Authorization": f"Bearer {key}"}, _TR_TIMEOUT)
    if status == 400 and json_mode:   # 端点不支持 response_format/max_tokens：裸请求重试
        return _translate_one(it, post, key, base, model,
                              json_mode=False, insist_jian=insist_jian)
    if status != 200:
        raise RuntimeError(f"HTTP {status}")
    content = (json.loads(resp.decode("utf-8", "replace"))
               ["choices"][0]["message"]["content"] or "").strip()
    content = re.sub(r"^```[a-z]*\s*|\s*```$", "", content).strip()  # 剥代码围栏
    try:
        data = json.loads(content)
    except ValueError:   # JSON 模式失效时兜底：掐首个花括号片段再试
        i, j = content.find("{"), content.rfind("}")
        if i < 0 or j <= i:
            raise ValueError("译文不是 JSON 对象")
        data = json.loads(content[i:j + 1])
    if isinstance(data, str):   # 模型偶尔只回字符串：当标题译文用
        data = {"t": data}
    if not isinstance(data, dict):
        raise ValueError("译文不是 JSON 对象")
    t = _oneline(str(data.get("t") or ""))[:300]
    s = _oneline(str(data.get("s") or ""))[:2000]
    if not t or t == it["title"]:
        raise ValueError("标题译文为空或与原文相同")
    return {"t": t, "s": s}


def translate_items(items: list[dict], post=http_post,
                    sleep=time.sleep, clock=time.monotonic) -> dict[int, dict]:
    """逐条翻译成另一语言；返回 {序号: {"t","s"}}。
    单条重试后仍失败只降级该条；全失败才抛错（调用方整体降级）。"""
    key, base, model = ai_config()
    if not key:
        raise RuntimeError("未配置 AI_API_KEY")
    deadline = clock() + _TR_DEADLINE
    out: dict[int, dict] = {}
    errs: list[str] = []
    for idx, it in enumerate(items, 1):
        if clock() >= deadline:
            errs.append(f"翻译总预算 {_TR_DEADLINE}s 用尽，第 {idx}-{len(items)} 条降级为仅原文")
            break
        v, err = None, None
        for attempt in range(_TR_RETRIES + 1):
            try:
                v, err = _translate_one(it, post, key, base, model), None
                break
            except Exception as e:
                v, err = None, _scrub(str(e), key)
                if attempt < _TR_RETRIES:
                    sleep(_TR_BACKOFF[min(attempt, len(_TR_BACKOFF) - 1)])
        if v and not is_zh(it["title"]) and _has_trad(v["t"]):
            try:   # 繁体检出：强简体重问一次，再繁就保留（含义比字形重要）
                v2 = _translate_one(it, post, key, base, model, insist_jian=True)
                if not _has_trad(v2["t"]):
                    v = v2
            except Exception:
                pass
        if v:
            out[idx] = v
        elif err:
            errs.append(f"第 {idx} 条：{err}")
    if errs and out:
        emit(f"LOG 翻译部分条目失败（对应条目降级为仅原文）：{'；'.join(errs)}")
    if not out:
        raise RuntimeError("; ".join(errs) or "无译文")
    return out


def title_pair(it: dict, tr: dict | None) -> tuple[str, str]:
    """(中文标题, 另一语言标题)；无译文时两侧同为原文（英文原题兜底）。"""
    tr = tr or {}
    if is_zh(it["title"]):
        if _has_trad(it["title"]) and tr.get("t"):   # 繁体源：简体译文为主
            return tr["t"], it["title"]
        return it["title"], tr.get("t") or it["title"]
    return tr.get("t") or it["title"], it["title"]


def body_pair(it: dict, tr: dict | None) -> tuple[str, str]:
    """(中文正文, 另一语言正文)；无译文时两侧同为原文。正文语言随标题侧。"""
    tr = tr or {}
    body = (it.get("long") or it.get("summary") or "").strip()
    s = tr.get("s") or ""
    if is_zh(it["title"]):
        if _has_trad(it["title"]) and s:   # 繁体源：简体译文为主
            return s, body
        return body, s or body
    return s or body, body


# ---------- HTML 报告 ----------

def esc(s: str) -> str:
    return _html.escape(str(s or ""), quote=True)


def fmt_age(published, now) -> str:
    if not published:
        return ""
    h = max((now - published).total_seconds() / 3600, 0)
    return f"{int(h)} 小时前" if h < 48 else f"{int(h // 24)} 天前"


_CSS = """
:root{--bg:#f5f6f8;--card:#fff;--ink:#1d2129;--mut:#86909c;--line:#e5e6eb;--brand:#165dff}
@media (prefers-color-scheme: dark){:root{--bg:#17171a;--card:#232326;--ink:#e8e9ec;--mut:#8b8e98;--line:#313236;--brand:#3c7eff}}
*{box-sizing:border-box} body{margin:0;padding:24px;background:var(--bg);color:var(--ink);
font:14px/1.65 system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:880px;margin:0 auto} h1{font-size:20px;margin:0 0 4px}
.stat{color:var(--mut);font-size:12.5px;margin:0 0 18px}
.ai{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--brand);
border-radius:10px;padding:12px 16px;margin:0 0 18px}
.ai h2{font-size:14px;margin:0 0 6px;color:var(--brand)} .ai p{margin:0;white-space:pre-wrap}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;
display:flex;flex-direction:column;transition:transform .15s ease,border-color .15s ease}
.card:hover{transform:translateY(-2px);border-color:var(--brand)}
.card-img{width:100%;height:140px;object-fit:cover;display:block;background:var(--line)}
.card-b{padding:10px 12px 12px;display:flex;flex-direction:column;gap:6px;flex:1}
.meta{display:flex;gap:8px;align-items:center;color:var(--mut);font-size:12px}
.src{color:var(--brand);font-weight:600} .pts{color:#d97706;margin-left:auto}
h3{font-size:13.5px;margin:0;line-height:1.5} .idx{color:var(--mut)}
a{color:inherit;text-decoration:none} h3 a:hover{color:var(--brand)}
.sum{margin:0;font-size:12.5px;color:var(--mut);display:-webkit-box;-webkit-line-clamp:3;
-webkit-box-orient:vertical;overflow:hidden}
.t9{margin:0;font-size:12.5px;color:var(--mut);border-left:2px solid var(--brand);
padding-left:8px;line-height:1.5} .t9 b{color:var(--brand);font-weight:600;margin-right:4px}
.cat h2{font-size:16px;margin:22px 0 10px} .cat h2 .cnt{color:var(--mut);font-weight:400;
font-size:13px;margin-left:6px}
/* —— 详情页 —— */
.back{display:inline-block;margin-bottom:12px;color:var(--brand);text-decoration:none;
font-size:13px} .back:hover{text-decoration:underline}
.dmeta{color:var(--mut);font-size:12.5px;margin:0 0 16px}
.dimg{width:100%;max-height:380px;object-fit:cover;border-radius:10px;display:block;
margin:0 0 16px;background:var(--line)}
.dsum{font-size:14.5px;line-height:1.85;white-space:pre-wrap;margin:0 0 18px}
.links{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:14px 16px;margin:0 0 12px}
.links h2{font-size:14px;margin:0 0 8px}
.links ul{margin:0;padding-left:20px;font-size:13px;line-height:2.1}
.links a{color:var(--brand)} .links a:hover{text-decoration:underline}
.links .muted{color:var(--mut)}
/* —— 详情页双语段落：默认中文在前，.en-first 时英文在前 —— */
.langbtn{margin:0 0 14px;border:1px solid var(--line);background:var(--card);
color:var(--brand);border-radius:8px;padding:5px 12px;font-size:12.5px;cursor:pointer}
.langbtn:hover{border-color:var(--brand)}
.pair{display:flex;flex-direction:column;gap:10px}
html.en-first .pair{flex-direction:column-reverse}
html:not(.en-first) .pair .en,html.en-first .pair .zh{color:var(--mut)}
footer{margin-top:20px;color:var(--mut);font-size:12px;text-align:center}
"""


def detail_name(date_str: str, i: int) -> str:
    return f"detail-{date_str}-{i}.html"


def render_html(items: list[dict], images: dict, ai_text: str,
                date_str: str, stats: list[str], trans: dict | None = None) -> str:
    trans = trans or {}
    sections = []
    for cat in CAT_ORDER:
        group = [(i, it) for i, it in enumerate(items, 1) if it.get("cat") == cat]
        if not group:
            continue
        cards = []
        for i, it in group:
            local = images.get(it["url"])
            img = (f'<img class="card-img" loading="lazy" src="img/{esc(local)}" alt="">'
                   if local else "")
            pts = (f'<span class="pts">▲ {it["points"]}</span>' if it["points"] else "")
            age = fmt_age(it["published"], datetime.now(timezone.utc))
            # 标题一律中文为主，另一语言（原文或译文）以「译」行对照
            zh_t, alt_t = title_pair(it, trans.get(i))
            t9 = (f'<p class="t9"><b>译</b>{esc(alt_t)}</p>' if alt_t != zh_t else "")
            summ = f'<p class="sum">{esc(it["summary"])}</p>' if it["summary"] else ""
            # 整卡可点 → 详情页；外链全部移到详情页，避免 a 嵌 a
            cards.append(
                f'<a class="card" href="{esc(detail_name(date_str, i))}">{img}<div class="card-b">'
                f'<div class="meta"><span class="src">{esc(it["source"])}</span>'
                f'{f"<span>{esc(age)}</span>" if age else ""}{pts}</div>'
                f'<h3><span class="idx">{i}.</span> {esc(zh_t)}</h3>{t9}{summ}</div></a>')
        sections.append(
            f'<section class="cat"><h2>{CAT_BADGE[cat]}'
            f'<span class="cnt">{len(group)} 条</span></h2>'
            f'<div class="grid">{" ".join(cards)}</div></section>')
    ai_block = (f'<section class="ai"><h2>AI 摘要</h2><p>{esc(ai_text)}</p></section>'
                if ai_text else "")
    stat_line = " · ".join(esc(s) for s in stats)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 资讯日报 {esc(date_str)}</title>
<style>{_CSS}</style></head><body><div class="wrap">
<h1>🤖 AI 资讯日报 · {esc(date_str)}</h1>
<p class="stat">{stat_line}</p>
{ai_block}
{''.join(sections)}
<footer>ZenTray ai-news-digest 生成 · 点卡片进详情 · 图片为本地缓存，链接外开</footer>
</div></body></html>"""


_EXT = 'target="_blank" rel="noopener noreferrer"'


def render_detail(i: int, it: dict, items: list[dict], images: dict,
                  trans: dict, date_str: str) -> str:
    """单条资讯详情页：中英对照图文（可切换语言主次）+ 出处/相关链接。"""
    url = safe_url(it["url"])
    domain = urllib.parse.urlsplit(url).netloc if url else ""
    home = f"{urllib.parse.urlsplit(url).scheme}://{domain}/" if domain else ""
    age = fmt_age(it["published"], datetime.now(timezone.utc))
    pts = f" · ▲ {it['points']}" if it.get("points") else ""
    img = (f'<img class="dimg" src="img/{esc(images[url])}" alt="">' if url in images else "")
    zh_t, alt_t = title_pair(it, (trans.get(i) or {}) if trans else None)
    zh_b, en_b = body_pair(it, (trans.get(i) or {}) if trans else None)
    if not zh_b:
        zh_b = en_b = "（该源未提供内容摘要，请看原文）"
    t9 = (f'<p class="t9"><b>译</b>{esc(alt_t)}</p>' if alt_t != zh_t else "")
    # 有对照才给切换按钮；onclick 内联一行，静态页零依赖
    toggle = (
        '<button class="langbtn" onclick="var h=document.documentElement;'
        "h.classList.toggle('en-first');this.textContent="
        "'语言主次：'+(h.classList.contains('en-first')?'EN 在前（点击切换）'"
        ":'中文在前（点击切换）')\">语言主次：中文在前（点击切换）</button>"
        if zh_b != en_b else "")
    links = []
    if url:
        # 存档副本：原文被墙/被反爬（403）时仍有可点的跳转。
        # 选 archive.ph 而非 web.archive.org：后者在本机网络不可达。
        links.append(f'<li>📰 原文出处：<a href="{esc(url)}" {_EXT}>{esc(domain or url)}</a>'
                     f' — {esc(it["source"])} · '
                     f'<a class="muted" href="https://archive.ph/newest/{esc(url)}"'
                     f' {_EXT}>存档副本</a></li>')
    if home:
        links.append(f'<li>🏠 来源主页：<a href="{esc(home)}" {_EXT}>{esc(domain)}</a></li>')
    if it.get("hn_id"):
        links.append(f'<li>💬 HN 讨论：<a href="https://news.ycombinator.com/item?id='
                     f'{esc(str(it["hn_id"]))}" {_EXT}>news.ycombinator.com</a></li>')
    related = [(j, o) for j, o in enumerate(items, 1)
               if j != i and o.get("cat") == it.get("cat")][:5]
    rel = ([f'<li><a href="{esc(detail_name(date_str, j))}">{esc(title_pair(o, (trans.get(j) or {}) if trans else None)[0])}</a>'
            f'<span class="muted"> · {esc(o["source"])}</span></li>' for j, o in related]
           or ['<li class="muted">今日同分类暂无其它入选条目</li>'])
    cat = it.get("cat") or "AI"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(zh_t)} · AI 资讯日报</title>
<style>{_CSS}</style></head><body><div class="wrap">
<a class="back" href="{esc(date_str)}.html">← 返回日报</a>
<p class="dmeta">{CAT_BADGE[cat]} · 第 {i} 条 · {esc(it["source"])}{(" · " + esc(age)) if age else ""}{pts}</p>
<h1 style="font-size:22px">{esc(zh_t)}</h1>
{t9}
{img}
{toggle}
<div class="pair"><p class="dsum zh">{esc(zh_b)}</p><p class="dsum en">{esc(en_b)}</p></div>
<div class="links"><h2>🔗 出处与链接</h2><ul>{''.join(links) or '<li class="muted">无</li>'}</ul></div>
<div class="links"><h2>📑 相关资讯（同分类）</h2><ul>{''.join(rel)}</ul></div>
<footer>ZenTray ai-news-digest 生成 · 外部链接在新标签页打开</footer>
</div></body></html>"""


# ---------- 主流程 ----------

def run(data_dir: Path, fetch=http_get, post=http_post, out=emit,
        now: datetime | None = None) -> int:
    cfg = load_config(data_dir)
    now = now or datetime.now(timezone.utc)
    sources = list(SOURCES)
    for u in (cfg.get("extra_rss") or []):
        if isinstance(u, str) and u.startswith(("http://", "https://")):
            sources.append({"id": "extra", "name": urllib.parse.urlsplit(u).netloc,
                            "type": "rss", "lang": "", "url": u})

    all_items, failures = [], []
    for i, s in enumerate(sources, 1):
        out(f"PROGRESS {i}/{len(sources) + 1} 拉取 {s['name']}")
        try:
            all_items.extend(fetch_source(s, fetch))
        except Exception as e:
            failures.append(f"{s['name']}: {_oneline(str(e))[:60]}")
            out(f"LOG 源失败 {s['name']}: {e}")

    items = select_top(dedupe(all_items), cfg, now)
    if not items:
        out("RESULT fail 各源均无可收录资讯"
            + (f"（失败：{'；'.join(failures)}）" if failures else ""))
        return 1

    default_cat = {s["name"]: s.get("cat", "AI") for s in sources}
    kept = []
    for it in items:
        matched = classify(it["title"])
        cat = matched or default_cat.get(it["source"], "AI")
        # AI 板块聚焦行业/技术：标题未实锚 AI 关键词的条目不进 AI 组
        # （HN query=AI 为全文检索，标题与 AI 无关的条目在此挡下）
        if cat == "AI" and matched != "AI":
            continue
        it["cat"] = cat
        kept.append(it)
    if not kept:
        out("RESULT fail 今日各源均无聚焦 AI 行业/技术的条目")
        return 1
    items = kept

    out(f"PROGRESS {len(sources) + 1}/{len(sources) + 1} 抓图与渲染")
    images = collect_images(items, data_dir / "reports" / "img", fetch)

    ai_text = ""
    if cfg.get("ai_summary"):
        try:
            ai_text = ai_summarize(items, post)
        except Exception as e:
            ai_text = ""
            out(f"LOG AI 摘要失败（已降级）：{_scrub(str(e), ai_config()[0])}")

    trans = {}
    if cfg.get("bilingual", True):
        try:
            trans = translate_items(items, post)
        except Exception as e:
            trans = {}
            out(f"LOG 标题/正文翻译失败（已降级为仅原文）：{_scrub(str(e), ai_config()[0])}")

    date_str = now.astimezone().strftime("%Y-%m-%d")
    stats = [f"入选 {len(items)} 条", f"配图 {len(images)} 张",
             f"来源 {len({it['source'] for it in items})} 个",
             "分类 " + " / ".join(
                 f"{CAT_BADGE[c].split()[1]} {sum(1 for it in items if it['cat'] == c)}"
                 for c in CAT_ORDER if any(it["cat"] == c for it in items))]
    if trans:
        stats.append(f"中英对照 {len(trans)} 条")
    if failures:
        stats.append(f"失败源 {len(failures)}")
    report = data_dir / "reports" / f"{date_str}.html"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_html(items, images, ai_text, date_str, stats, trans),
                      encoding="utf-8")
    for i, it in enumerate(items, 1):
        (report.parent / detail_name(date_str, i)).write_text(
            render_detail(i, it, items, images, trans, date_str), encoding="utf-8")
    out("RESULT ok " + _oneline(
        f"AI 资讯日报已生成：{report}｜入选 {len(items)} 条（含 {len(items)} 个详情页）、配图 {len(images)} 张"
        + (f"；⚠ 失败源：{'；'.join(failures)}" if failures else "")))
    return 0


def main(argv: list) -> int:
    if "--selftest" in argv:
        return selftest()
    data_dir = Path(os.environ.get("ZENTRAY_PLUGIN_DATA_DIR") or Path(__file__).parent)
    if "ZENTRAY_PLUGIN_DATA_DIR" not in os.environ:
        emit("LOG 未检测到 ZENTRAY_PLUGIN_DATA_DIR，回退用脚本所在目录（仅调试）")
    return run(data_dir)


# ---------- selftest（离线，fetch/post 全注入） ----------

RSS_FIX = b"""<?xml version="1.0"?><rss version="2.0" xmlns:content="x" xmlns:media="y">
<channel><title>t</title>
<item><title><![CDATA[OpenAI <b>releases</b> GPT-6]]></title><link>https://a.com/x</link>
<pubDate>Mon, 28 Sep 2026 10:00:00 +0000</pubDate>
<description>&lt;p&gt;Big &amp; launch&lt;/p&gt;</description></item>
<item><title>Dup of GPT6</title><link>https://other.com/gpt6</link>
<pubDate>Mon, 28 Sep 2026 11:00:00 +0000</pubDate></item>
</channel></rss>"""

ATOM_FIX = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom item</title>
<link rel="alternate" type="text/html" href="https://b.com/1"/>
<published>2026-09-28T12:00:00Z</published><summary>s</summary></entry></feed>"""

HN_FIX = json.dumps({"hits": [
    {"title": "Show HN: AI tool", "url": "https://c.com/1", "points": 120,
     "objectID": "3434343", "created_at": "2026-09-28T13:00:00Z"},
    {"title": "low score", "url": "https://c.com/2", "points": 3,
     "created_at": "2026-09-28T13:00:00Z"},
    {"title": "no url", "url": None, "points": 99, "created_at": "2026-09-28T13:00:00Z"},
]}).encode()

PAGE_FIX = ('<html><head>'
            '<meta property="og:image" content="/cdn/pic.jpg">'
            '<meta name="twitter:image" content="https://t.com/2.jpg"></head>'
            '<body><img src="https://cdn.example/logo.svg"><img src="data:image/png;base64,xx">'
            '<img src="/static/photo.png"></body></html>')

PNG_1x1 = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


class FakeFetch:
    """按 URL 前缀路由的假 fetch；记录请求顺序。"""

    def __init__(self, routes: dict):
        self.routes, self.calls = routes, []

    def __call__(self, url: str, timeout: int = 15) -> tuple[int, bytes]:
        self.calls.append(url)
        for prefix, resp in self.routes.items():
            if url.startswith(prefix):
                return resp if isinstance(resp, tuple) else (200, resp)
        return (404, b"")


def selftest() -> int:  # noqa: C901
    import tempfile
    now = datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc)
    n = [0]

    def check(name: str, cond: bool, detail: str = ""):
        n[0] += 1
        print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
        return cond

    # 1 RSS2 解析（CDATA/实体/strip_html）
    items = parse_rss(RSS_FIX, {"name": "T", "lang": "ZH"})
    check("rss2 解析+strip", len(items) == 2 and items[0]["title"] == "OpenAI releases GPT-6"
          and items[0]["summary"] == "Big & launch", str(items[:1]))
    # 2 时间解析（RFC822 与 ISO Z）
    check("时间解析", parse_time("Mon, 28 Sep 2026 10:00:00 +0000") is not None
          and parse_time("2026-09-28T13:00:00Z") == parse_time("2026-09-28T13:00:00+00:00")
          and parse_time("垃圾") is None)
    # 3 Atom 解析（link href）
    a = parse_rss(ATOM_FIX, {"name": "A", "lang": ""})
    check("atom 解析", len(a) == 1 and a[0]["url"] == "https://b.com/1")
    # 4 HN 解析（滤无 url）
    h = parse_hn(HN_FIX, {"name": "HN", "lang": "EN"})
    check("hn 解析", len(h) == 2 and h[0]["points"] == 120)
    # 5 去重（标题键 + URL 键）
    d = dedupe([{"title": "GPT-6!", "url": "https://a.com/x"},
                {"title": "gpt6", "url": "https://new.com/y"},
                {"title": "Other", "url": "https://www.a.com/x/"},
                {"title": "Other2", "url": "https://z.com/1"}])
    check("去重", len(d) == 2, str([i["title"] for i in d]))
    # 5b 分类（时政>数码>AI 关键词，全不中返回 None 回退源默认）
    check("分类", classify("欧盟通过 AI 出口管制新法案") == "时政"
          and classify("Senate passes chip regulation") == "时政"
          and classify("iPhone 17 Pro 灵动岛评测", "AI") == "数码"
          and classify("OpenAI releases GPT-6") == "AI"
          and classify("Urban said nothing", "数码") == "数码"
          and classify("The market falls", "时政") == "时政"
          and classify("Show HN: a lisp interpreter") is None
          and classify("Mistral 融资 6 亿美元") == "AI"
          and classify("新推理基准刷纪录") == "AI")
    # 6 选题（HN 阈值、窗口、席位）
    pool = h + items + a
    pool = [dict(it, published=now - timedelta(hours=2)) for it in pool] + [
        {"title": "太旧", "url": "https://old.com/1", "source": "T", "lang": "ZH",
         "points": 0, "published": now - timedelta(days=10), "summary": "", "image_hint": ""}]
    top = select_top(pool, dict(DEFAULT_CFG, top_n=3, min_hn_points=30), now)
    check("选题", len(top) == 3 and all(
        (it["points"] >= 30 if it["source"] == "HN" else True) for it in top)
        and "太旧" not in [it["title"] for it in top])
    # 7 og:image 提取（相对→绝对、twitter 兜底、logo/svg/data: 过滤）
    check("og:image", extract_image(PAGE_FIX, "https://p.com/a/")
          == "https://p.com/cdn/pic.jpg")
    no_og = '<html><body><img src="i.png"></body></html>'
    check("首图兜底+过滤", extract_image(
        '<img src="/l.svg"><img src="/i.png">', "https://p.com/") == "https://p.com/i.png"
        and extract_image(no_og, "https://p.com/x/y") == "https://p.com/x/i.png")
    check("og:logo过滤", extract_image(
        '<meta property="og:image" content="/img/logo-v2.png">', "https://p.com/") == "")
    # 8 非法 scheme 防护
    check("scheme 防护", safe_url("javascript:alert(1)") == ""
          and safe_url("https://ok.com/1") != "")
    # 9 图片下载（魔数判定/超限拒绝/404 拒绝）
    with tempfile.TemporaryDirectory() as td:
        img_dir = Path(td) / "img"
        f = FakeFetch({"https://cdn.example/pic.png": PNG_1x1,
                       "https://big.com/x": b"\xff\xd8\xff" + b"\x00" * (MAX_IMAGE_BYTES + 1),
                       "https://404.com/z": (404, b"")})
        name = download_image("https://cdn.example/pic.png", img_dir, f)
        check("图片下载", name.endswith(".png") and (img_dir / name).exists()
              and download_image("https://big.com/x", img_dir, f) == ""
              and download_image("https://404.com/z", img_dir, f) == "", name)

        def png_wh(w, h):
            return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", w, h)

        f2 = FakeFetch({"https://s.com/logo.png": png_wh(300, 300),
                        "https://s.com/pic.png": png_wh(1200, 630)})
        check("小图拦截", download_image("https://s.com/logo.png", img_dir, f2) == ""
              and download_image("https://s.com/pic.png", img_dir, f2).endswith(".png"))
    # 10 collect_images（image_hint 直下 + 文章页提取路径）
    with tempfile.TemporaryDirectory() as td:
        f = FakeFetch({"https://a.com/x": PAGE_FIX.encode(),
                       "https://a.com/cdn/pic.jpg": b"\xff\xd8\xff" + b"\x00" * 60})
        got = collect_images([{"title": "t", "url": "https://a.com/x", "source": "T",
                               "lang": "", "points": 0, "published": None,
                               "summary": "", "image_hint": ""}],
                             Path(td) / "img", f)
        check("collect_images", list(got.values()) and list(got.values())[0].endswith(".jpg"))
    # 11 HTML 渲染（转义 XSS、图片相对引用、AI 块、分组与详情页链接）
    page = render_html(
        [{"title": '<script>alert("x")</script>', "url": "javascript:1",
          "source": "T", "lang": "ZH", "points": 5, "cat": "AI",
          "published": now - timedelta(hours=3), "summary": "<b>bold</b>"},
         {"title": "欧盟出台芯片新规", "url": "https://e.com/1", "source": "B",
          "lang": "ZH", "points": 0, "cat": "时政", "published": None, "summary": ""}],
        {"javascript:1": "deadbeef.png"}, "摘要<b>文本</b>", "2026-09-29",
        ["入选 2 条", "配图 1 张"])
    check("渲染转义", "<script>alert" not in page and "&lt;script&gt;" in page
          and 'href="javascript:1"' not in page and "deadbeef.png" in page
          and "AI 摘要" in page and "&lt;b&gt;bold&lt;/b&gt;" in page)
    check("分组+详情链接", "🤖 AI" in page and "🌍 时政" in page
          and 'href="detail-2026-09-29-1.html"' in page
          and 'href="detail-2026-09-29-2.html"' in page
          and "<h3><a" not in page)
    # 11b 详情页（出处/相关链接/返回日报/同分类互链）
    det_items = [
        {"title": '<script>alert("x")</script>', "url": "https://t.com/x",
         "source": "T", "lang": "ZH", "points": 5, "cat": "AI",
         "published": now - timedelta(hours=3), "summary": "<b>bold</b>",
         "long": "长<b>摘要</b>"},
        {"title": "GPT-7 发布", "url": "https://e.com/2", "source": "B",
         "lang": "ZH", "points": 0, "cat": "AI", "published": None, "summary": ""}]
    det = render_detail(1, det_items[0], det_items, {}, {}, "2026-09-29")
    check("详情页", 'href="2026-09-29.html"' in det and "原文出处" in det
          and "相关资讯" in det and "长&lt;b&gt;摘要&lt;/b&gt;" in det
          and "GPT-7 发布" in det and 'href="detail-2026-09-29-2.html"' in det
          and 'href="javascript:' not in det
          and "https://archive.ph/newest/https://t.com/x" in det)
    # 11c 详情页中英对照：双语标题/正文成对 + 语言主次切换按钮
    bi = {"title": "OpenAI releases GPT-6", "url": "https://t.com/x", "source": "T",
          "lang": "EN", "points": 0, "cat": "AI", "published": None,
          "summary": "EN body", "long": "EN body"}
    det2 = render_detail(1, bi, [bi], {}, {1: {"t": "开放AI发布GPT-6", "s": "英文正文的中文译文"}},
                         "2026-09-29")
    check("详情中英对照+切换", 'class="dsum zh"' in det2 and 'class="dsum en"' in det2
          and "开放AI发布GPT-6" in det2 and "英文正文的中文译文" in det2
          and "EN body" in det2 and 'class="langbtn"' in det2
          and "en-first" in det2 and 'class="langbtn"' not in det,
          "zh/en 应成对且仅对照时给切换按钮")
    # 12 AI 请求形状（system+user、Bearer、失败降级异常）
    os.environ["AI_API_KEY"] = "sk-test-selftest"
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append((url, json.loads(data), headers))
        return (200, json.dumps({"choices": [{"message": {"content": "今日主线…"}}]}).encode())

    txt = ai_summarize([{"source": "T", "title": "x"}], fake_post)
    url, body, headers = calls[0]
    check("ai 请求", txt == "今日主线…" and url.endswith("/chat/completions")
          and body["messages"][0]["content"] == AI_SYS_PROMPT
          and headers["Authorization"].startswith("Bearer "))

    def bad_post(url, data, headers, timeout):
        return (500, b"{}")

    try:
        ai_summarize([{"source": "T", "title": "x"}], bad_post)
        ok = False
    except RuntimeError as e:
        ok = "HTTP 500" in str(e)
    check("ai 失败抛错", ok)
    # 12b 中英对照：语言判定 / 批量翻译（围栏 JSON）/ 非法输出抛错
    check("is_zh 判定", is_zh("量子位发布新一代模型") and not is_zh("OpenAI releases GPT-6")
          and is_zh("联想天禧自研智能体TianxiCode斩获SWE-bench-Live全球第一")
          and not is_zh("") and not is_zh(" "))
    tr_items = [{"title": "OpenAI releases GPT-6", "long": "Big launch day",
                 "summary": "Big launch"},
                {"title": "量子位发布模型", "long": "正文很长", "summary": "正文"},
                {"title": "same same"}]
    tr_seen, tr_slept = [], []
    _TR_ANS = {"OpenAI releases GPT-6": ("开放AI发布GPT-6", "发布日"),
               "量子位发布模型": ("QbitAI releases a model", "Long body")}

    def _req_title(req) -> str:
        m = re.search(r"^TITLE: (.*)", req["messages"][1]["content"], re.M)
        return m.group(1) if m else ""

    def tr_post(url, data, headers, timeout):   # 按请求标题作答；"same same" 永不回
        req = json.loads(data)
        tr_seen.append(req)
        t = _req_title(req)
        if t in _TR_ANS:
            content = ("```json\n" + json.dumps({"t": _TR_ANS[t][0], "s": _TR_ANS[t][1]},
                                                ensure_ascii=False) + "\n```")
        else:
            content = "不是 JSON"
        return (200, json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    tr = translate_items(tr_items, tr_post, sleep=tr_slept.append)
    check("逐条翻译", tr == {1: {"t": "开放AI发布GPT-6", "s": "发布日"},
                             2: {"t": "QbitAI releases a model", "s": "Long body"}}
          and "简体中文" in tr_seen[0]["messages"][0]["content"]
          and "TITLE: OpenAI releases GPT-6" in tr_seen[0]["messages"][1]["content"]
          and "BODY: Big launch day" in tr_seen[0]["messages"][1]["content"]
          and tr_seen[0].get("response_format") == {"type": "json_object"}
          and len(tr_seen) == 5 and tr_slept == [2, 4],
          str((tr, len(tr_seen), tr_slept)))  # 第 3 条 3 次尝试全败 → 降级
    try:
        translate_items(tr_items, lambda *a: (200, json.dumps(
            {"choices": [{"message": {"content": "不是 JSON"}}]}).encode()),
                        sleep=lambda s: None)
        ok = False
    except (ValueError, RuntimeError):
        ok = True
    check("翻译非JSON抛错", ok)
    rc_calls, rc_slept = [], []

    def retry_post(url, data, headers, timeout):
        rc_calls.append(1)
        if len(rc_calls) == 1:
            return (500, b"")
        return (200, json.dumps({"choices": [
            {"message": {"content": '{"t": "译x", "s": ""}'}}]}).encode())

    check("重试后成功", translate_items([{"title": "x"}], retry_post,
                                        sleep=rc_slept.append)
          == {1: {"t": "译x", "s": ""}} and rc_slept == [2],
          str((rc_calls, rc_slept)))
    jf_modes = []

    def jf_post(url, data, headers, timeout):
        req = json.loads(data)
        jf_modes.append("json" if "response_format" in req else "plain")
        if "response_format" in req:
            return (400, b"")
        return (200, json.dumps({"choices": [
            {"message": {"content": '{"t": "译y", "s": ""}'}}]}).encode())

    check("json_object 400 降级", translate_items([{"title": "y"}], jf_post,
                                                  sleep=lambda s: None)
          == {1: {"t": "译y", "s": ""}} and jf_modes == ["json", "plain"],
          str(jf_modes))
    trad_calls = []

    def trad_post(url, data, headers, timeout):
        req = json.loads(data)
        reasked = "繁体" in req["messages"][1]["content"]
        trad_calls.append(reasked)
        t = "特朗普与普京达成协议" if reasked else "特朗普與普京達成協議"
        return (200, json.dumps({"choices": [{"message": {
            "content": json.dumps({"t": t, "s": ""}, ensure_ascii=False)}}]},
            ensure_ascii=False).encode())

    check("繁体重问", translate_items([{"title": "Trump and Putin reach a deal"}],
                                      trad_post, sleep=lambda s: None)
          == {1: {"t": "特朗普与普京达成协议", "s": ""}}
          and trad_calls == [False, True], str(trad_calls))
    ticks = iter([0, 0] + [10 ** 9] * 10)
    check("总预算用尽降级", list(translate_items(
        [{"title": "a"}, {"title": "b"}], lambda *a: (200, json.dumps({"choices": [
            {"message": {"content": '{"t": "译a", "s": ""}'}}]}).encode()),
        sleep=lambda s: None, clock=lambda: next(ticks))) == [1])
    check("字符串译文兼容", translate_items(
        [{"title": "t"}], lambda *a: (200, json.dumps({"choices": [
            {"message": {"content": '"译t"'}}]}).encode()), sleep=lambda s: None)
        == {1: {"t": "译t", "s": ""}})
    # 英文条目：中文主标题 + 英文原题进「译」行
    page = render_html(
        [{"title": "OpenAI releases GPT-6", "url": "https://a.com/x", "source": "T",
          "lang": "EN", "points": 0, "cat": "AI", "published": None, "summary": ""}],
        {}, "", "2026-09-29", [], {1: {"t": "<b>开放AI发布GPT-6</b>", "s": "x"}})
    check("t9 渲染", "开放AI发布GPT-6" in page and "&lt;b&gt;开放AI发布GPT-6&lt;/b&gt;" in page
          and 'class="t9"' in page and "OpenAI releases GPT-6" in page
          and "中英对照" not in page)
    # 中文条目：原中文为主，英文译文进「译」行
    page_zh = render_html(
        [{"title": "量子位发布模型", "url": "https://a.com/y", "source": "Q",
          "lang": "ZH", "points": 0, "cat": "AI", "published": None, "summary": ""}],
        {}, "", "2026-09-29", [], {1: {"t": "QbitAI releases a model", "s": "y"}})
    check("中文原题主位", "<h3><span class=\"idx\">1.</span> 量子位发布模型</h3>" in page_zh
          and "QbitAI releases a model" in page_zh)
    # 繁体源（BBC 中文部分文章）：译简体作主标题，繁体原文进「译」行
    dir_seen = []

    def dir_post(url, data, headers, timeout):
        req = json.loads(data)
        dir_seen.append(req["messages"][0]["content"])
        return (200, json.dumps({"choices": [{"message": {"content": json.dumps(
            {"t": "泽连斯基谴责美俄柴油交易", "s": "简体正文"},
            ensure_ascii=False)}}]}, ensure_ascii=False).encode())

    trd = {"title": "澤連斯基譴責美俄柴油交易", "long": "繁體正文"}
    check("繁体源译简体", translate_items([trd], dir_post, sleep=lambda s: None)
          == {1: {"t": "泽连斯基谴责美俄柴油交易", "s": "简体正文"}}
          and "简体中文" in dir_seen[0] and "English" not in dir_seen[0],
          str(dir_seen))
    check("繁体源主位", title_pair(trd, {"t": "泽连斯基谴责美俄柴油交易"})
          == ("泽连斯基谴责美俄柴油交易", "澤連斯基譴責美俄柴油交易")
          and body_pair(trd, {"s": "简体正文"}) == ("简体正文", "繁體正文"))
    page2 = render_html(
        [{"title": "t", "url": "https://a.com/x", "source": "T", "lang": "",
          "points": 0, "cat": "AI", "published": None, "summary": ""}], {}, "", "d", [], None)
    check("无译文不渲染t9", 'class="t9"' not in page2)
    # 13 run() 端到端（假网络、报告落盘、RESULT 单行、详情页成对落盘）
    with tempfile.TemporaryDirectory() as td:
        lines = []
        routes = {
            "https://hn.algolia.com": HN_FIX,
            "https://techcrunch.com": RSS_FIX,
            "https://www.theverge.com": (429, b""),
            "https://www.technologyreview.com": (200, b"<rss></rss>"),
            "https://www.qbitai.com": RSS_FIX,
            "https://feeds.bbci.co.uk": RSS_FIX,
            "https://a.com/x": PAGE_FIX.encode(),
            "https://p.com/cdn/pic.jpg": b"\xff\xd8\xff" + b"\x00" * 60,
            "https://b.com/1": (200, b"<html></html>"),
            "https://c.com/1": (200, b"<html></html>"),
        }
        rc = run(Path(td), fetch=FakeFetch(routes), post=lambda *a: (500, b""),
                 out=lines.append, now=now)
        result = [l for l in lines if l.startswith("RESULT")]
        # 主报告与 detail-* 区分（同目录混放，glob 顺序不可依赖）
        rep = next(p for p in (Path(td) / "reports").glob("*.html")
                   if not p.name.startswith("detail-"))
        rep_txt = rep.read_text(encoding="utf-8")
        details = sorted((Path(td) / "reports").glob("detail-*.html"))
        check("run 端到端", rc == 0 and rep is not None and len(result) == 1
              and "\n" not in result[0] and "RESULT ok" in result[0])
        check("失败源进文案", "The Verge AI" in result[0])
        check("报告含条目", '<a class="card"' in rep_txt and "🤖 AI" in rep_txt)
        check("翻译失败降级", 'class="t9"' not in rep_txt)
        n_cards = rep_txt.count('<a class="card"')
        check("详情页落盘", n_cards > 0 and len(details) == n_cards
              and all("原文出处" in d.read_text(encoding="utf-8")
                      and "相关资讯" in d.read_text(encoding="utf-8") for d in details))
    # 13b run() 翻译成功链路（报告含对照行与统计）
    with tempfile.TemporaryDirectory() as td:
        lines = []
        routes = {
            "https://hn.algolia.com": HN_FIX,
            "https://techcrunch.com": RSS_FIX,
            "https://www.theverge.com": RSS_FIX,
            "https://www.technologyreview.com": (200, b"<rss></rss>"),
            "https://www.qbitai.com": RSS_FIX,
            "https://feeds.bbci.co.uk": RSS_FIX,
            "https://a.com/x": (200, b"<html></html>"),
            "https://other.com/gpt6": (200, b"<html></html>"),
            "https://c.com/1": (200, b"<html></html>"),
        }

        _RUN_ANS = {"OpenAI releases GPT-6": ("开放AI发布GPT-6", "中文正文1"),
                    "Dup of GPT6": ("GPT-6 重复报道", "中文正文2"),
                    "Show HN: AI tool": ("AI 工具展示", "中文正文3"),
                    "Atom item": ("原子条目", "")}

        def ok_post(url, data, headers, timeout):
            req = json.loads(data)
            m = re.search(r"^TITLE: (.*)", req["messages"][1]["content"], re.M)
            if m:   # 逐条翻译请求
                t, s = _RUN_ANS.get(m.group(1), (m.group(1) + "译", ""))
                content = json.dumps({"t": t, "s": s}, ensure_ascii=False)
            else:   # ai_summarize：任意摘要文本
                content = "今日要点：模型发布"
            return (200, json.dumps({"choices": [{"message": {"content": content}}]}).encode())

        rc = run(Path(td), fetch=FakeFetch(routes), post=ok_post, out=lines.append, now=now)
        rep = next(p for p in (Path(td) / "reports").glob("*.html")
                   if not p.name.startswith("detail-"))
        txt = rep.read_text(encoding="utf-8")
        check("翻译成功链路", rc == 0 and 'class="t9"' in txt
              and "开放AI发布GPT-6" in txt and "中英对照" in txt)
    # 14 无可收录 → RESULT fail
    with tempfile.TemporaryDirectory() as td:
        lines = []
        rc = run(Path(td), fetch=FakeFetch({s["url"].split("?")[0]: (200, b"<rss></rss>")
                                          for s in SOURCES}), post=lambda *a: (500, b""),
                 out=lines.append, now=now)
        check("空结果 fail", rc == 1 and any(l.startswith("RESULT fail") for l in lines))

    print(f"selftest: {n[0]} checks, done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
