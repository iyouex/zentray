# zentray/repositories/file_periodic_repository.py
import json
import logging
from pathlib import Path
from typing import List

from zentray.config import PERIODIC_TEMPLATES_FILE
from zentray.core.file_io import load_json_list, save_json_list
from zentray.core.models import PeriodicTemplate
from zentray.core.repository import PeriodicTemplateRepository

logger = logging.getLogger(__name__)


def _templates_from_latest_backup(exports_dir: Path) -> List[dict] | None:
    """从 exports 下按时间最近的备份 zip 里取周期模板（加密包/损坏包/空包跳过）。"""
    if not exports_dir.is_dir():
        return None
    import pyzipper

    for zp in sorted(
        exports_dir.glob("zentray-*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        try:
            with pyzipper.AESZipFile(zp) as zf:
                if "periodic_templates.json" not in zf.namelist():
                    continue
                data = json.loads(zf.read("periodic_templates.json").decode("utf-8"))
        except Exception:
            continue
        if isinstance(data, list) and data:
            return data
    return None


class FilePeriodicTemplateRepository(PeriodicTemplateRepository):
    """基于 JSON 文件的周期任务模板存储实现"""

    def __init__(self, filepath: Path | None = None):
        self.filepath = Path(filepath) if filepath else PERIODIC_TEMPLATES_FILE
        # 主文件与 .bak 双失后只尝试一次备份自愈，避免 watcher 每分钟重扫 exports
        self._heal_attempted = False

    def find_all(self) -> List[PeriodicTemplate]:
        data = load_json_list(self.filepath)
        if not data and not self._heal_attempted and not self.filepath.exists():
            # load_json_list 已试过 .bak 仍无数据（双失）。文件存在但为空列表
            # 属于用户主动清空，不回填；只有彻底丢失才从最近备份自愈。
            self._heal_attempted = True
            healed = _templates_from_latest_backup(self.filepath.parent / "exports")
            if healed:
                save_json_list(self.filepath, healed)
                logger.warning(
                    "周期模板文件丢失，已从最近备份自愈 %d 条: %s",
                    len(healed),
                    self.filepath,
                )
                data = healed
        return [PeriodicTemplate.from_dict(d) for d in data]

    def save_all(self, templates: List[PeriodicTemplate]) -> None:
        save_json_list(self.filepath, [t.to_dict() for t in templates])
