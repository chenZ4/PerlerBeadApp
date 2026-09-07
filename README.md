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
- 预览缩放（25%~400%）、滚轮缩放、拖动平移、适应窗口、双击居中
- 导出：PNG / PDF（适应 A4 单页 或 1:1 实物大小 5mm/颗 多页拼接，含出血与页码）
- 批量队列：快照设置、缩略图、取消、防覆盖文件名、断点恢复
- 历史记录（自动迁移旧格式）、设置持久化、撤销（结构化快照）、快捷键、拖拽选图
- Swift 版特效库 **15 项全暴露**（描边/灰度/抖动/限色/风格预设/画面调整/裁剪/镜像/赛璐璐/霓虹/双色调/背景去除/大头等，带参数控件）、手动格子编辑（点击换色/撤销）、进度追踪（自动保存续做）、色卡窗口

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

UI 测试已本地验证 3/3（启动+引擎初始化、模板→生成 E2E、拖拽安全）。
注意：不要给 xcodebuild 加 `CODE_SIGNING_ALLOWED=NO`，未签名 Runner 会被 macOS 拒绝启动；
工程内已配置 ad-hoc 签名（project.yml），无需证书。

当前基线：`run_tests` 214 项 / `gui_smoke` 92 项 / `stress_protocol` 12 项 / `swift test` 78 项，全部通过。
CI：push/PR 自动跑（GitHub Actions：Python 双平台 + Swift + Windows Tk 冒烟 + UI 测试观察项）。

## 工程说明

架构设计、数据流、比例模式语义、开发规范详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 数据文件（自动生成，已 gitignore）

- `output/` 输出图片
- `history.json` 历史记录
- `app_settings.json` 用户偏好
- `queue_state.json` 批量队列
- `track/` Swift 版进度追踪
