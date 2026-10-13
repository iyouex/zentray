#!/usr/bin/env python3
"""邮箱新邮件日报（ZenTray script 插件，api_version 2）。

协议见 docs/plugins/PLUGIN_SPEC.md。仅用 Python 标准库。

- 账号：$ZENTRAY_PLUGIN_DATA_DIR/config.json（参照插件目录 config.example.json）
  支持 password 与 XOAUTH2（Gmail / Microsoft / custom）双轨认证、多文件夹。
- 状态：$ZENTRAY_PLUGIN_DATA_DIR/state.json
  水位键 "账号名|folder"（旧版无 "|" 的键视为 "账号名|INBOX"，无损迁移）；
  XOAUTH2 access_token 缓存键 "__token__账号名"。
- 新邮件判定：有水位 → UID > last_uid（UIDVALIDITY 变化按首次处理）；
  首次 → 最近 24 小时（Date 头）。
- IMAP 只读：LOGIN/AUTHENTICATE / SELECT(readonly=True) / UID FETCH BODY.PEEK /
  LOGOUT，不置已读标志；密码与各类令牌绝不进日志/输出。
- 可选 AI 概览：config 顶层 "ai_summary": true 时把「发件人 ─ 主题」列表
  （不含任何凭证）POST 到 OpenAI 兼容端点，生成每账号概览 + 总体总结；
  失败只降级为 ⚠ 提示。
- HTML 报告：reports/<日期>.html——每账号 AI 概览 + 邮件列表；点邮件进
  detail-<日期>-<序号>.html 详情页：正文、附件（≤10MB 本地落盘可直接打开，
  超限只列名）、网页版邮箱登录链接（查看/恢复邮件；Gmail 按 Message-ID 深链）。
  账号级 webmail 链接可用 config "webmail" 字段指定，主流 host 有默认值。
- RESULT 为单行（stdout 协议按行解析，多行 RESULT 会被截断），
  账号节用「｜」、邮件行用「；」分隔，文案含报告路径。
"""
from __future__ import annotations

import email.policy
import hashlib
import html as _html
import imaplib

# RFC2971 ID 不在 imaplib 内建命令表，发前注册（网易系需要，见 process_account）
imaplib.Commands["ID"] = ("AUTH", "SELECTED")
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

MAX_LIST = 50        # 单账号最多列出的邮件数，超出只列最新 N 封
TOKEN_TIMEOUT = 15   # OAuth2 令牌端点超时（秒）
AI_TIMEOUT = 30      # AI 概览端点超时（秒）
MAX_BODY_CHARS = 60_000             # 详情页正文上限（字符）
MAX_ATT_BYTES = 10 * 1024 * 1024    # 单附件落盘上限，超出只列名与大小
AI_OV_SYS = ("你是邮箱日报编辑。按账号分组概括新邮件重点：每账号 80 字内概览，"
             "按重要度排序不逐封复述；再给 120 字内总体总结。"
             '只输出 JSON：{"accounts":[{"name":"账号名","brief":"…"}],"overall":"…"}')
TOKEN_KEY_PREFIX = "__token__"  # state 里令牌缓存键前缀（水位键都含 "|"，不冲突）

# 网页版邮箱默认入口（查看/恢复邮件用）；账号 config "webmail" 可覆盖
WEBMAIL = {"imap.gmail.com": "https://mail.google.com",
           "imap.163.com": "https://mail.163.com",
           "imap.126.com": "https://mail.126.com",
           "imap.qq.com": "https://mail.qq.com",
           "outlook.office365.com": "https://outlook.live.com/mail/"}

GMAIL = {"url": "https://oauth2.googleapis.com/token", "scope": "https://mail.google.com/"}
M365_SCOPE = "https://outlook.office365.com/IMAP.AccessAsUser.All offline_access"


class AccountError(Exception):
    """单账号失败（进汇总失败节，不中断其它账号）。"""


# ---------- 小工具 ----------

def emit(line: str) -> None:
    print(line, flush=True)


def _oneline(s: str) -> str:
    """协议是按行的：字段内任何换行都压成空格。"""
    return re.sub(r"[\r\n]+", " ", s).strip()


def _scrub(text: str, *secrets) -> str:
    """双保险：任何敏感串出现在文案里都替换为 ***。"""
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


def extract_headers(raw: bytes) -> dict:
    """从头部字节块取 Date/From/Subject（字节级解析，含折叠行展开）。

    不用 email.parser：compat32 会把未经 RFC2047 的原始 utf-8 头破坏成
    替换字符，default 策略对折叠 encoded-word 有解码问题；这里只要 3 个
    固定头，手工解析最可控。
    """
    headers, current = {}, None
    for line in raw.splitlines():
        if line[:1] in (b" ", b"\t") and current:
            headers[current] += b" " + line.strip()
            continue
        mm = re.match(rb"(Date|From|Subject|Message-ID)\s*:\s*(.*)", line, re.IGNORECASE)
        if mm:
            current = mm.group(1).decode("ascii").lower()
            headers[current] = mm.group(2).strip()
        else:
            current = None
    return headers


def decode_hdr_bytes(value: bytes) -> str:
    """头值解码：纯 ASCII 走 RFC2047；含原始 8 位按 utf-8 兜底（不规范但常见）。"""
    if not value:
        return ""
    try:
        s = value.decode("ascii")
    except UnicodeDecodeError:
        return value.decode("utf-8", "replace").strip()
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return s.strip()


def sender_display(from_value: bytes) -> str:
    if not from_value:
        return "未知发件人"
    try:
        s = from_value.decode("ascii")  # encoded word 保持原样进 parseaddr（防显示名含逗号）
    except UnicodeDecodeError:  # 原始 utf-8 头：整体解码后取显示名/地址
        name, addr = parseaddr(from_value.decode("utf-8", "replace"))
        return name.strip() or addr or "未知发件人"
    name, addr = parseaddr(s)
    name = decode_hdr_bytes(name.encode("ascii")) if name else ""
    return name or addr or "未知发件人"


