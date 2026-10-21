#!/usr/bin/env bash
# 独立验证 harness 源码准备（只读 app/ 源码；不修改产品代码）
# 用法: ./prepare_sources.sh HEAD       # 修复前基线（git HEAD 中的产品源码）
#       ./prepare_sources.sh WORKTREE   # 当前工作区（T8/T9 修复后）
# 注入补丁（与 qa/ui/render 相同策略，最小化）：
#   1) ContentView: @StateObject vm -> @ObservedObject vm（允许探针注入已驱动 VM）
#   2) Engine: 引擎脚本路径改为 PERLER_REPO_ROOT（复制后 #filePath 层级已变）
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
SRC="$ROOT/app/Sources/PerlerApp"
REF="${1:-HEAD}"
DEST="$HERE/Sources/AppCopy"

rm -rf "$DEST"
mkdir -p "$DEST"

# 产品源码文件（排除带 @main 的 PerlerApp.swift；其余全量复制，避免新增文件缺失）
for f in ContentView ColorChartView Engine Models AppViewModel DesignSystem; do
  if [ "$REF" = "WORKTREE" ]; then
    cp "$SRC/$f.swift" "$DEST/$f.swift"
  else
    git -C "$ROOT" show "HEAD:app/Sources/PerlerApp/$f.swift" > "$DEST/$f.swift"
  fi
done

if [ "$REF" = "WORKTREE" ]; then
  for p in "$SRC"/*.swift; do
    b="$(basename "$p")"
    [ "$b" = "PerlerApp.swift" ] && continue
    [ -f "$DEST/$b" ] && continue
    cp "$p" "$DEST/$b"
  done
fi

# 资源（T9 hero 图等）：存在则复制，并在 harness Package.swift 声明 resources
RES_LINE=""
RES_DIR="$SRC/Resources"
if [ "$REF" = "WORKTREE" ] && [ -d "$RES_DIR" ]; then
  cp -R "$RES_DIR" "$DEST/Resources"
  RES_LINE='            resources: [.process("AppCopy/Resources")],'
fi

python3 - "$DEST" "$HERE" "$RES_LINE" <<'PY'
import sys, pathlib
dest = pathlib.Path(sys.argv[1]); here = pathlib.Path(sys.argv[2]); res_line = sys.argv[3]

p = dest / "ContentView.swift"
s = p.read_text(encoding="utf-8")
old = "@StateObject private var vm = AppViewModel()"
assert old in s, "ContentView 注入锚点未找到: " + old
s = s.replace(old, "@ObservedObject var vm: AppViewModel")
p.write_text(s, encoding="utf-8")

p = dest / "Engine.swift"
s = p.read_text(encoding="utf-8")
old = '''        let dir = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        return dir.appendingPathComponent("core_server.py").path'''
new = '''        let root = ProcessInfo.processInfo.environment["PERLER_REPO_ROOT"]
            ?? FileManager.default.currentDirectoryPath
        return URL(fileURLWithPath: root).appendingPathComponent("core_server.py").path'''
assert old in s, "Engine 注入锚点未找到"
s = s.replace(old, new)
p.write_text(s, encoding="utf-8")

pkg = here / "Package.swift"
pkg.write_text(f'''// swift-tools-version: 6.0
// 独立验证离屏 harness（自动生成；只依赖系统 SwiftUI/AppKit，不引入第三方依赖）
import PackageDescription

let package = Package(
    name: "ZoomProbe",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "ZoomProbe",
            path: "Sources",
{res_line}
            swiftSettings: [.swiftLanguageMode(.v5)]
        )
    ]
)
''', encoding="utf-8")

print("prepared:", ", ".join(x.name for x in sorted(dest.glob("*.swift"))), "| resources:", bool(res_line.strip()))
PY
