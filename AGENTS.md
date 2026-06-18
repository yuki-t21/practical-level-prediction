# 開発エージェント向け指示書 (AGENTS.md)

本リポジトリ (`practical-level-prediction`) の変更・開発を行うエージェントは、本ファイルおよび各サブディレクトリの `AGENTS.md` に記載されたプラクティスを**すべて**遵守してください。

---

## 1. リポジトリ全体に適用される最重要ルール

### ① Google Cloud プロジェクト ID のハードコード禁止

Google Cloud のプロジェクト ID（文字列）を、ソースコード・設定ファイル・ドキュメントのいずれかにリテラル値として直接記述することは**絶対に禁止**です。

| レイヤー | 正しい参照方法 |
| :--- | :--- |
| **Terraform** | `var.project_id` 変数経由で参照。プロジェクト番号は `data.google_project.project.number` で動的取得 |
| **Dataform (SQLX)** | `dataform.projectConfig.defaultDatabase` または `ref()` 経由で参照 |
| **Python (Cloud Run Functions)** | `os.environ.get("PROJECT_ID")` で環境変数から取得 |
| **ドキュメント (README 等)** | `<your-project-id>` や `YOUR_PROJECT_ID` などのプレースホルダーを使用 |

### ② 個人情報・機密情報のコミット禁止

以下の情報をリポジトリにコミットすることは**禁止**です。

- 氏名・メールアドレス・社員 ID などの個人識別情報
- サービスアカウントキー (JSON ファイル)
- 認証情報・シークレット・パスワード
- Dataform 認証情報 (`.df-credentials.json`)

これらのファイルは `.gitignore` によってバージョン管理から除外されています。新たに機密ファイルが生じた場合は、必ず `.gitignore` に追記してください。

### ③ ドキュメントへの絶対パスの記載禁止

`README.md` などのドキュメントには、ローカル環境に依存する**絶対パス**（例: `/Users/username/...`）を記載しないでください。ポータビリティを確保するため、リポジトリルートからの**相対パス**を使用してください。

### ④ Git コミットにおける個人情報の漏洩防止

リポジトリのパブリック公開に備え、Git コミットの Author および Committer 情報（名前・メールアドレス）に、本名やローカルPC環境依存のドメインを含むアドレス（例: `username@your-macbook.local`）が登録されないようにしてください。

開発やコード生成を行う前に、必ずリポジトリローカルで以下の設定を行い、個人の識別情報がログに混入するのを防いでください。
* **通常の開発者/アカウント**: GitHub の `no-reply` アドレス等を使用
  ```bash
  git config --local user.name "<your-github-username>"
  git config --local user.email "<your-id>+<your-github-username>@users.noreply.github.com"
  ```
* **AI エージェント等による自動コミット**: 以下の汎用エイリアスを使用
  ```bash
  git config --local user.name "developer"
  git config --local user.email "noreply@example.com"
  ```

---


## 2. サブディレクトリの AGENTS.md への委譲

各コンポーネントの詳細な開発ルールは、それぞれのサブディレクトリに配置された `AGENTS.md` に記載されています。対象のディレクトリを変更・開発する際は、**必ず対応する `AGENTS.md` を参照・遵守**してください。

| ディレクトリ | AGENTS.md | 主要なルール |
| :--- | :--- | :--- |
| `definitions/` | [definitions/AGENTS.md](definitions/AGENTS.md) | Dataform Core 3.0 準拠、SQL スタイルガイド、アサーション・ユニットテストの義務化 |

| `functions/` | [functions/AGENTS.md](functions/AGENTS.md) | `uv` によるパッケージ管理、バージョン厳密固定 (`==`)、pytest の義務化 |
| `terraform/` | [terraform/AGENTS.md](terraform/AGENTS.md) | プロジェクト ID のハードコード禁止、最小権限の原則、WIF の活用 |

---

## 3. スキーマの二重管理ルール

`raw_data.skill_check_results` および `raw_data.service_master` の 2 テーブルのスキーマ定義は、以下の 2 箇所で**意図的に**二重管理されています。
どちらか一方を変更した場合は、**必ずもう一方も同時に更新**してください。

1. **Dataform 定義**: `definitions/sources/` 配下の `.sqlx` ファイル
2. **Python インポーター定義**: `functions/import-skill-check/schemas/` 配下の JSON ファイル

---

## 4. コード品質管理ツール

本リポジトリでは以下のツールを導入しています。コミット・デプロイ前に各ツールが正常通過することを確認してください。

| ツール | 対象 | コマンド |
| :--- | :--- | :--- |
| `black` | Python (`functions/`) | `uv run black --check .` |
| `flake8` | Python (`functions/`) | `uv run flake8 .` |
| `mypy` | Python (`functions/`) | `uv run mypy .` |
| `isort` | Python (`functions/`) | `uv run isort --check-only --diff .` |
| `radon` | Python (`functions/`) | `uv run radon cc . -e "test_*.py" -n C` |
| `pytest` | Python (`functions/`) | `uv run pytest` |
| `SQLFluff` | SQLX (`definitions/`) | `sqlfluff lint definitions/` |
| `npx @dataform/cli compile` | Dataform | `npx @dataform/cli compile` |
| `terraform fmt` | Terraform | `terraform fmt -check` |
| `terraform validate` | Terraform | `terraform validate` |
| `cSpell` | 全体 (`functions/`) | `npx cspell "functions/**/*"` |

> [!NOTE]
> これらのチェックは GitHub Actions (`deploy.yaml`) の `validate` ジョブで自動実行されます。PR 作成前にローカルで確認することを推奨します。

---

## 5. Pull Request のルール

PR を作成する際は、`.github/pull_request_template.md` のテンプレートに従い、すべてのチェック項目を確認してください。

テンプレートに含まれる確認項目:

1. **Python 開発**: pytest パス、black/flake8 適合、mypy 型チェック適合、isort/radon 適合、パッケージバージョン固定
2. **データスキーマ**: Dataform 定義と Python 定義の双方が同期更新されているか
3. **Dataform**: コンパイル正常終了、SQLX 文法エラーなし
4. **Terraform**: `terraform fmt` / `terraform validate` 適合
5. **セキュリティ**: cSpell パス、秘密鍵の混入なし、WIF シークレット名の正確性

---

## 6. ブランチ戦略と CI/CD

- **`main` ブランチ**: 本番デプロイ対象。直接プッシュは禁止。必ず PR 経由でマージしてください。
- **`develop` ブランチ**: 開発用。PR の Lint・テストジョブが実行されます。
- **`main` への Push**: GitHub Actions の `deploy` ジョブが実行され、`terraform apply` によって GCP リソースが自動デプロイされます。

---

## 7. `.gitignore` の管理

以下のファイル・ディレクトリはバージョン管理から除外されています。新たに機密ファイルや生成物が生じた場合は、必ず `.gitignore` に追記してください。

| 除外対象 | 理由 |
| :--- | :--- |
| `bin/` | ビルド成果物 |
| `terraform/.terraform/` | Terraform プロバイダーキャッシュ |
| `terraform/terraform.tfstate*` | 状態ファイル（機密情報を含む） |
| `terraform/files/` | 関数ソース ZIP（生成物） |
| `.venv/`, `__pycache__/`, `*.pyc` | Python 仮想環境・キャッシュ |
| `*.zip` | 圧縮成果物 |
| `.df-credentials.json` | Dataform 認証情報（機密） |
| `.DS_Store` | macOS システムファイル |
