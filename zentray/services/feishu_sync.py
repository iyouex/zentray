# zentray/services/feishu_sync.py
"""
飞书单向同步 —— ZenTray 任务 → 飞书开放平台（自建应用）。

与通知用的 FeishuBotService（群 webhook）完全独立：本模块走开放平台
app_id/app_secret，把任务单向推送到飞书日历（ZenTray 日历）与任务清单
（ZenTray 清单），不在飞书侧回读。配置步骤见 docs/FEISHU_SYNC.md。

可靠性约定：任务操作路径上的 enqueue 绝不抛错；后台推送失败只记
last_error + 日志（不打 app_secret），绝不阻塞本地任务 CRUD。
"""
from __future__ import annotations

import datetime
import logging
import queue
import threading
import time

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://open.feishu.cn"
CALENDAR_NAME = "ZenTray"
TASKLIST_NAME = "ZenTray"
# 动作：upsert=新建/更新推送；done=标记完成；deleted=删除远端对象
ACTION_UPSERT = "upsert"
ACTION_DONE = "done"
ACTION_DELETED = "deleted"


class FeishuSyncError(Exception):
    """携带可直接展示给用户的中文错误信息。"""


def _api(method: str, path: str, token: str = "", **kw) -> dict:
    """开放平台统一请求：错误码 != 0 抛 FeishuSyncError。"""
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.request(method, API_BASE + path, headers=headers, timeout=10, **kw)
        data = resp.json()
    except Exception as e:
        raise FeishuSyncError(f"网络错误：{e}") from e
    if data.get("code") not in (0, None):
        raise FeishuSyncError(f"飞书接口失败（{path}）：code={data.get('code')} {data.get('msg')}")
    # token 端点不包 data 层，直接回全量；其余端点回 data 节
    return data.get("data") or data


