# scrape-gcp-certifications (Google Cloud 認定資格スクレイピングサービス)

このサービスは、Google Cloud 認定資格の公式サイトを Playwright (Chromium) を使用してスクレイピングし、最新の資格一覧（資格名、レベル、URL）を取得する Web API (Cloud Run Service) です。

BigQuery の Remote Function から呼び出されることを前提に設計・実装されています。

---

## 1. 役割と呼び出し仕様

*   **実行環境**: Cloud Run Service (Dockerfile ベース)
*   **用途**: BigQuery Remote Function から呼び出され、最新の認定資格マスタ情報を取得して Dataform アサーション等で検証するために利用します。
*   **インターフェース**: BigQuery Remote Function の呼び出し規約に従い、JSON 形式でリクエストを受理し、結果を JSON 形式で返します。

### リクエストフォーマット (POST)
BigQuery 側からバッチ単位でデータが送信されます（本機能では引数なしの呼び出しを想定しているため、内側の配列は空です）。

```json
{
  "calls": [
    []
  ]
}
```

### レスポンスフォーマット
各 `calls` に対応する要素数と同じ長さの `replies` を返します。中身はスクレイピング結果の認定資格情報の JSON 配列文字列になります。

```json
{
  "replies": [
    "[{\"title\": \"Associate Cloud Engineer\", \"level\": \"Associate\", \"url\": \"https://cloud.google.com/...\"}, ...]"
  ]
}
```

> [!NOTE]
> スクレイピングは Chromium を起動して行う重い処理であるため、リクエスト内の `calls` に複数行（バッチ）が含まれている場合でも、内部のスクレイピングは 1 回のみ実行し、その結果をすべての行に対する `replies` として再利用して返却します。

---

## 2. コンテナ設計 (Dockerfile)

Playwright (Chromium) をヘッドレスコンテナで安定して動作させるため、Playwright 公式の Python ランタイムイメージを使用しています。

*   **ベースイメージ**: `mcr.microsoft.com/playwright/python:v1.60.0-jammy`
    *   Chromium バイナリおよび Linux 用のシステム依存ライブラリがあらかじめインストールされています。
*   **パッケージ管理**: `uv` パッケージマネージャを用いて、システム Python に対して依存ライブラリをインストールします。
*   **Web サーバー**: `Uvicorn` を使用して FastAPI アプリケーションをポート `8080` で起動します。

---

## 3. ローカル開発とテスト

本プロジェクトは Python 3.14 (CPython 3.14.5) 環境に完全対応しています。

### ① パッケージのインストールと同期
`uv` を用いて、Python 3.14 環境で依存ライブラリをセットアップします。
```bash
uv sync --group dev --python 3.14
```

### ② 単体テストの実行
Playwright によるブラウザの動作をモック（Mock）した pytest による単体テストを同梱しています。
```bash
uv run pytest
```

### ③ コード品質管理ツールの実行
プロジェクト規定のフォーマッタ・静的解析ツールを以下のコマンドで実行できます。
```bash
# フォーマットチェック
uv run black --check .

# リンターチェック
uv run flake8 .

# 型チェック
uv run mypy .

# インポート順チェック
uv run isort --check-only --diff .

# 循環的複雑度チェック (C以上でエラー)
uv run radon cc . -e "test_*.py" -n C
```
