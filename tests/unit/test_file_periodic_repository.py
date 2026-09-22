# tests/unit/test_file_periodic_repository.py
from zentray.repositories.file_periodic_repository import FilePeriodicTemplateRepository
from zentray.core.models import PeriodicTemplate
import glob
import os


def _cleanup(repo):
    """清理主文件及 .bak/.corrupt 残留（.bak 残留会触发 load 自愈）。"""
    for p in glob.glob(str(repo.filepath) + "*"):
        os.remove(p)


def test_template_save_and_load():
    """验证周期模板的保存与加载功能"""
    repo = FilePeriodicTemplateRepository()
    template = PeriodicTemplate(
        base_title="每日站会",
        category="工作",
        periodicity="daily"
    )
    repo.save_all([template])
    loaded = repo.find_all()
    assert len(loaded) == 1
    assert loaded[0].base_title == "每日站会"
    assert loaded[0].periodicity == "daily"

    # 清理测试文件
    _cleanup(repo)


def test_load_empty_when_file_missing():
    """验证文件不存在（且无 .bak）时返回空列表"""
    repo = FilePeriodicTemplateRepository()
    _cleanup(repo)
    result = repo.find_all()
    assert result == []
    _cleanup(repo)
