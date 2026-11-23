#!/usr/bin/env python3
"""生成并发布更新清单 latest.json —— 三端安装包齐备、逐个校验之后，最后上传。

对齐 taomni 的 compose-update-manifest + finalize 约束：
- 清单是「可安装版本」的真相：客户端只认清单里的版本、大小与 SHA256；清单缺失时才回退到
  无哈希的旧探测路径。所以它必须最后发布，且只在一发布就完整。
- 任一平台缺包、大小对不上、deb 内嵌版本与 tag 不符 → 直接失败，不碰 Release。
- 默认只校验并打印清单；--output 写到文件；--upload 才上传（发布流程的最后一步）。

用法（需要已登录的 gh；直连超时就带 HTTPS_PROXY）：
  python scripts/compose_update_manifest.py v0.7.25
  python scripts/compose_update_manifest.py v0.7.25 --output dist/releases/latest.json
  python scripts/compose_update_manifest.py v0.7.25 --upload

本脚本刻意不 import zentray：CI 里用系统 Python 也能跑。平台表与客户端
（zentray/services/updater.py 的 PLATFORMS）的一致性由 tests/unit/test_update_manifest_script.py 保证。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = "iyouex/zentray"
DOWNLOAD_BASE = f"https://github.com/{REPO}/releases/download"
MANIFEST_NAME = "latest.json"
NOTES_LIMIT = 4000

TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# latest.json 的平台键 → Release 资产文件名后缀（必须与客户端 PLATFORMS 一致）
PLATFORMS = {
    "linux-amd64": "_amd64.deb",
    "windows-x64": "_windows_x64.zip",
    "macos-arm64": "_macos_arm64.zip",
}


class ManifestError(RuntimeError):
    """清单不能发布：带着原因终止，不对 Release 做任何改动。"""


def asset_names(version: str) -> dict:
    return {key: f"zentray_{version}{suffix}" for key, suffix in PLATFORMS.items()}


def compose_manifest(tag: str, notes: str, published_at: str, digests: dict) -> dict:
    """digests: {平台键: {"size": int, "sha256": str}}，三端缺一不可。"""
    matched = TAG_RE.match(tag or "")
    if not matched:
        raise ManifestError(f"非法 tag：{tag!r}（应形如 v0.7.25）")
    version = matched.group(1)
    missing = [key for key in PLATFORMS if key not in digests]
    if missing:
        raise ManifestError(f"缺少平台安装包：{'、'.join(missing)}（先传齐再生成清单）")
    platforms = {}
    for key, name in asset_names(version).items():  # 固定顺序，产物可复现
        size, sha256 = int(digests[key]["size"]), str(digests[key]["sha256"]).lower()
        if size <= 0 or not SHA256_RE.match(sha256):
            raise ManifestError(f"{key} 的大小或哈希不合法（size={size}）")
        platforms[key] = {
            "url": f"{DOWNLOAD_BASE}/{tag}/{name}", "size": size, "sha256": sha256}
    return {
        "version": version,
        "pub_date": published_at,
        "notes": (notes or "")[:NOTES_LIMIT],
        "platforms": platforms,
    }


def validate_manifest(manifest) -> list:
    """独立于生成逻辑的复核（CI / 人工排查都能用）。返回问题列表，空 = 合法。"""
    if not isinstance(manifest, dict):
        return ["清单不是 JSON 对象"]
    errors = []
    version = str(manifest.get("version") or "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append(f"版本号不合法：{version!r}")
        return errors
    platforms = manifest.get("platforms")
    for key, name in asset_names(version).items():
        entry = platforms.get(key) if isinstance(platforms, dict) else None
        if not isinstance(entry, dict):
            errors.append(f"缺少 {key} 条目")
            continue
        if entry.get("url") != f"{DOWNLOAD_BASE}/v{version}/{name}":
            errors.append(f"{key} 的下载地址不符合确定性规则")
        if not SHA256_RE.match(str(entry.get("sha256") or "")):
            errors.append(f"{key} 的 sha256 不合法")
        if not isinstance(entry.get("size"), int) or entry["size"] <= 0:
            errors.append(f"{key} 的大小不合法")
    return errors


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def deb_version(path: Path) -> str | None:
    """读 deb 的 Debian Version 字段；没有 dpkg-deb（如 macOS）时返回 None。"""
    if shutil.which("dpkg-deb") is None:
        return None
    completed = subprocess.run(["dpkg-deb", "-f", str(path), "Version"],
                               capture_output=True, text=True)
    return completed.stdout.strip() if completed.returncode == 0 else None


def gh(*args: str) -> str:
    try:
        completed = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    except FileNotFoundError:
        raise ManifestError("需要 gh CLI（并已 gh auth login）") from None
    return completed.stdout


def gh_json(*args: str) -> dict:
    return json.loads(gh(*args))


def build(tag: str, workdir: Path) -> tuple:
    """核对 Release 上的三端资产并算出清单。返回 (manifest, 人读的核对记录)。"""
    matched = TAG_RE.match(tag or "")
    if not matched:
        raise ManifestError(f"非法 tag：{tag!r}（应形如 v0.7.25）")
    version = matched.group(1)
    try:
        release = gh_json("release", "view", tag, "--json", "assets,body,publishedAt,isDraft")
    except subprocess.CalledProcessError as e:
        raise ManifestError(f"读取 Release {tag} 失败：{e.stderr.strip()}") from None
    on_release = {a.get("name"): a for a in release.get("assets") or []}
    digests, log = {}, []
    for key, name in asset_names(version).items():
        asset = on_release.get(name)
        if not asset:
            raise ManifestError(f"{tag} 缺少 {name}（{key}）——先传齐三端安装包")
        gh("release", "download", tag, "--pattern", name, "--dir", str(workdir))
        local = workdir / name
        size = local.stat().st_size
        recorded = int(asset.get("size") or 0)
        if recorded and size != recorded:
            raise ManifestError(f"{name} 下载后 {size} 字节，与 Release 记录的 {recorded} 不符")
        sha256 = sha256_file(local)
        if name.endswith(".deb"):
            embedded = deb_version(local)
            if embedded is None:
                log.append(f"{name}: 本机没有 dpkg-deb，跳过内嵌版本核对")
            elif embedded != version:
                # 未升版本号的分支构建 --clobber 覆盖了正式资产时会走到这里
                raise ManifestError(
                    f"{name} 内嵌的 Debian 版本是 {embedded}，与 tag {tag} 不符")
        digests[key] = {"size": size, "sha256": sha256}
        log.append(f"{key}: {name}  {size} 字节  sha256 {sha256[:16]}…")
    if release.get("isDraft"):
        log.append("注意：该 Release 仍是草稿")
    published = release.get("publishedAt") or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    manifest = compose_manifest(tag, release.get("body") or "", published, digests)
    problems = validate_manifest(manifest)
    if problems:
        raise ManifestError("生成的清单未通过复核：" + "；".join(problems))
    return manifest, log


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成并发布更新清单 latest.json")
    parser.add_argument("tag", help="release tag，如 v0.7.25")
    parser.add_argument("--output", help="把清单写到该路径（不上传）")
    parser.add_argument("--upload", action="store_true",
                        help="校验通过后上传 latest.json（发布流程的最后一步）")
    args = parser.parse_args(argv)
    if args.upload and args.output:
        parser.error("--upload 与 --output 只能选一个")
    workdir = Path(tempfile.mkdtemp(prefix="zentray-manifest-"))
    try:
        manifest, log = build(args.tag, workdir)
    except (ManifestError, subprocess.CalledProcessError) as e:
        print(f"✗ 未生成清单：{e}", file=sys.stderr)
        return 1
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    for line in log:
        print(f"· {line}")
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"✓ 清单已写入 {args.output}")
    elif args.upload:
        target = workdir / MANIFEST_NAME
        target.write_text(text, encoding="utf-8")
        gh("release", "upload", args.tag, str(target), "--clobber")
        print(f"✓ latest.json 已上传到 {args.tag}（客户端下次检查即走清单路径）")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
