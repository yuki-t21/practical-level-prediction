#!/bin/bash
set -e

# リポジトリルートを取得
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
TERRAFORM_CMD="$REPO_ROOT/bin/terraform"

echo "=== Starting Project Quality Validation ==="

# 1. Terraform Verification
echo "--> Verifying Terraform configuration..."
cd "$REPO_ROOT/terraform"
if [ -f "$TERRAFORM_CMD" ]; then
  echo "Using bundled terraform at bin/terraform"
  # 同梱されている terraform バイナリを使用
  chmod +x "$TERRAFORM_CMD"
  "$TERRAFORM_CMD" init -backend=false
  "$TERRAFORM_CMD" fmt -check
  "$TERRAFORM_CMD" validate
else
  # グローバルな terraform を試行
  if command -v terraform &> /dev/null; then
    echo "Using system terraform"
    terraform init -backend=false
    terraform fmt -check
    terraform validate
  else
    echo "Error: terraform command not found in bin/ or system PATH."
    exit 1
  fi
fi

# 2. Python Functions Verification
# 各 Python ディレクトリで品質チェックとテストを実行
FUNCTIONS=("import-skill-check" "export-prediction" "send-slack-notification" "scrape-gcp-certifications")
for FUNC in "${FUNCTIONS[@]}"; do
  echo "--> Verifying Python function: $FUNC..."
  cd "$REPO_ROOT/functions/$FUNC"
  uv sync --group dev
  uv run black --check .
  uv run flake8 .
  uv run mypy .
  uv run isort --check-only --diff .
  # radon cyclomatic complexity check
  result=$(uv run radon cc . -e "test_*.py" -n C)
  if [ -n "$result" ]; then
    echo "Error: Cyclomatic complexity is too high (C or worse found) in $FUNC:"
    echo "$result"
    exit 1
  fi
  uv run pytest
done

# 3. Dataform Verification
echo "--> Verifying Dataform compilation..."
cd "$REPO_ROOT"
npx @dataform/cli compile

# 4. Spell Check Verification
echo "--> Verifying Spellings with cSpell..."
npx cspell "functions/**/*" --no-must-find-files

echo "=== Validation Successful ==="