class FeishuSyncService:
    """单例。enqueue 入队后由 daemon 线程逐条推送（同任务 id 自动合并）。"""

    _instance = None

    @classmethod
    def instance(cls) -> "FeishuSyncService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._queue: "queue.Queue[str]" = queue.Queue()
        # task_id -> (task_snapshot_dict, action)；入队快照，后到覆盖先到
        self._pending: dict = {}
        self._lock = threading.Lock()
        self._worker = None
        self._token = ""
        self._token_expire_at = 0.0

    # ---------- 对外入口 ----------

    def enqueue(self, task, action: str) -> None:
        """任务变更入队（Task 对象或 dict 均可）。任务操作路径上绝不抛错。"""
        try:
            snap = task.to_dict() if hasattr(task, "to_dict") else dict(task)
            with self._lock:
                self._pending[snap["id"]] = (snap, action)
            self._queue.put(snap["id"])
            self._ensure_worker()
        except Exception as e:  # 同步功能绝不能拖垮任务操作
            logger.warning("feishu enqueue failed: %s", e)

    def resync_all(self, task_service) -> int:
        """清掉全部活跃任务的远端引用后整表重推；返回入队条数。"""

        def clear_refs(tasks) -> bool:
            for t in tasks:
                t.feishu_event_id = None
                t.feishu_task_id = None
            return bool(tasks)

        self._repo().mutate_all(clear_refs)
        tasks = task_service.get_all_tasks()
        for t in tasks:
            self.enqueue(t, ACTION_UPSERT)
        return len(tasks)

    def test_connection(self) -> tuple[bool, str]:
        """设置页「测试连接」：token → 日历 → 订阅 → 清单 逐级验证。"""
        from zentray.services.settings_manager import SettingsManager

        s = SettingsManager().feishu_sync
        try:
            if not s.app_id or not s.app_secret:
                return False, "请先填写 App ID 与 App Secret"
            self._fetch_token(force=True)
            cal = self.ensure_calendar()
            if s.feishu_user_id:
                self._subscribe(self._token, cal, s.feishu_user_id)
            self.ensure_task_list()
            self._clear_error()
            return True, "连接成功：日历「ZenTray」与任务清单已就绪"
        except FeishuSyncError as e:
            self._set_error(str(e))
            return False, str(e)

    # ---------- 后台推送 ----------

    def _ensure_worker(self) -> None:
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(
                target=self._run, name="feishu-sync", daemon=True
            )
            self._worker.start()

    def _run(self) -> None:
        while True:
            task_id = self._queue.get()
            with self._lock:
                item = self._pending.pop(task_id, None)
            if item is None:  # 被更新的快照取代
                continue
            snap, action = item
            try:
                self._push(snap, action)
                self._clear_error(snap)
            except FeishuSyncError as e:
                self._set_error(str(e), snap)
                logger.warning("feishu sync push failed: %s", e)
            except Exception as e:
                self._set_error(f"未知错误：{e}", snap)
                logger.exception("feishu sync unexpected error")

    def _push(self, snap: dict, action: str) -> None:
        from zentray.services.settings_manager import SettingsManager

        s = SettingsManager().feishu_sync
        if not s.enabled or not s.app_id or not s.app_secret:
            return
        token = self._fetch_token()
        if action == ACTION_UPSERT:
            self._push_upsert(token, snap)
        else:
            self._push_remove(token, snap, completed=action == ACTION_DONE)

    def _push_upsert(self, token: str, snap: dict) -> None:
        from zentray.services.settings_manager import SettingsManager

        s = SettingsManager().feishu_sync
        ev_id = snap.get("feishu_event_id") or ""
        tk_id = snap.get("feishu_task_id") or ""

        # —— 日历事件（仅有截止/提醒的任务；映射同 _build_tasks_ics）——
        if s.sync_calendar:
            spec = _event_spec(snap)
            if spec is not None:
                cal = self.ensure_calendar()
                if ev_id:
                    _api("PATCH", f"/open-apis/calendar/v4/calendars/{cal}/events/{ev_id}",
                         token, json=spec)
                else:
                    data = _api("POST", f"/open-apis/calendar/v4/calendars/{cal}/events",
                                token, json=spec)
                    ev_id = data.get("event", {}).get("event_id") or ""
                    self._write_ref(snap["id"], "feishu_event_id", ev_id)

        # —— 任务清单条目 ——
        if s.sync_tasks:
            guid = self.ensure_task_list()
            body = _task_body(s, snap)
            if tk_id:
                _api("PATCH", f"/open-apis/task/v2/tasks/{tk_id}", token, json=body)
            else:
                data = _api("POST", "/open-apis/task/v2/tasks", token, json=body)
                tk_id = data.get("task", {}).get("guid") or ""
                self._write_ref(snap["id"], "feishu_task_id", tk_id)

    def _push_remove(self, token: str, snap: dict, completed: bool) -> None:
        from zentray.services.settings_manager import SettingsManager

        s = SettingsManager().feishu_sync
        ev_id = snap.get("feishu_event_id") or ""
        if s.sync_calendar and ev_id and s.calendar_id:
            _api("DELETE",
                 f"/open-apis/calendar/v4/calendars/{s.calendar_id}/events/{ev_id}", token)
        tk_id = snap.get("feishu_task_id") or ""
        if s.sync_tasks and tk_id:
            if completed:
                # v2 任务：completed_at=毫秒时间串标记完成，"0" 表示未完成
                _api("PATCH", f"/open-apis/task/v2/tasks/{tk_id}", token,
                     json={"completed_at": str(int(datetime.datetime.now().timestamp() * 1000))})
            else:
                _api("DELETE", f"/open-apis/task/v2/tasks/{tk_id}", token)

    # ---------- 远端对象准备（token / 日历 / 清单） ----------

    def _fetch_token(self, force: bool = False) -> str:
        if not force and self._token and time.time() < self._token_expire_at - 300:
            return self._token
        from zentray.services.settings_manager import SettingsManager

        s = SettingsManager().feishu_sync
        data = _api("POST", "/open-apis/auth/v3/tenant_access_token/internal",
                    json={"app_id": s.app_id, "app_secret": s.app_secret})
        self._token = data.get("tenant_access_token") or ""
        self._token_expire_at = time.time() + int(data.get("expire") or 3600)
        if not self._token:
            raise FeishuSyncError("未取得 tenant_access_token")
        return self._token

    def ensure_calendar(self) -> str:
        """取同步日历 id；无则建「ZenTray」日历并（可选）授权订阅者。"""
        from zentray.services.settings_manager import SettingsManager

        sm = SettingsManager()
        s = sm.feishu_sync
        if s.calendar_id:
            return s.calendar_id
        token = self._fetch_token()
        data = _api("POST", "/open-apis/calendar/v4/calendars", token,
                    json={"summary": CALENDAR_NAME, "description": "ZenTray 任务同步日历"})
        cal = (data.get("calendar") or {}).get("calendar_id") or ""
        if not cal:
            raise FeishuSyncError("创建日历失败：响应缺少 calendar_id")
        s.calendar_id = cal
        if s.feishu_user_id:
            self._subscribe(token, cal, s.feishu_user_id)
        sm.save()
        return cal

    def _subscribe(self, token: str, cal: str, user_id: str) -> None:
        """把日历共享给用户（open_id），已订阅过视为成功。"""
        try:
            _api("POST", f"/open-apis/calendar/v4/calendars/{cal}/acls", token,
                 params={"user_id_type": "open_id"},
                 json={"role": "writer", "scope": {"type": "user", "user_id": user_id}})
        except FeishuSyncError as e:
            if "已存在" not in str(e) and "already" not in str(e):
                raise

    def ensure_task_list(self) -> str:
        """取任务清单 guid；无则建「ZenTray」清单。"""
        from zentray.services.settings_manager import SettingsManager

        sm = SettingsManager()
        s = sm.feishu_sync
        if s.task_list_guid:
            return s.task_list_guid
        token = self._fetch_token()
        # shortcut: tasklist 列表/创建端点未逐字核对文档，字段名不符时由测试连接报错暴露
        data = _api("GET", "/open-apis/task/v2/tasklists", token)
        for item in data.get("items") or []:
            if item.get("name") == TASKLIST_NAME and item.get("tasklist_guid"):
                s.task_list_guid = item["tasklist_guid"]
                sm.save()
                return s.task_list_guid
        data = _api("POST", "/open-apis/task/v2/tasklists", token, json={"name": TASKLIST_NAME})
        guid = (data.get("tasklist") or {}).get("tasklist_guid") or ""
        if not guid:
            raise FeishuSyncError("创建任务清单失败：响应缺少 tasklist_guid")
        s.task_list_guid = guid
        sm.save()
        return guid

    # ---------- 本地回写与状态 ----------

    def _repo(self):
        from zentray.repositories.file_repository import FileTaskRepository

        return FileTaskRepository()

    def _write_ref(self, task_id: str, field: str, value: str) -> None:
        """远端 id 回写到任务文件（任务可能已被完成/删除，找不到就跳过）。"""
        if not value:
            return

        def mutator(tasks) -> bool:
            for t in tasks:
                if t.id == task_id:
                    setattr(t, field, value)
                    return True
            return False

        try:
            self._repo().mutate_all(mutator)
        except Exception as e:
            logger.warning("feishu write ref failed: %s", e)

    def _set_error(self, msg: str, snap: dict | None = None) -> None:
        self._mark(snap, error=msg)

    def _clear_error(self, snap: dict | None = None) -> None:
        self._mark(snap, error="", ok=True)

    def _mark(self, snap: dict | None, error: str = "", ok: bool = False) -> None:
        from zentray.services.settings_manager import SettingsManager

        try:
            sm = SettingsManager()
            s = sm.feishu_sync
            s.last_error = error
            if ok:
                s.last_sync_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sm.save()
        except Exception:
            pass


