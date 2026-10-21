# T6 编辑部风 UI 落地 · 验收截图（qa/ui/after/）

> 生成时间：2026-10-21 · App 2.3.0（T6 重构分支）· macOS 27.0.1 / Swift 6.4  
> 构建：`cd app && swift build --disable-sandbox`（本机 DSH 文件沙箱不允许 SwiftPM 嵌套 sandbox-exec；普通终端下 `swift build` 等价）  
> 启动：`.build/debug/PerlerApp`（真实二进制；截图用 `screencapture -x -o -l <CGWindowID>` 按窗口抓取）  
> 不涉及 git commit/push。

## 1. 真实启动截图（空状态，1920×…） 

| 文件 | 外观 | 内容区尺寸 | 说明 |
|---|---|---|---|
| `real_empty_light_1280x800.png` | light | 1280 × 800（窗口含标题栏 1280×800） | 封面空状态 + 示例图版/模板/快捷键 + 状态条 |
| `real_empty_dark_1280x800.png` | dark | 1280 × 800 | 黑卡纸 + 米白墨 + 朱砂 |
| `real_empty_light_1440x900.png` | light | 1440 × 858* | 大窗版式（两栏右侧留白扩大） |
| `real_empty_dark_1440x900.png` | dark | 1440 × 858* | 同上，暗色 |

\* 本机显示器可用高度约 858pt（1470×956 屏幕 − 菜单栏 − Dock），macOS 会把窗口高度限制在屏幕可见区，所以 1440×900 请求实际落为 1440×858。要求严格 1440×900 的验收请在 ≥1440×900 可用高度的显示器上复跑（命令见 §3）。

## 2. 内容态截图（同源码离屏 harness，真实引擎）

真机无法用键盘自动化选图（本机 `AXIsProcessTrusted=false`，System Events 返回 -10004），内容态用 `qa/ui/render/` harness：复制同一份 ContentView/DesignSystem/AppViewModel，仅把 `@StateObject vm` 改为 `@ObservedObject vm` 以注入驱动，其余为真实视图与真实 `core_server.py` 引擎。

| 文件 | 内容 |
|---|---|
| `harness_current_1280_light_v2.png` | 主工作台 1280 宽 / 亮色：左 spec sheet、中 hero 图纸、右耗材+导出 |
| `harness_current_1440_light_v2.png` | 主工作台 1440 宽 / 亮色 |
| `harness_current_1280_dark_v2.png` | 主工作台暗色（含已应用 2 项特效与编辑模式） |
| `harness_effects_expanded_light.png` | 展开参数/编辑模式状态 |
| `harness_effects_gallery_light_v2.png` | 特效画廊 sheet（15 项分 5 组，编辑式卡片替代 Toggle 墙） |
| `harness_colorschart_light_v2.png` | 色卡弹窗重绘（9 列色样册、搜索、复制） |

生成数据：`qa/lead/inputs/eagle.png` 512×512 → MARD 221 色卡 / 60×60 网格 / 3,600 颗 / 52 色。

## 3. 复跑命令

~~~bash
# 构建
cd app && swift build --disable-sandbox   # 或普通终端：swift build
# 真实启动 + 指定外观/尺寸（QA 环境变量；不影响正常使用）
PERLER_APPEARANCE=light PERLER_WINDOW_SIZE=1280x800 app/.build/debug/PerlerApp &
PERLER_APPEARANCE=dark  PERLER_WINDOW_SIZE=1440x900 app/.build/debug/PerlerApp &
# 抓窗口：先取 CGWindowID（owner=PerlerApp），再
screencapture -x -o -l <CGWindowID> qa/ui/after/xxx.png
# 内容态（真实引擎生成 + 离屏快照）
qa/ui/render/prepare_sources.sh
cd qa/ui/render && swift build --disable-sandbox \
  --cache-path ../../qa/ui/tmp/spm-cache --config-path ../../qa/ui/tmp/spm-config \
  --security-path ../../qa/ui/tmp/spm-security
cd /path/to/PerlerBeadApp && PERLER_REPO_ROOT=$PWD TMPDIR=$PWD/qa/ui/tmp \
  qa/ui/render/.build/debug/UIShot audit
~~~

## 4. 已知限制 / 待接

- `PERLER_WINDOW_SIZE` / `PERLER_APPEARANCE` 是 QA 截图钩子（PerlerApp.swift AppDelegate），只在有 env 时生效。
- 自动预览（T5）已接线：AppViewModel 的 didSet + UI 的 `uiNotifyParametersChanged()` 双通道触发 `parametersDidChange()` → 500ms debounce 自动重渲染；状态条/侧栏/画廊底栏显示「正在自动刷新预览… / 参数已修改 · 即将刷新」；手动「生成」优先且会取消 pending 自动预览。
- T5 新增参数控件（描边宽度/线稿强度/灰度对比度/抖动强度）已在特效画廊参数面板接线。
- 特效画廊 Phase 1 无 per-effect 缩略图（按 Lead 要求不伪造）；等 T5 `effectPreviews` 到位后替换卡片缩略区。
- 1440×900 受本机屏幕高度限制（见上）。