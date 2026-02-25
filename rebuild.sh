#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=== Removing existing output files ==="
rm -f "$REPO_ROOT/model_prices_and_context_window.json" \
      "$REPO_ROOT/model_prices_and_context_window.sha256"

echo "=== Running sync script ==="
python3 "$REPO_ROOT/scripts/sync_prices.py" --config config.json --repo-root "$REPO_ROOT"

echo "=== Done ==="
