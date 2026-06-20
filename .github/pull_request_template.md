## 概要

<!-- このプルリクエストで実装した内容、背景、解決した問題について簡潔に記述してください。 -->

## 変更内容
<!-- 具体的な変更点を箇条書きで記述してください。 -->
- 

## 関連Issue/リンク
- 

## 開発・デプロイ前のチェックリスト

開発ガイドラインおよびセキュリティ基準に基づき、マージ前に以下の項目を確認してください。

### 1. Python 開発 (functions 配下)
- [ ] ローカルテスト環境 (Python 3.14) で `uv run pytest` が全件パスすることを確認した
- [ ] コードが `black` で自動整形されていることを確認した (`uv run black --check .`)
- [ ] 静的解析 `flake8` でエラーがないことを確認した (`uv run flake8 .`)
- [ ] 静的型チェック `mypy` でエラーがないことを確認した (`uv run mypy .`)
- [ ] インポート順が `isort` で整理されていることを確認した (`uv run isort --check-only --diff .`)
- [ ] `radon` による循環的複雑度（Cyclomatic Complexity）チェックで C 以上のブロックが検出されないことを確認した
- [ ] `AGENTS.md` の指示通り、追加した依存関係パッケージのバージョンは `==` で厳密に固定されている
- [ ] Dockerfile が存在する場合、ベースイメージタグのバージョンと `pyproject.toml` 内のパッケージバージョン（例: playwright）が一致していることを確認した

### 2. データスキーマ (二重管理の整合性)
- [ ] スキーマ変更時、Dataform 定義（`definitions/sources/`）と Python 定義（`functions/import-skill-check/schemas/`）の**双方が同期更新**されていることを確認した

### 3. Dataform
- [ ] ローカル環境で Dataform のコンパイルが正常終了することを確認した (`npx @dataform/cli compile`)
- [ ] SQLXファイルの記述に文法エラーがないことを確認した

### 4. Terraform
- [ ] `terraform fmt` でフォーマット整形されている
- [ ] `terraform validate` で定義に構文エラーがない

### 5. セキュリティ & その他
- [ ] cSpell によるスペルチェックをパスしていることを確認した (`npx cspell "functions/**/*"`)
- [ ] サービスアカウントの秘密鍵 (JSON キー) を誤ってコードやリポジトリに含めていない
- [ ] WIF 連携用のシークレット名やパラメータ名が正しい
