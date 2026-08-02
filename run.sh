#!/bin/bash
# macOS 启动脚本
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
if command -v conda > /dev/null 2>&1 && conda env list | grep -q "pindou"; then
    conda run -n pindou python main.py
else
    python3 main.py
fi