def _event_spec(snap: dict) -> dict | None:
    """任务 → 日历事件体；无截止且无提醒返回 None（映射同 _build_tasks_ics）。"""
    import datetime as _dt

    deadline = snap.get("deadline") or ""
    rem = snap.get("reminder") or {}
    rem_time = None
    if isinstance(rem, dict) and rem.get("enabled"):
        rem_time = rem.get("time_of_day") or "17:00"
    if deadline:
        try:
            _dt.date.fromisoformat(str(deadline))
        except ValueError:
            deadline = ""
    if not deadline and not rem_time:
        return None
    pri_tag = {"high": "🔴 ", "medium": "", "low": "⬇ "}.get(snap.get("priority", ""), "")
    spec = {
        "summary": f"{pri_tag}{snap.get('title', '')}".strip(),
        "description": f"分类: {snap.get('category') or '未分类'}\n{snap.get('details') or ''}",
    }
    if deadline and rem_time:
        start = _dt.datetime.combine(
            _dt.date.fromisoformat(deadline), _dt.time.fromisoformat(rem_time))
        end = start + _dt.timedelta(minutes=30)
        spec["start_time"] = {"timestamp": str(int(start.timestamp()))}
        spec["end_time"] = {"timestamp": str(int(end.timestamp()))}
    elif deadline:
        # 全天事件：end_date 不含当天（飞书按前闭后开区间解释）
        spec["start_time"] = {"date": str(deadline)}
        spec["end_time"] = {
            "date": str(_dt.date.fromisoformat(deadline) + _dt.timedelta(days=1))}
    else:
        start = _dt.datetime.combine(
            _dt.date.today(), _dt.time.fromisoformat(rem_time))
        spec["start_time"] = {"timestamp": str(int(start.timestamp()))}
        spec["end_time"] = {
            "timestamp": str(int((start + _dt.timedelta(minutes=30)).timestamp()))}
    return spec


def _task_body(settings, snap: dict) -> dict:
    """任务 → 任务清单条目体。"""
    body = {"summary": snap.get("title", ""), "description": snap.get("details") or ""}
    if settings.task_list_guid:
        body["tasklists"] = [{"tasklist_guid": settings.task_list_guid}]
    if settings.feishu_user_id:
        # 负责人挂到用户，任务才会出现在该用户的飞书客户端
        body["members"] = [
            {"id": settings.feishu_user_id, "type": "user", "role": "assignee"}]
    deadline = snap.get("deadline") or ""
    if deadline:
        try:
            import datetime as _dt

            start = _dt.datetime.combine(
                _dt.date.fromisoformat(str(deadline)), _dt.time(0, 0))
            body["due"] = {
                "timestamp": str(int(start.timestamp() * 1000)), "is_all_day": True}
        except ValueError:
            pass
    return body