def parse_date(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(str(value))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()  # 转本地时区


def fmt_time(dt, now) -> str:
    if dt is None:
        return "--:--"
    return dt.strftime("%H:%M") if dt.date() == now.date() else dt.strftime("%m-%d %H:%M")


# ---------- HTTP（令牌 / AI，可注入以便自测） ----------

def http_post(url: str, data, headers: dict, timeout: int):
    """POST；dict → x-www-form-urlencoded，bytes → 原样。返回 (status, body)。

    HTTPError 折叠成 (code, body) 向上；其余异常（网络等）由调用方归类。
    """
    if isinstance(data, dict):
        payload = urllib.parse.urlencode(data).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded", **headers}
    else:
        payload = data
    req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# ---------- 配置与状态 ----------

def load_config(data_dir: Path):
    """返回 (accounts | None, ai_summary, path, reason)。

    兼容旧版纯数组格式；新版对象 {"accounts": [...], "ai_summary": bool}。
    None = 配置缺失/非法/为空。
    """
    path = data_dir / "config.json"
    try:
        raw = json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        return None, False, path, "文件不存在"
    except json.JSONDecodeError as e:
        return None, False, path, f"JSON 非法（第 {e.lineno} 行）"
    except OSError as e:
        return None, False, path, f"读取失败（{e.__class__.__name__}）"

    if isinstance(raw, list):
        items, ai_summary = raw, False
    elif isinstance(raw, dict):
        items, ai_summary = raw.get("accounts"), bool(raw.get("ai_summary"))
    else:
        return None, False, path, "应为账号对象数组"
    if not isinstance(items, list) or not items:
        return None, False, path, "应为非空的账号对象数组（或 {\"accounts\": [...]}）"

    accounts = []
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            return None, False, path, f"第 {i} 项不是对象"
        name = str(item.get("name") or f"账号{i}").strip() or f"账号{i}"
        host = str(item.get("host") or "").strip()
        user = str(item.get("user") or "").strip()
        auth = str(item.get("auth") or "password")
        if auth not in ("password", "xoauth2"):
            return None, False, path, f"账号「{name}」auth 必须是 password|xoauth2"
        if auth == "password" and not str(item.get("password") or ""):
            return None, False, path, f"账号「{name}」缺少 password"
        if not (host and user):
            return None, False, path, f"账号「{name}」缺少 host/user"

        oauth = None
        if auth == "xoauth2":
            oauth = item.get("oauth2")
            if not isinstance(oauth, dict):
                return None, False, path, f"账号「{name}」缺 oauth2 配置对象"
            provider = oauth.get("provider")
            if provider not in ("gmail", "microsoft", "custom"):
                return None, False, path, f"账号「{name}」oauth2.provider 必须是 gmail|microsoft|custom"
            if not (oauth.get("client_id") and oauth.get("refresh_token")):
                return None, False, path, f"账号「{name}」oauth2 缺 client_id/refresh_token"
            if provider == "microsoft" and not oauth.get("tenant"):
                return None, False, path, f"账号「{name}」oauth2.microsoft 需要 tenant"
            if provider == "custom" and not oauth.get("token_url"):
                return None, False, path, f"账号「{name}」oauth2.custom 需要 token_url"

        folders = item.get("folders")
        if folders is None:
            folders = ["INBOX"]
        if (not isinstance(folders, list) or not folders
                or any(not isinstance(f, str) or not f.strip() for f in folders)):
            return None, False, path, f"账号「{name}」folders 必须是非空字符串数组"
        try:
            port = int(item.get("port") or 993)
        except (TypeError, ValueError):
            return None, False, path, f"账号「{name}」port 非法"
        accounts.append({"name": name, "host": host, "port": port,
                         "ssl": bool(item.get("ssl", True)), "user": user,
                         "auth": auth, "password": str(item.get("password") or ""),
                         "oauth2": oauth, "folders": list(dict.fromkeys(folders)),
                         "webmail": str(item.get("webmail") or WEBMAIL.get(host) or "")})
    return accounts, ai_summary, path, ""


def load_state(path: Path) -> dict:
    """读 state.json；旧版无 "|" 的水位键无损迁移为 "账号名|INBOX"。"""
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {(k if ("|" in k or k.startswith(TOKEN_KEY_PREFIX)) else k + "|INBOX"): v
            for k, v in data.items()}


def save_state(path: Path, state: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(path)


# ---------- OAuth2 令牌 ----------

def token_endpoint(oauth: dict):
    """(url, scope)：Gmail / Microsoft 固定端点，custom 用配置的 token_url。"""
    provider = oauth["provider"]
    if provider == "gmail":
        return GMAIL["url"], GMAIL["scope"]
    if provider == "microsoft":
        return (f"https://login.microsoftonline.com/{oauth['tenant']}"
                f"/oauth2/v2.0/token", M365_SCOPE)
    return oauth["token_url"], str(oauth.get("scope") or "")


def get_access_token(acct: dict, states: dict, new_states: dict, post) -> str:
    """取 access_token；state 里未过期则复用。错误文案只含 HTTP 状态与 provider 名。"""
    oauth = acct["oauth2"]
    provider = oauth["provider"]
    key = TOKEN_KEY_PREFIX + acct["name"]
    cached = states.get(key) or new_states.get(key) or {}
    if cached.get("value") and time.time() < float(cached.get("expires_at") or 0):
        return cached["value"]

    url, scope = token_endpoint(oauth)
    form = {"grant_type": "refresh_token",
            "refresh_token": oauth["refresh_token"],
            "client_id": oauth["client_id"]}
    if oauth.get("client_secret"):
        form["client_secret"] = oauth["client_secret"]
    if scope:
        form["scope"] = scope
    try:
        status, body = post(url, form, {}, TOKEN_TIMEOUT)
    except Exception:
        raise AccountError(f"令牌获取失败（{provider}）：网络错误")
    if status != 200:
        # 文案仅含 HTTP 状态与 provider 名；refresh_token/client_secret 一概不出现
        raise AccountError(f"令牌获取失败（{provider}）：HTTP {status}")
    try:
        data = json.loads(body.decode("utf-8", "replace"))
        token = data["access_token"]
        expires_in = int(data.get("expires_in") or 3600)
    except Exception:
        raise AccountError(f"令牌获取失败（{provider}）：响应异常")
    new_states[key] = {"value": token,
                       "expires_at": time.time() + expires_in - 300}  # 提前 5 分钟过期
    return token


def _xoauth2_reason(challenge) -> str:
    """从 XOAUTH2 challenge（JSON，可能 base64）提取失败原因；取不到给空串。"""
    if not challenge:
        return ""
    raw = challenge if isinstance(challenge, bytes) else str(challenge).encode()
    candidates = [raw]
    try:
        import base64
        candidates.append(base64.b64decode(raw))
    except Exception:
        pass
    for c in candidates:
        try:
            j = json.loads(c.decode("utf-8", "replace"))
        except Exception:
            continue
        reason = j.get("sasl_error") or j.get("error") or ""
        if reason:
            return f"{reason} {j.get('description') or ''}".strip()
    return ""


# ---------- IMAP ----------

def http_connect_tunnel(proxy, host: str, port: int, timeout: float,
                        sock_factory=socket.create_connection):
    """经本地 HTTP 代理 CONNECT 隧道连到 (host, port)，返回未包 TLS 的裸 socket。"""
    raw = sock_factory(proxy, timeout)
    raw.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = raw.recv(4096)
        if not chunk:
            raise OSError("代理无响应")
        buf += chunk
    if b" 200 " not in buf.split(b"\r\n")[0]:
        raise OSError(f"代理 CONNECT 失败: {buf.split(b'\r\n')[0][:60].decode('utf-8', 'replace')}")
    return raw


class ProxyIMAP4SSL(imaplib.IMAP4_SSL):
    """经 HTTP 代理隧道的 IMAP4_SSL：Gmail 等直连被墙的邮箱用。
    config 里账号级 proxy_host/proxy_port 指定本地代理（如 clash 7897）。"""

    def __init__(self, host, port, proxy, timeout=None):
        self.proxy = proxy
        super().__init__(host, port, timeout=timeout)  # 本机 imaplib timeout 仅限关键字

    def open(self, host="", port=imaplib.IMAP4_SSL_PORT, timeout=None):
        self.host, self.port = host, port
        raw = http_connect_tunnel(self.proxy, host, port, timeout or 30)
        self.sock = self.ssl_context.wrap_socket(raw, server_hostname=host)
        self.file = self.sock.makefile("rb")


def default_connect(ssl: bool, host: str, port: int, proxy=None):
    if proxy and ssl:
        return ProxyIMAP4SSL(host, port, proxy)
    cls = imaplib.IMAP4_SSL if ssl else imaplib.IMAP4
    return cls(host, port)


def search_uids(m, *criteria) -> list:
    typ, data = m.uid("search", None, *criteria)
    if typ != "OK" or not data or not data[0]:
        return []
    if isinstance(data[0], bytes):
        return [int(u) for u in data[0].split()]
    return [int(u) for u in str(data[0]).split()]


def _parse_message(raw: bytes) -> tuple[str, list]:
    """(正文, [{"name","size","data"}])。这里才用 email 解析器——头部仍走
    extract_headers 的字节级解析（compat32/default 各有头部坑，正文没有）。"""
    msg = BytesParser(policy=email.policy.default).parsebytes(raw)
    plain = htmlpart = ""
    for part in msg.walk():
        if part.get_content_maintype() != "text" or part.get_filename():
            continue
        # 不走 get_content()：缺 charset 的 part 会被按 ASCII 解出乱码，
        # 手解字节 + utf-8 兜底（中文邮件漏标 charset 的不少）
        data = part.get_payload(decode=True) or b""
        cs = part.get_content_charset() or "utf-8"
        try:
            text = data.decode(cs, "replace")
        except LookupError:
            text = data.decode("utf-8", "replace")
        if part.get_content_subtype() == "plain" and not plain:
            plain = text
        elif part.get_content_subtype() == "html" and not htmlpart:
            htmlpart = text
    body = plain or re.sub(r"<[^>]+>", " ", _html.unescape(htmlpart or ""))
    body = body.replace("\r\n", "\n").strip()[:MAX_BODY_CHARS]
    atts = []
    for part in msg.walk():
        name = part.get_filename()
        if not name:
            continue
        # 不规范 8 位文件名会产生代理字符，写盘/渲染前替换掉
        name = name.encode("utf-8", "replace").decode("utf-8")
        try:
            data = part.get_payload(decode=True) or b""
        except Exception:
            data = b""
        atts.append({"name": _oneline(name), "size": len(data), "data": data})
    return body, atts


def _save_atts(atts: list, att_dir: Path) -> None:
    """附件落盘（≤MAX_ATT_BYTES），就地补 href（相对 reports/ 的 att/ 名）。"""
    for a in atts:
        a["href"] = ""
        if not a["data"] or a["size"] > MAX_ATT_BYTES:
            continue
        safe = re.sub(r"[/\\\x00]", "_", a["name"])[:80] or "attachment"
        fname = hashlib.sha1(a["data"]).hexdigest()[:10] + "-" + safe
        att_dir.mkdir(parents=True, exist_ok=True)
        (att_dir / fname).write_bytes(a["data"])
        a["href"] = f"att/{fname}"


def fetch_rows(m, uids, att_dir: Path) -> list:
    """按给定 UID 取整封邮件，返回 [{dt,sender,subject,mid,body,atts}]，保 UID 升序。"""
    typ, data = m.uid("fetch", ",".join(str(u) for u in uids), "(UID BODY.PEEK[])")
    by_uid = {}
    if typ == "OK":
        for item in data or []:
            if isinstance(item, tuple) and len(item) >= 2:
                mm = re.search(rb"UID (\d+)", item[0])
                if not mm:
                    continue
                uid = int(mm.group(1))
                hdrs = extract_headers(item[1])
                body, atts = _parse_message(item[1])
                _save_atts(atts, att_dir)
                by_uid[uid] = {
                    "dt": parse_date(decode_hdr_bytes(hdrs.get("date", b"")) or None),
                    "sender": sender_display(hdrs.get("from", b"")),
                    "subject": _oneline(decode_hdr_bytes(hdrs.get("subject", b""))) or "（无主题）",
                    "mid": hdrs.get("message-id", b"").decode("ascii", "replace").strip(),
                    "body": body, "atts": atts}
    return [by_uid[u] for u in uids if u in by_uid]


def process_account(acct: dict, states: dict, now, connect, post, new_states: dict, out,
                    att_dir: Path) -> dict:
    """单账号（认证 + 逐文件夹）：水位写入 new_states，返回 {name, rows, truncated, acct}。

    异常向上抛（AccountError 或 imaplib/socket 异常 → 计入失败节）。
    """
    proxy = ((acct["proxy_host"], int(acct["proxy_port"]))
             if acct.get("proxy_host") and acct.get("proxy_port") else None)
    m = (connect(acct["ssl"], acct["host"], acct["port"], proxy=proxy) if proxy
         else connect(acct["ssl"], acct["host"], acct["port"]))
    try:
        if acct["auth"] == "xoauth2":
            token = get_access_token(acct, states, new_states, post)
            sasl = (b"user=" + acct["user"].encode("utf-8")
                    + b"\x01auth=Bearer " + token.encode("utf-8") + b"\x01\x01")
            challenge = {}

            def cb(data):
                if data:
                    challenge["data"] = data
                return sasl

            try:
                m.authenticate("XOAUTH2", cb)
            except Exception as e:
                reason = _xoauth2_reason(challenge.get("data")) or f"{type(e).__name__}: {e}"
                raise AccountError(_scrub(f"XOAUTH2 认证失败：{reason}", token))
        else:
            m.login(acct["user"], acct["password"])

        # 网易系（163/126/企业邮）登录后必须先发 ID，否则 SELECT 报
        # "Unsafe Login"（实测 NO SELECT Unsafe Login）；其他服务器支持或
        # 无视 ID，不支持时这里失败也不致命
        try:
            m._simple_command("ID", '("name" "ZenTray" "version" "1.0")')
        except Exception:
            pass

        rows_all, truncated_any = [], False
        for folder in acct["folders"]:
            typ, _ = m.select(folder, readonly=True)
            if typ != "OK":
                raise AccountError(f"SELECT {folder} 失败: {typ}")
            uidvalidity = 0
            key, val = m.response("UIDVALIDITY")
            if key and val and val[0]:
                try:
                    uidvalidity = int(val[0])
                except (TypeError, ValueError):
                    uidvalidity = 0

            skey = f"{acct['name']}|{folder}"
            prev = states.get(skey)
            have_state = bool(prev) and prev.get("uidvalidity") == uidvalidity and uidvalidity
            if have_state:
                last = int(prev.get("last_uid") or 0)
                uids = [u for u in search_uids(m, "UID", f"{last + 1}:*") if u > last]
                max_uid = max(uids) if uids else last
                cutoff = None
            else:  # 首次运行或 UIDVALIDITY 变化：回退取最近 24 小时
                cutoff = now - timedelta(hours=24)
                uids = search_uids(m, "SINCE", cutoff.strftime("%d-%b-%Y"))
                all_uids = search_uids(m, "ALL")  # 水位：全箱最大 UID
                max_uid = max(all_uids) if all_uids else 0

            truncated = len(uids) > MAX_LIST
            if truncated:
                uids = uids[-MAX_LIST:]
            rows = fetch_rows(m, uids, att_dir) if uids else []
            if cutoff is not None:
                rows = [r for r in rows if r["dt"] is None or r["dt"] >= cutoff]
            new_states[skey] = {"uidvalidity": uidvalidity, "last_uid": max_uid}
            rows_all += rows
            truncated_any = truncated_any or truncated
            out(f"LOG {acct['name']}/{folder}：取到 {len(rows)} 封")
        return {"name": acct["name"], "rows": rows_all, "truncated": truncated_any,
                "acct": acct}
    finally:
        try:
            m.logout()
        except Exception:
            pass


# ---------- AI 摘要（配置解析与 mem-advisor 同款） ----------

def _load_settings_profile() -> dict | None:
    """settings.json 的 ai 活跃 profile（DATA_DIR/plugin_data/<id>/ 上两级即 DATA_DIR）。"""
    sf = Path(os.environ.get("ZENTRAY_PLUGIN_DATA_DIR", ".")).parent.parent / "settings.json"
    try:
        ai = json.loads(sf.read_text(encoding="utf-8")).get("ai") or {}
    except (OSError, ValueError):
        return None
    profiles = [p for p in (ai.get("api_profiles") or []) if isinstance(p, dict)]
    if not profiles:
        # 旧版单 key 布局（同主程序 _parse_ai 的兜底）
        if ai.get("api_key") or ai.get("base_url") or ai.get("model"):
            return ai
        return None
    active = ai.get("active_api_id")
    for p in profiles:
        if p.get("id") == active:
            return p
    return profiles[0]


def ai_config() -> tuple[str, str, str]:
    """(api_key, base_url, model)；环境变量（与主程序同名）逐项优先于活跃 profile。"""
    p = _load_settings_profile() or {}
    key = os.environ.get("AI_API_KEY") or p.get("api_key") or ""
    base = (os.environ.get("AI_API_BASE_URL") or p.get("base_url")
            or "https://api.openai.com/v1").strip()
    model = (os.environ.get("AI_MODEL_NAME") or p.get("model") or "gpt-4o").strip()
    return key, base, model


def ai_overview(sections: list, now, post) -> tuple[dict, str]:
    """AI 概览：({账号名: 概览}, 总体总结)。请求不含任何凭证；
    非 JSON 输出整段当总结（概览留空，报告仍可出）。"""
    key, base, model = ai_config()
    if not key:
        raise RuntimeError("未配置 AI_API_KEY")
    listing = "\n".join(
        f"【{s['name']}】\n" + "\n".join(
            f"{fmt_time(r['dt'], now)} {r['sender']} ─ {r['subject']}"
            for r in s["rows"])
        for s in sections if s["rows"])
    body = json.dumps({"model": model, "messages": [
        {"role": "system", "content": AI_OV_SYS},
        {"role": "user", "content": listing}]}).encode("utf-8")
    status, resp = post(base.rstrip("/") + "/chat/completions", body,
                        {"Content-Type": "application/json",
                         "Authorization": f"Bearer {key}"}, AI_TIMEOUT)
    if status != 200:
        raise RuntimeError(f"HTTP {status}")
    content = (json.loads(resp.decode("utf-8", "replace"))
               ["choices"][0]["message"]["content"] or "").strip()
    try:
        i, j = content.find("{"), content.rfind("}")
        data = json.loads(content[i:j + 1]) if i >= 0 else {}
    except ValueError:
        data = {}
    if isinstance(data, dict) and (data.get("accounts") or data.get("overall")):
        briefs = {str(a.get("name")): _oneline(str(a.get("brief") or ""))
                  for a in data.get("accounts") or [] if isinstance(a, dict)}
        return briefs, _oneline(str(data.get("overall") or ""))
    return {}, _oneline(content)


# ---------- 汇总 ----------

def build_summary(sections: list, failures: list, total: int, now, ai_part=None) -> str:
    """单行汇总（stdout 协议按行解析，不能输出真换行）。"""
    parts = []
    for s in sections:
        n = len(s["rows"])
        head = f"【{s['name']}】新增 {n} 封" if n else f"【{s['name']}】无新邮件"
        if s["truncated"]:
            head += f"（超 {MAX_LIST} 封，仅列最新 {MAX_LIST} 封）"
        if n:
            head += "：" + "；".join(
                f"{fmt_time(r['dt'], now)} {_oneline(r['sender'])} ─ {r['subject']}"
                for r in s["rows"])
        parts.append(head)
    if failures:
        parts.append("失败：" + "；".join(f"{_oneline(nm)}（{_oneline(err)}）" for nm, err in failures))
    if ai_part:
        parts.append(ai_part)
    parts.append(f"共 {total} 封")
    return "｜".join(parts)


# ---------- HTML 报告 ----------

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
.acc h2{font-size:16px;margin:22px 0 10px} .acc h2 .cnt{color:var(--mut);font-weight:400;
font-size:13px;margin-left:6px}
.list{display:flex;flex-direction:column;gap:8px}
a.row{display:flex;gap:10px;align-items:baseline;background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:10px 14px;text-decoration:none;color:inherit}
a.row:hover{border-color:var(--brand)}
.tm{color:var(--mut);font-size:12px;white-space:nowrap} .fr{font-weight:600}
.sj{flex:1} .atn{color:#d97706;font-size:12px;white-space:nowrap}
.empty{color:var(--mut);background:var(--card);border:1px dashed var(--line);
border-radius:10px;padding:12px 14px}
.back{display:inline-block;margin-bottom:12px;color:var(--brand);text-decoration:none;font-size:13px}
.back:hover{text-decoration:underline}
.dmeta{color:var(--mut);font-size:12.5px;margin:0 0 16px}
.dbody{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;
white-space:pre-wrap;line-height:1.8;margin:0 0 16px}
.links{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:14px 16px;margin:0 0 12px}
.links h2{font-size:14px;margin:0 0 8px} .links ul{margin:0;padding-left:20px;font-size:13px;line-height:2.1}
.links a{color:var(--brand)} .links a:hover{text-decoration:underline} .links .muted{color:var(--mut)}
footer{margin-top:20px;color:var(--mut);font-size:12px;text-align:center}
"""

_EXT = 'target="_blank" rel="noopener noreferrer"'


def esc(s) -> str:
    return _html.escape(str(s or ""), quote=True)


def detail_name(date_str: str, i: int) -> str:
    return f"detail-{date_str}-{i}.html"


def _fmt_size(n: int) -> str:
    return f"{n / 1048576:.1f}MB" if n >= 1048576 else f"{max(n // 1024, 1)}KB"


def webmail_links(acct: dict, row: dict) -> list:
    """[(文案, url)]：Gmail 按 Message-ID 深链直达 + 各账号网页版登录入口。"""
    links = []
    mid = row.get("mid") or ""
    if "gmail" in acct["host"] and mid:
        links.append(("在 Gmail 网页版打开本邮件（查看/恢复）",
                      "https://mail.google.com/mail/u/0/#search/rfc822msgid%3A"
                      + urllib.parse.quote(mid, safe="")))
    wm = acct.get("webmail") or ""
    if wm:
        links.append(("网页版邮箱登录（查看 / 恢复邮件）", wm))
    return links


def render_html(date_str: str, sections: list, briefs: dict, overall: str,
                failures: list, total: int, now) -> str:
    secs = []
    for s in sections:
        if s["rows"]:
            brief = briefs.get(s["name"])
            bhtml = (f'<div class="ai"><h2>AI 概览</h2><p>{esc(brief)}</p></div>' if brief else "")
            rows = "".join(
                f'<a class="row" href="{esc(r["detail"])}">'
                f'<span class="tm">{fmt_time(r["dt"], now)}</span>'
                f'<span class="fr">{esc(r["sender"])}</span>'
                f'<span class="sj">{esc(r["subject"])}</span>'
                + (f'<span class="atn">📎 {len(r["atts"])}</span>' if r["atts"] else "")
                + "</a>"
                for r in s["rows"])
            body = f'<div class="list">{rows}</div>'
        else:
            bhtml, body = "", '<p class="empty">无新邮件</p>'
        secs.append(f'<section class="acc"><h2>📮 {esc(s["name"])}'
                    f'<span class="cnt">{len(s["rows"])} 封</span></h2>{bhtml}{body}</section>')
    ai_html = (f'<section class="ai"><h2>AI 总览</h2><p>{esc(overall)}</p></section>'
               if overall else "")
    fail_html = ('<section class="acc"><h2>⚠ 失败账号</h2><p class="empty">'
                 + "；".join(f"{esc(n)}（{esc(e)}）" for n, e in failures)
                 + "</p></section>" if failures else "")
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>邮箱日报 {esc(date_str)}</title>
<style>{_CSS}</style></head><body><div class="wrap">
<h1>📬 邮箱日报 · {esc(date_str)}</h1>
<p class="stat">账号 {len(sections)} 个 · 新邮件 {total} 封</p>
{ai_html}
{''.join(secs)}
{fail_html}
<footer>ZenTray email-digest 生成 · 点邮件进详情 · 附件与网页版邮箱链接在详情页</footer>
</div></body></html>"""


def render_detail(date_str: str, acct: dict, row: dict) -> str:
    atts = "".join(
        (f'<li><a href="{esc(a["href"])}" download>{esc(a["name"])}</a>'
         f'<span class="muted"> · {_fmt_size(a["size"])}</span></li>')
        if a.get("href") else
        f'<li class="muted">{esc(a["name"])} · {_fmt_size(a["size"])}（超限未落盘）</li>'
        for a in row["atts"])
    links = "".join(
        f'<li><a href="{esc(u)}" {_EXT}>{esc(t)}</a></li>'
        for t, u in webmail_links(acct, row))
    body = row["body"] or "（无文本正文，请到网页版邮箱查看）"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(row["subject"])} · 邮箱日报</title>
<style>{_CSS}</style></head><body><div class="wrap">
<a class="back" href="{esc(date_str)}.html">← 返回日报</a>
<p class="dmeta">📮 {esc(acct["name"])} · {esc(fmt_time(row["dt"], datetime.now().astimezone()))} · {esc(row["sender"])}</p>
<h1 style="font-size:20px">{esc(row["subject"])}</h1>
<div class="dbody">{esc(body)}</div>
<div class="links"><h2>📎 附件</h2><ul>{atts or '<li class="muted">无</li>'}</ul></div>
<div class="links"><h2>🔗 网页版邮箱</h2><ul>{links or '<li class="muted">未配置入口：config.json 账号里加 "webmail" 字段</li>'}</ul></div>
<footer>ZenTray email-digest 生成 · 外部链接在新标签页打开</footer>
</div></body></html>"""


# ---------- 主流程 ----------

def run(data_dir: Path, connect, out, post=None) -> int:
    post = post or http_post
    now = datetime.now().astimezone()
    accounts, ai_summary, cfg_path, reason = load_config(data_dir)
    if accounts is None:
        out(f"RESULT fail 配置缺失：{reason}；路径 {cfg_path}，"
            f"请参照 config.example.json 创建")
        return 1

    state_path = data_dir / "state.json"
    states = load_state(state_path)
    sections, failures = [], []
    new_states = dict(states)
    total = 0
    reports_dir = data_dir / "reports"
    att_dir = reports_dir / "att"

    for i, acct in enumerate(accounts, 1):
        out(f"PROGRESS {i}/{len(accounts)} {acct['name']}")
        out(f"LOG 连接 {acct['host']}:{acct['port']}（{'SSL' if acct['ssl'] else '明文'}，"
            f"{acct['auth']}）")
        oc = acct.get("oauth2") or {}
        try:
            res = process_account(acct, states, now, connect, post, new_states, out, att_dir)
        except Exception as e:
            err = _scrub(f"{type(e).__name__}: {e}"[:80],
                         acct.get("password"),
                         oc.get("refresh_token"), oc.get("client_secret"))
            out(f"LOG 账号「{acct['name']}」失败：{err}")
            failures.append((acct["name"], err))
            continue
        total += len(res["rows"])
        sections.append(res)

    if len(failures) == len(accounts):
        out("RESULT fail 全部账号失败：" +
            "；".join(f"{nm}: {err}" for nm, err in failures))
        return 1

    ai_part, briefs, overall = None, {}, ""
    if ai_summary and total > 0:
        out("LOG 生成 AI 概览")
        try:
            briefs, overall = ai_overview(sections, now, post)
            if overall:
                ai_part = "AI 摘要：" + overall
        except Exception as e:
            ai_part = "⚠ AI 摘要失败"  # 不带细节，防令牌误泄
            out(f"LOG AI 摘要失败：{type(e).__name__}")

    save_state(state_path, new_states)
    date_str = now.strftime("%Y-%m-%d")
    report = reports_dir / f"{date_str}.html"
    report.parent.mkdir(parents=True, exist_ok=True)
    i = 0
    for s in sections:   # detail 序号与列表渲染顺序一致（跨账号全局递增）
        for r in s["rows"]:
            i += 1
            r["detail"] = detail_name(date_str, i)
            (report.parent / r["detail"]).write_text(
                render_detail(date_str, s["acct"], r), encoding="utf-8")
    report.write_text(
        render_html(date_str, sections, briefs, overall, failures, total, now),
        encoding="utf-8")
    out("RESULT ok 邮箱日报已生成：" + str(report) + "｜"
        + build_summary(sections, failures, total, now, ai_part))
    return 0


def main(argv: list) -> int:
    if "--selftest" in argv:
        return selftest()
    data_dir = os.environ.get("ZENTRAY_PLUGIN_DATA_DIR", "")
    if data_dir:
        path = Path(data_dir)
    else:  # ZenTray 运行时恒注入；此处仅便于终端手工调试
        emit("LOG 未检测到 ZENTRAY_PLUGIN_DATA_DIR，回退用脚本所在目录（仅调试）")
        path = Path(__file__).resolve().parent
    return run(path, default_connect, emit)


# ---------- selftest（仅测试用，正常运行不带 --selftest） ----------

class FakeIMAP4_SSL:
    """canned IMAP 模拟：login/authenticate/select/uid(search|fetch)/logout。

    mailboxes: host -> {"ok": bool, "folders": {folder: [msgs]},
                        "reject_xoauth2": bool}，msg = {uid, date, from, subject}。
    search 支持 UID n:*（按 IMAP 语义至少含最后一封）、SINCE、ALL。
    记录 login_calls / auth_log[(mech, sasl)] / selects[folder] 供断言。
    """

    mailboxes: dict = {}
    instances: list = []

    def __init__(self, host, port=993):
        cfg = self.mailboxes[host]
        self.host, self.port = host, port
        self._ok = cfg["ok"]
        self._folders = cfg["folders"]
        self._reject = cfg.get("reject_xoauth2", False)
        self._current = []
        self.login_calls = 0
        self.auth_log = []
        self.selects = []
        FakeIMAP4_SSL.instances.append(self)

    @classmethod
    def reset(cls):
        cls.instances = []

    def login(self, user, password):
        self.login_calls += 1
        if not self._ok:
            raise imaplib.IMAP4.error("authentication failed")

    def authenticate(self, mechanism, authobject):
        import base64
        self.auth_log.append((mechanism, authobject(b"")))  # 初始响应
        if self._reject:  # 服务器 challenge（JSON 错误）后拒绝
            challenge = base64.b64encode(json.dumps(
                {"status": "400", "sasl_error": "invalid_grant",
                 "description": "refresh token expired"}).encode())
            authobject(challenge)  # 客户端回包（cb 会记录 challenge）
            raise imaplib.IMAP4.error("AUTHENTICATE failed")
        return "OK", [b"Authenticated"]

    def select(self, mailbox="INBOX", readonly=False):
        self.selects.append(mailbox)
        msgs = self._folders.get(mailbox)
        if msgs is None:
            return "NO", [b"NO no such mailbox"]
        self._current = msgs
        return "OK", [str(len(msgs)).encode()]

    def response(self, key):
        if key == "UIDVALIDITY":
            return "UIDVALIDITY", [b"1"]
        return None, [None]

    def uid(self, command, *args):
        if command == "search":
            crit = [a.decode() if isinstance(a, bytes) else str(a) for a in args if a is not None]
            all_uids = [msg["uid"] for msg in self._current]
            uids, i = all_uids, 0
            while i < len(crit):
                c = crit[i]
                if c == "UID":
                    lo = int(crit[i + 1].split(":")[0])
                    uids = [u for u in uids if u >= lo] or (all_uids[-1:] if all_uids else [])
                    i += 2
                elif c == "SINCE":
                    day = datetime.strptime(crit[i + 1], "%d-%b-%Y").date()
                    uids = [msg["uid"] for msg in self._current
                            if msg["uid"] in uids and parse_date(msg["date"]).date() >= day]
                    i += 2
                else:  # ALL 等
                    i += 1
            return "OK", [b" ".join(str(u).encode() for u in uids)]
        if command == "fetch":
            wanted = {int(x) for x in str(args[0]).split(",")}
            items = []
            for seq, msg in enumerate(self._current, 1):
                if msg["uid"] not in wanted:
                    continue
                raw = (f"Date: {msg['date']}\r\nFrom: {msg['from']}\r\n"
                       f"Subject: {msg['subject']}\r\n"
                       f"Message-ID: <{msg['uid']}@fake.test>\r\n")
                if msg.get("att"):
                    import base64 as _b64
                    raw += (f'Content-Type: multipart/mixed; boundary="bb"\r\n\r\n'
                            f'--bb\r\nContent-Type: text/plain\r\n\r\n'
                            f'{msg.get("body", "")}\r\n'
                            f'--bb\r\nContent-Type: application/octet-stream\r\n'
                            f'Content-Disposition: attachment; filename="{msg["att"][0]}"\r\n'
                            f'Content-Transfer-Encoding: base64\r\n\r\n'
                            + _b64.b64encode(msg["att"][1]).decode() + "\r\n--bb--\r\n")
                else:
                    raw += f"\r\n{msg.get('body', '')}"
                raw_b = raw.encode("utf-8")
                meta = f"{seq} (UID {msg['uid']} BODY[] {{{len(raw_b)}}}".encode()
                items.append((meta, raw_b))
                items.append(b")")
            return "OK", items
        raise ValueError(command)

    def logout(self):
        return "BYE", [b"Fake logout"]


class FakeHTTP:
    """canned 令牌 / chat 端点；记录全部调用供断言。"""

    def __init__(self):
        self.calls = []                # (url, data)
        self.token_status = 200
        self.token_expires_in = 3600
        self.chat_status = 200
        self.chat_reply = "重点：服务器巡检完成与季度会议安排。"

    @property
    def token_calls(self):
        return sum(1 for u, _ in self.calls if "/chat/completions" not in u)

    @property
    def chat_calls(self):
        return sum(1 for u, _ in self.calls if "/chat/completions" in u)

    def __call__(self, url, data, headers, timeout):
        self.calls.append((url, data))
        if "/chat/completions" in url:
            if self.chat_status != 200:
                return self.chat_status, b"{}"
            return 200, json.dumps(
                {"choices": [{"message": {"content": self.chat_reply}}]}).encode()
        if self.token_status != 200:
            return self.token_status, b"{}"
        return 200, json.dumps({"access_token": "fake-at-token-XYZ",
                                "expires_in": self.token_expires_in}).encode()


def selftest() -> int:
    import tempfile
    from email.header import Header

    tmp = Path(tempfile.mkdtemp(prefix="email-digest-selftest-"))
    now = datetime.now().astimezone()
    ds = lambda h: (now - timedelta(hours=h)).strftime("%a, %d %b %Y %H:%M:%S +0800")
    enc_subject = Header("会议纪要：第三季度", "utf-8").encode()  # RFC2047
    enc_sender = Header("王五", "utf-8").encode()

    def run_once(cfg, mailboxes, http=None):
        """跑一次 run()，返回 (exit_code, lines, instances, http)。"""
        data_dir = cfg["dir"]
        (data_dir / "config.json").write_text(
            json.dumps(cfg["config"], ensure_ascii=False), "utf-8")
        FakeIMAP4_SSL.reset()
        FakeIMAP4_SSL.mailboxes = mailboxes
        http = http if http is not None else FakeHTTP()
        lines: list = []
        code = run(data_dir, lambda s, h, p: FakeIMAP4_SSL(h, p), lines.append, http)
        return code, lines, list(FakeIMAP4_SSL.instances), http

    def result_line(lines):
        return next((l for l in lines if l.startswith("RESULT ok ")), "")

    results = []

    def check(label: str, cond: bool):
        results.append(cond)
        print(f"{'PASS' if cond else 'FAIL'}  {label}")

    # HTTP CONNECT 隧道：CONNECT 行拼装 / 200 应答 / 非 200 抛错
    class _FakeSock:
        def __init__(self, status_line=b"HTTP/1.1 200 Connection established"):
            self.sent = []
            self.buf = status_line + b"\r\n\r\n"

        def sendall(self, b):
            self.sent.append(b)

        def recv(self, n):
            out, self.buf = self.buf[:n], self.buf[n:]
            return out

    fs = _FakeSock()
    raw = http_connect_tunnel(("127.0.0.1", 7897), "imap.gmail.com", 993, 10,
                              sock_factory=lambda addr, t: fs)
    check("隧道 CONNECT 拼装", fs.sent and fs.sent[0].startswith(b"CONNECT imap.gmail.com:993")
          and b"Host: imap.gmail.com:993" in fs.sent[0] and raw is fs)
    try:
        http_connect_tunnel(("127.0.0.1", 7897), "x.test", 993, 10,
                            sock_factory=lambda a, t: _FakeSock(b"HTTP/1.1 403 Forbidden"))
        check("隧道非200抛错", False)
    except OSError:
        check("隧道非200抛错", True)

    def msgset(pairs):
        # 4 元组 (uid,date,from,subject)，6 元组再加 (body, att=(文件名,字节))
        return [dict(zip(("uid", "date", "from", "subject", "body", "att"), p))
                for p in pairs]

    # ===== 原有场景：password 双账号 + 失败账号 =====
    d1 = tmp / "s1"
    d1.mkdir()
    cfg1 = {"dir": d1, "config": [
        {"name": "个人", "host": "imap.personal.test", "port": 993, "ssl": True,
         "user": "me@personal.test", "password": "secret-pass-1",
         "webmail": "https://mail.personal.test/"},
        {"name": "公司", "host": "imap.work.test", "port": 993, "ssl": True,
         "user": "me@work.test", "password": "secret-pass-2"},
        {"name": "坏账", "host": "imap.bad.test", "port": 993, "ssl": True,
         "user": "me@bad.test", "password": "secret-pass-3"},
    ]}
    mb1 = {
        "imap.personal.test": {"ok": True, "folders": {"INBOX": msgset([
            (1, ds(30), "张三 <z3@personal.test>", "一周前的旧邮件"),
            (2, ds(2), "张三 <z3@personal.test>", "周报提醒"),
            (3, ds(1), f"{enc_sender} <l4@personal.test>", enc_subject,
             "季度报表见附带 PDF，此为详情页正文。", ("报表.pdf", b"%PDF-fake-data")),
        ])}},
        "imap.work.test": {"ok": True, "folders": {"INBOX": msgset([
            (1, ds(3), "运维 <ops@work.test>", "Re: 服务器巡检"),
        ])}},
        "imap.bad.test": {"ok": False, "folders": {"INBOX": []}},
    }
    code1, lines1, inst1, http1 = run_once(cfg1, mb1)
    out1 = "\n".join(lines1)
    r1 = result_line(lines1)

    check("第一次运行退出码 0", code1 == 0)
    check("输出 RESULT ok", bool(r1))
    check("含两账号节【个人】/【公司】", "【个人】" in r1 and "【公司】" in r1)
    check("个人新增 2 封（30h 前旧邮件被 24h 窗口排除）", "【个人】新增 2 封" in r1)
    check("公司新增 1 封", "【公司】新增 1 封" in r1)
    check("RFC2047 主题已解码（会议纪要：第三季度）", "会议纪要：第三季度" in r1)
    check("RFC2047 发件人显示名已解码（王五）", "王五" in r1)
    check("主题行格式（时间 发件人 ─ 主题）", "周报提醒" in r1 and "─" in r1)
    check("坏账进入失败节但整体仍 ok", "失败：坏账" in r1)
    check("共 3 封", "共 3 封" in r1)
    check("密码未出现在任何输出", "secret-pass" not in out1)
    check("PROGRESS 逐账号输出", sum(1 for l in lines1 if l.startswith("PROGRESS ")) == 3)

    state = json.loads((d1 / "state.json").read_text("utf-8"))
    check("state.json 已写入", bool(state))
    check("个人|INBOX last_uid=3（全箱最大 UID，含未列出的旧邮件）",
          state.get("个人|INBOX", {}).get("last_uid") == 3)
    check("公司|INBOX last_uid=1", state.get("公司|INBOX", {}).get("last_uid") == 1)
    check("uidvalidity 已记录", state.get("个人|INBOX", {}).get("uidvalidity") == 1)

    # ===== HTML 报告：列表/详情页/附件落盘/网页版链接 =====
    dstr = now.strftime("%Y-%m-%d")
    rep = d1 / "reports" / f"{dstr}.html"
    rep_txt = rep.read_text("utf-8") if rep.exists() else ""
    check("HTML 报告生成", rep.exists() and 'class="row"' in rep_txt
          and "周报提醒" in rep_txt and "共 3 封" in r1)
    check("报告不含正文/密码", "secret-pass" not in rep_txt
          and "季度报表" not in rep_txt)   # 正文只进详情页，列表不带
    det2 = d1 / "reports" / detail_name(dstr, 2)   # 个人第 2 行=王五（带附件）
    det2_txt = det2.read_text("utf-8") if det2.exists() else ""
    check("详情页正文+附件链接", "季度报表" in det2_txt and "报表.pdf" in det2_txt
          and det2_txt.count('href="att/') == 1)
    check("详情页网页版登录链接", "mail.personal.test" in det2_txt)
    check("附件已落盘", any((d1 / "reports" / "att").glob("*报表*")))

    code2, lines2, _, _ = run_once(cfg1, mb1)
    r2 = result_line(lines2)
    check("第二次运行退出码 0", code2 == 0)
    check("二次运行不重复计数（共 0 封）", "共 0 封" in r2)
    check("两账号均无新邮件", "【个人】无新邮件" in r2 and "【公司】无新邮件" in r2)
    state2 = json.loads((d1 / "state.json").read_text("utf-8"))
    check("二次运行后水位不变（个人|INBOX last_uid 仍为 3）",
          state2.get("个人|INBOX", {}).get("last_uid") == 3)

    # ===== ⑩ 无 oauth2 字段账号与旧版行为一致（仍 login） =====
    check("⑩ password 账号走 login（1 次）", inst1[0].login_calls == 1)
    check("⑩ password 账号不触发 authenticate", not inst1[0].auth_log)

    # ===== ①② XOAUTH2：SASL 严格等值 + 令牌缓存 =====
    d2 = tmp / "s2"
    d2.mkdir()
    cfg2 = {"dir": d2, "config": {"accounts": [
        {"name": "谷歌", "host": "imap.gmail.test", "port": 993, "ssl": True,
         "auth": "xoauth2", "user": "me@gmail.test",
         "oauth2": {"provider": "gmail", "client_id": "cid-SECRET-CLIENT",
                    "client_secret": "cs-SECRET-2",
                    "refresh_token": "rt-SECRET-REFRESH-1"}},
    ]}}
    mb2 = {"imap.gmail.test": {"ok": True, "folders": {"INBOX": msgset([
        (1, ds(2), "Gmail 团队 <no-reply@gmail.test>", "安全提醒"),
    ])}}}
    http2 = FakeHTTP()
    code3, lines3, inst3, http3 = run_once(cfg2, mb2, http2)
    r3 = result_line(lines3)
    out3 = "\n".join(lines3)
    check("① xoauth2 运行退出码 0 且 RESULT ok", code3 == 0 and "【谷歌】新增 1 封" in r3)
    sasl_expected = b"user=me@gmail.test\x01auth=Bearer fake-at-token-XYZ\x01\x01"
    check("① SASL 字节串严格等于 user=…\\x01auth=Bearer <tok>\\x01\\x01",
          bool(inst3[0].auth_log) and inst3[0].auth_log[0] == ("XOAUTH2", sasl_expected))
    check("① authenticate 机制名为 XOAUTH2", inst3[0].auth_log[0][0] == "XOAUTH2")

    # Gmail host：详情页按 Message-ID 生成网页版深链（无需配置 webmail）
    det_g = d2 / "reports" / detail_name(now.strftime("%Y-%m-%d"), 1)
    check("① Gmail Message-ID 深链", det_g.exists()
          and "rfc822msgid%3A" in det_g.read_text("utf-8")
          and "mail.google.com" in det_g.read_text("utf-8"))

    # ② 令牌缓存：同目录两连跑，令牌端点仅 1 次 HTTP
    code4, lines4, _, http4 = run_once(cfg2, mb2, http3)
    check("② 两连跑假令牌端点仅 1 次 HTTP",
          http4.token_calls == 1 and result_line(lines4).startswith("RESULT ok"))

    # ③ expires_in=1s + sleep → 重新请求（先把已缓存令牌标成过期）
    http4.token_expires_in = 1
    st2 = json.loads((d2 / "state.json").read_text("utf-8"))
    st2["__token__谷歌"]["expires_at"] = time.time() - 1
    (d2 / "state.json").write_text(json.dumps(st2), "utf-8")
    time.sleep(1.1)
    code5, lines5, _, http5 = run_once(cfg2, mb2, http4)
    check("③ expires_in=1s 过期后重新请求令牌（第 2 次 HTTP）",
          http5.token_calls == 2 and result_line(lines5).startswith("RESULT ok"))

    # ④ 三类敏感串不出现（首跑全输出：令牌来自假端点）
    check("④ refresh_token 不在任何输出", "rt-SECRET-REFRESH-1" not in out3)
    check("④ client_secret 不在任何输出", "cs-SECRET-2" not in out3)
    check("④ access_token 不在任何输出", "fake-at-token-XYZ" not in out3)
    sent = [d for u, d in http5.calls if "/chat/completions" not in u]
    check("④ 令牌确实在 POST 请求体里（输出无、请求有）",
          any("rt-SECRET-REFRESH-1" in str(d) for d in sent))

    # ===== ⑤ 令牌端点 500 → 该账号失败，其余正常 =====
    d5 = tmp / "s5"
    d5.mkdir()
    cfg5 = {"dir": d5, "config": {"accounts": [
        {"name": "谷歌", "host": "imap.gmail.test", "port": 993, "ssl": True,
         "auth": "xoauth2", "user": "me@gmail.test",
         "oauth2": {"provider": "gmail", "client_id": "cid-x",
                    "refresh_token": "rt-x"}},
        {"name": "公司", "host": "imap.work.test", "port": 993, "ssl": True,
         "user": "me@work.test", "password": "pw"},
    ]}}
    http5b = FakeHTTP()
    http5b.token_status = 500
    code6, lines6, _, _ = run_once(cfg5, {**mb1, **mb2}, http5b)
    r6 = result_line(lines6)
    check("⑤ 令牌端点 500 → 谷歌进失败节（HTTP 500/gmail）",
          "谷歌" in r6 and "HTTP 500" in r6 and "gmail" in r6)
    check("⑤ 其余账号正常，整体 RESULT ok", code6 == 0 and "【公司】新增 1 封" in r6)

    # ===== ⑥ authenticate 拒绝（challenge）→ 失败节文案不含令牌本体 =====
    d6 = tmp / "s6"
    d6.mkdir()
    cfg6 = {"dir": d6, "config": {"accounts": [
        {"name": "谷歌", "host": "imap.gmail.test", "port": 993, "ssl": True,
         "auth": "xoauth2", "user": "me@gmail.test",
         "oauth2": {"provider": "gmail", "client_id": "cid-x",
                    "refresh_token": "rt-x"}},
        {"name": "公司", "host": "imap.work.test", "port": 993, "ssl": True,
         "user": "me@work.test", "password": "pw"},
    ]}}
    mb6 = {"imap.gmail.test": {"ok": True, "reject_xoauth2": True,
                               "folders": {"INBOX": []}},
           "imap.work.test": mb1["imap.work.test"]}
    code7, lines7, _, _ = run_once(cfg6, mb6)
    out7 = "\n".join(lines7)
    r7 = result_line(lines7)
    check("⑥ challenge 拒绝 → 失败节含 invalid_grant 原因",
          "invalid_grant" in r7 and "谷歌" in r7)
    check("⑥ 失败文案不含令牌本体", "fake-at-token-XYZ" not in out7)

    # ===== ⑦ 多文件夹：各自 SELECT、两个水位键 =====
    d7 = tmp / "s7"
    d7.mkdir()
    cfg7 = {"dir": d7, "config": {"accounts": [
        {"name": "多箱", "host": "imap.multi.test", "port": 993, "ssl": True,
         "user": "me@multi.test", "password": "pw",
         "folders": ["INBOX", "Archive"]},
    ]}}
    mb7 = {"imap.multi.test": {"ok": True, "folders": {
        "INBOX": msgset([(1, ds(2), "A <a@x.test>", "收件箱主题")]),
        "Archive": msgset([(1, ds(1), "B <b@x.test>", "归档主题")]),
    }}}
    code8, lines8, inst8, _ = run_once(cfg7, mb7)
    r8 = result_line(lines8)
    state8 = json.loads((d7 / "state.json").read_text("utf-8"))
    check("⑦ 两文件夹各自 SELECT（顺序 INBOX→Archive）",
          inst8[0].selects == ["INBOX", "Archive"])
    check("⑦ state 出现两个水位键", "多箱|INBOX" in state8 and "多箱|Archive" in state8)
    check("⑦ 每账号节内邮件行合并（共 2 封）", code8 == 0 and "共 2 封" in r8
          and "收件箱主题" in r8 and "归档主题" in r8)

    # ===== ⑧ 旧版无 | 键 state（last_uid=5）→ 迁移后首跑不重拉 =====
    d8 = tmp / "s8"
    d8.mkdir()
    (d8 / "state.json").write_text(json.dumps(
        {"旧账": {"uidvalidity": 1, "last_uid": 5}}), "utf-8")
    cfg8 = {"dir": d8, "config": [
        {"name": "旧账", "host": "imap.old.test", "port": 993, "ssl": True,
         "user": "me@old.test", "password": "pw"},
    ]}
    mb8 = {"imap.old.test": {"ok": True, "folders": {"INBOX": msgset(
        [(u, ds(30 + u), f"o{u} <o{u}@x.test>", f"旧邮件 {u}") for u in range(1, 6)])}}}
    code9, lines9, _, _ = run_once(cfg8, mb8)
    r9 = result_line(lines9)
    state9 = json.loads((d8 / "state.json").read_text("utf-8"))
    check("⑧ 旧键迁移为 旧账|INBOX 且无裸旧键",
          "旧账|INBOX" in state9 and "旧账" not in state9)
    check("⑧ 迁移后首跑不重拉（无新邮件）",
          code9 == 0 and "【旧账】无新邮件" in r9
          and state9.get("旧账|INBOX", {}).get("last_uid") == 5)

    # ===== ⑨ ai_summary：假 chat 端点恰 1 次且请求体含主题；500 → ⚠ =====
    env_backup = {k: os.environ.get(k) for k in
                  ("AI_API_KEY", "AI_API_BASE_URL", "AI_MODEL_NAME",
                   "ZENTRAY_PLUGIN_DATA_DIR")}
    try:
        os.environ.update(AI_API_KEY="sk-selftest-key",
                          AI_API_BASE_URL="http://fake.local/v1",
                          AI_MODEL_NAME="fake-model")
        d9 = tmp / "s9"
        d9.mkdir()
        cfg9 = {"dir": d9, "config": {"accounts": [
            {"name": "个人", "host": "imap.personal.test", "port": 993, "ssl": True,
             "user": "me@personal.test", "password": "pw"}],
            "ai_summary": True}}
        http9 = FakeHTTP()
        code10, lines10, _, http10 = run_once(cfg9, mb1, http9)
        r10 = result_line(lines10)
        check("⑨ AI：假 chat 端点恰 1 次调用", http10.chat_calls == 1)
        chat_body = next(json.loads(d.decode() if isinstance(d, bytes) else str(d))
                         for u, d in http10.calls if "/chat/completions" in u)
        check("⑨ 请求体含主题（且无凭证）",
              "周报提醒" in chat_body["messages"][1]["content"]
              and "sk-selftest-key" not in json.dumps(chat_body))
        check("⑨ RESULT ok 含 AI 摘要段", code10 == 0 and "AI 摘要：" in r10
              and "服务器巡检" in r10)

        http10.chat_status = 500
        d9b = tmp / "s9b"
        d9b.mkdir()
        code11, lines11, _, _ = run_once({"dir": d9b, "config": cfg9["config"]},
                                         mb1, http10)
        r11 = result_line(lines11)
        check("⑨ chat 端点 500 → RESULT ok 含 ⚠ AI 摘要失败",
              code11 == 0 and "⚠ AI 摘要失败" in r11)
    finally:
        for k, v in env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    print(f"\nselftest: {sum(results)}/{len(results)} 通过（数据目录 {tmp}）")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
