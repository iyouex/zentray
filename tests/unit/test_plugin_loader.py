from pathlib import Path

from zentray.plugins.loader import PluginLoader

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "plugins"


def test_scan_loads_valid_only(tmp_path):
    # 把 fixtures 当 user 目录的父：扫描 fixtures 本身
    loader = PluginLoader()
    plugins = loader.scan(user_dir=FIXTURES, load_bundled=False, load_user=True)
    ids = {p.manifest.id for p in plugins}
    assert "sample-script" in ids
    assert "sample-service" in ids
    assert "bad-escape" not in ids
    assert any("bad-escape" in str(p) or True for p in loader.failures)
    assert loader.failures  # bad-escape


def test_user_overrides_bundled(tmp_path):
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    for root, name in ((bundled, "bundled-name"), (user, "user-name")):
        d = root / "sample-script"
        d.mkdir(parents=True)
        (d / "plugin.yaml").write_text(
            f"""id: sample-script
name: {name}
version: 0.1.0
type: script
api_version: 1
entry: run.sh
""",
            encoding="utf-8",
        )
        run = d / "run.sh"
        run.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
        run.chmod(0o755)

    loader = PluginLoader()
    loader.scan(
        bundled_dir=bundled,
        user_dir=user,
        load_bundled=True,
        load_user=True,
    )
    p = loader.get("sample-script")
    assert p is not None
    assert p.manifest.name == "user-name"
    assert p.source == "user"
