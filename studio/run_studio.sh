#!/usr/bin/env bash
# Start PhotoCraft VStitcher Localhost Studio on port 8092
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo " Starting PhotoCraft x Browzwear VStitcher Studio"
echo " URL: http://127.0.0.1:8095"
echo " Engine: /Users/ragavij/Documents/Developer/photocraft/target/release/photocraft-cli"
echo "=========================================================="

exec python3 server.py
