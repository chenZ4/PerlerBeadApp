# 拼豆图纸 (PerlerBeadApp)

图片转拼豆图纸工具：自动映射色卡、生成带行列标号与耗材统计的高清图纸，支持 PNG / PDF 导出与批量处理。

## 双版本

| 版本 | 目录 | 技术栈 | 适用 |
|---|---|---|---|
| **Tk 版**（保底） | `main.py` + `ui/` | Python + Tkinter | macOS / Windows，Tk 8.6+ |
| **SwiftUI 版**（主推） | `app/` | SwiftUI (macOS 14+) | macOS 原生体验 |

两版共用同一核心引擎（`core/`），Swift 版通过 `core_server.py`（stdio JSON 协议）调用。

## 功能

- 图片 → 色卡自动映射（**CIELAB 感知色距**，渐变更平滑、饱和色不映错色相；MARD 221 / 佩勒 24 / 哈马 16 / 基础 8 / My Colors）
- 网格设置：宽/高/每格像素独立调节；比例模式（原始比例 / 等比完整 / 1:1 / 4:3 / 3:4 / 16:9 / 9:16 / 自定义）
- **网格输入实时联动（Tk 与 Swift 一致）**：改一侧另一侧逐键跟随（固定比例按比例、原始比例/等比完整按源图像素比，无图时按 1:1 兜底）；引擎 WYSIWYG——UI 联动配对即引擎最终网格
- 行列标号 / 网格线 / 颜色图例 / 耗材统计 / 成品效果预览
- 预览缩放（25%~400%，面板常驻 −/滑块/＋/百分比/重置，`⌘+` / `⌘−` / `⌘0`）：鼠标滚轮/触控板双指 pinch 以光标为锚点缩放，双指滚动/拖拽平移，平移带 15% 可见钳制，适应窗口显示真实缩放比例
- 导出：PNG / PDF（适应 A4 单页 或 1:1 实物大小 5mm/颗 多页拼接，含出血与页码）；**2.6.0 起生成的图纸/成品/PDF 与 App 同一套老钱风**（暖纸底 + 深咖墨 + 干邑黄铜、PLATE 页脚、编辑式 MATERIALS 图例与 BOM 材料页、CJK 混排）
- 批量队列：快照设置、缩略图、取消、防覆盖文件名、断点恢复
- 历史记录（自动迁移旧格式）、设置持久化、撤销（结构化快照）、快捷键、拖拽选图
- Swift 版特效库 **15 项全暴露**（描边/灰度/抖动/限色/风格预设/画面调整/裁剪/镜像/赛璐璐/霓虹/双色调/背景去除/大头等，带参数控件）、**参数变更 500ms 防抖自动重渲染预览**（无需再点生成）、非致命提示（如大头未检测到人脸）显示在状态栏、手动格子编辑（点击换色/撤销）、进度追踪（自动保存续做）、色卡窗口
- Swift 版采用**老钱风/编辑杂志风界面**（2.5.x：暖羊皮纸 + 深咖墨 + 干邑/黄铜、报头双线/编号章节/图版图注 + 耗材 inspector，亮暗双主题；开始页为**左侧整幅「照片 → 拼豆」背景大图** + 右侧操作列，无示例缩略图干扰）；**生成图/PDF 同源同一套 tokens（core/models.py → processor 渲染）**

## 环境准备

建议使用 conda 环境（系统 Python 的 Tk 8.5 无法运行 Tk 版）：

```bash
conda create -n pindou python=3.11 -y
conda run -n pindou pip install -r requirements.txt
```

pip 镜像（可选，国内加速）：`https://mirrors.cloud.tencent.com/pypi/simple/`

## 运行

```bash
# Tk 版
conda run -n pindou python main.py     # 或 ./run.sh / run.bat

# Swift 版（macOS 14+，需 pindou 环境提供引擎）
cd app && swift run
```

## 测试（交付门禁，全绿）

```bash
conda run -n pindou python tests/run_tests.py        # 引擎+模型+服务层无界面自动化
conda run -n pindou python tests/gui_smoke.py        # Tk 版 GUI 冒烟（零弹窗零交互）
conda run -n pindou python tests/stress_protocol.py  # 协议压力：取消风暴/垃圾输入/内存基线
cd app && swift test                                 # Swift 版（VM + 引擎协议 + 回归）
```

可选（XCUITest 真实 UI 层，需 XcodeGen 生成工程）：

```bash
brew install xcodegen
cd app && xcodegen generate
xcodebuild test -project PerlerApp.xcodeproj -scheme PerlerApp -destination 'platform=macOS'
```

XCUITest 属可选观察项：需要 XcodeGen 生成工程，且依赖 macOS 自动化权限；**不在 4 套交付门禁内**，本仓库当前未提供可核验的通过记录（详见 [qa/gates/report.md](qa/gates/report.md)）。
注意：不要给 xcodebuild 加 `CODE_SIGNING_ALLOWED=NO`，未签名 Runner 会被 macOS 拒绝启动；
工程内已配置 ad-hoc 签名（project.yml），无需证书。

当前基线（2026-10-22 独立复测，顺序执行）：`run_tests` 279 项 / `gui_smoke` 92 项 / `stress_protocol` 12 项 / `swift test` 111 项，共 494 项全绿。
注意：测试套件会写共享 `output/`（并可能裁剪旧产物），必须顺序执行；不要并发跑。
CI：push/PR 自动跑（GitHub Actions：Python 双平台 + Swift + Windows Tk 冒烟 + UI 测试观察项）。

## QA 与 2.6.0 质量报告

- 独立 QA（特效视觉复现/门禁有效性/测试污染）与修复证据：[qa/](qa/)（报告 + mockup + 截图 + 可复跑脚本）
- 特效「代码可行但效果不可行」根因与修复前后数据：[qa/effects/report.md](qa/effects/report.md) / [qa/effects/T5_report.md](qa/effects/T5_report.md)
- UI 审计与编辑杂志风设计/落地：[qa/ui/audit.md](qa/ui/audit.md) / [重构 mockup](qa/ui/mockups/mockup_01_main_1280.png)
- 老钱风棕色 tokens/对比度：[qa/ui/theme/README.md](qa/ui/theme/README.md) / [落地截图](qa/ui/after/README.md)
- 缩放/平移修复与独立验证：[qa/verify/zoom_pan_and_theme_report.md](qa/verify/zoom_pan_and_theme_report.md)
- 封面改版（去掉示例面板 + 左侧整幅 hero）独立验证：[qa/verify/cover_redesign_report.md](qa/verify/cover_redesign_report.md)
- 生成图/成品/PDF editorial 风格统一（tokens 同源、CJK 混排修复）：[qa/effects/style/README.md](qa/effects/style/README.md) / [独立验证](qa/verify/style_unification_report.md)
- 开源算法/设计参考（含 license）：[qa/research/report.md](qa/research/report.md)
- 门禁复测与测试有效性盲区：[qa/gates/report.md](qa/gates/report.md)

## 工程说明

架构设计、数据流、比例模式语义、开发规范详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 数据文件（自动生成，已 gitignore）

- `output/` 输出图片
- `history.json` 历史记录
- `app_settings.json` 用户偏好
- `queue_state.json` 批量队列
- `track/` Swift 版进度追踪
