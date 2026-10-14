# tests/unit/test_file_periodic_repository.py
from zentray.repositories.file_periodic_repository import FilePeriodicTemplateRepository
from zentray.core.models import PeriodicTemplate


def test_template_save_and_load(tmp_path):
    """验证周期模板的保存与加载功能（tmp_path 隔离——曾用真实 DATA_DIR，
    save/_cleanup 会覆盖并删掉用户正式模板与 .bak）"""
    repo = FilePeriodicTemplateRepository(tmp_path / "periodic_templates.json")
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


def test_load_empty_when_file_missing(tmp_path):
    """验证文件不存在（且无 .bak）时返回空列表"""
    repo = FilePeriodicTemplateRepository(tmp_path / "periodic_templates.json")
    result = repo.find_all()
    assert result == []
