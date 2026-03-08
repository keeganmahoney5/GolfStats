#!/usr/bin/env bash
# Export rounds and analytics to share-data.json for static deployment.
# Requires the backend to be running at http://127.0.0.1:8000

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_FILE="$PROJECT_ROOT/frontend/public/share-data.json"
API_URL="${API_URL:-http://127.0.0.1:8000}"

mkdir -p "$(dirname "$OUTPUT_FILE")"
echo "Fetching export from $API_URL/api/export/share ..."
curl -sSf "$API_URL/api/export/share" -o "$OUTPUT_FILE"
echo "Saved to $OUTPUT_FILE"
