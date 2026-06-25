#!/usr/bin/env bash
set -euo pipefail

# generate-chart.sh — Generate the any-sync Helm chart from docker-compose.yml
#
# Prerequisites:
#   - kompose (https://kompose.io/)
#   - python3 with pyyaml (pip install pyyaml)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
TMP_DIR="$REPO_ROOT/.tmp-chart"
CHART_DIR="$REPO_ROOT/charts/any-sync"

echo "=== any-sync Helm chart generator ==="

# --- Check prerequisites ---
if ! command -v kompose &>/dev/null; then
    echo "ERROR: 'kompose' not found. Install from https://kompose.io/"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "ERROR: 'python3' not found."
    exit 1
fi

python3 -c "import yaml" 2>/dev/null || {
    echo "ERROR: Python pyyaml not installed. Run: pip install pyyaml"
    exit 1
}

# --- Prepare environment ---
echo "1. Preparing .env from .env.example..."
cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"

# --- Run kompose ---
echo "2. Running kompose convert..."
rm -rf "$TMP_DIR"
kompose convert -c -f "$REPO_ROOT/docker-compose.yml" -o "$TMP_DIR" 2>&1 | grep -E "^(INFO|WARN)" || true

# --- Run post-processor ---
echo "3. Running post-processor..."
rm -rf "$CHART_DIR/templates" "$CHART_DIR/Chart.yaml" "$CHART_DIR/values.yaml"
mkdir -p "$CHART_DIR/templates"
python3 "$REPO_ROOT/scripts/postprocess.py"

# --- Copy hand-crafted templates ---
echo "4. Copying hand-crafted templates..."
if [ -d "$REPO_ROOT/helm-templates" ]; then
    cp -v "$REPO_ROOT/helm-templates/"* "$CHART_DIR/templates/" 2>/dev/null || true
fi

# --- Cleanup ---
echo "5. Cleaning up..."
rm -rf "$TMP_DIR"
rm -f "$REPO_ROOT/.env"

echo ""
echo "=== Chart generated at $CHART_DIR ==="
echo "Run 'helm lint $CHART_DIR' to validate."
echo "Run 'helm template test $CHART_DIR' to render."
