# ZenTray 貢献ガイド

[简体中文](CONTRIBUTING.md) | [English](CONTRIBUTING_EN.md) | 日本語

ZenTray にご関心をお寄せいただきありがとうございます！本プロジェクトでは **feature → staging → master** の 3 層ブランチモデルを採用しています。

## ブランチモデル

| ブランチ | 役割 | 更新方法 |
|---------|------|---------|
| `master` | 安定版リリースライン（GitHub の既定ブランチ） | リリース時のみ staging からマージし、`vX.Y.Z` タグを付与 |
| `staging` | 結合テストライン | 機能ブランチをここにマージして検証 |
| `feature/*` | 機能開発ブランチ | **staging** から切り出し |
| `hotfix/*` | 緊急修正ブランチ | **master** から切り出し |

> 履歴に関する注記：かつては `main` をトランクとしていましたが、2026-08-25 に廃止しました。使用しないでください。

## 通常の開発フロー

1. staging から機能ブランチを切り出します：

   ```bash
   git switch -c feature/your-feature staging
   ```

2. 開発とコミット。コミットメッセージの形式：`feat: 新機能の説明` / `fix: 修正の説明`

3. 完成したら **staging** 向けに Pull Request を出す（またはメンテナーがマージ）。その後、staging 上で検証します。

4. リリース時には staging を **master** にマージしてタグを付けます。バージョン番号はセマンティックバージョニングに従います。リリース前に [docs/VERSIONING.md](docs/VERSIONING.md) に従って 3 か所のバージョン番号を同期してください（`zentray/config.py` / `pyproject.toml` / `installer/install_wizard.py`）。

## 緊急修正（ホットフィックス）

```bash
git switch -c hotfix/urgent-fix master
# 修正後は master と staging の両方にマージして戻す。どちらか一方だけでは不十分
```

ホットフィックスは、staging を経由せずに直接 `master` へ入る唯一の例外です。リリースとして扱う場合は、同様に [docs/VERSIONING.md](docs/VERSIONING.md) に従ってバージョン番号を同期し、タグを付けてください。

## 注意事項

- `master` への直接プッシュはしないでください
- 廃止された `main` ブランチは使用しないでください
