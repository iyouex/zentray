# tests/unit/test_file_io_selfheal.py
"""load_json_list 自愈：主文件丢失/损坏时从 save 留底的 .bak 恢复。"""
import json

from zentray.core.file_io import load_json_list, save_json_list


def test_missing_file_restored_from_bak(tmp_path):
    f = tmp_path / "data.json"
    save_json_list(f, [{"id": "a"}])
    f.unlink()  # 模拟文件丢失
    assert load_json_list(f) == [{"id": "a"}]
    assert f.exists()  # 主文件已重建


def test_bak_is_last_good(tmp_path):
    f = tmp_path / "data.json"
    save_json_list(f, [{"id": "a"}])
    save_json_list(f, [{"id": "a"}, {"id": "b"}])
    f.unlink()
    assert load_json_list(f) == [{"id": "a"}, {"id": "b"}]  # 第二次 save 的内容


def test_corrupt_file_restored_from_bak(tmp_path):
    f = tmp_path / "data.json"
    save_json_list(f, [{"id": "a"}])
    f.write_text("{broken", encoding="utf-8")
    assert load_json_list(f) == [{"id": "a"}]
    # 损坏原件另存，.bak 未被覆盖
    leftovers = [p.name for p in tmp_path.iterdir() if ".corrupt-" in p.name]
    assert leftovers, "损坏件应另存 .corrupt-<ts>"


def test_no_bak_returns_empty(tmp_path):
    f = tmp_path / "data.json"
    assert load_json_list(f) == []
    f.write_text(json.dumps([{"id": "x"}]), encoding="utf-8")
    f.unlink()
    assert load_json_list(f) == []
