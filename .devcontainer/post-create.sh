#!/usr/bin/env bash
# Devcontainer 初回作成時のセットアップ
# - Python 依存パッケージのインストール (agent-framework-foundry 1.0 GA + aiohttp)
# - azd microsoft.foundry 拡張のインストール (Hosted Agent / Inspector / Project / Toolbox 等を提供)
set -euo pipefail

echo "==> Upgrading pip"
python -m pip install --upgrade pip

echo "==> Installing workshop Python packages"
pip install -r .devcontainer/requirements.txt

echo "==> Installing azd microsoft.foundry extension"
# 最新の Hosted Agent Quickstart で正規となっている拡張名。
# 既にインストール済みでも失敗扱いにしない (再ビルド時のため)。
azd ext install microsoft.foundry || azd ext upgrade microsoft.foundry || true

echo "==> Versions"
python --version
az --version | head -n 1
azd version
gh --version | head -n 1
azd ext list || true

echo "==> Done. 次に 'az login' と 'azd auth login' を実行してください。"
