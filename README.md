# 拼豆图纸 (PerlerBeadApp)

图片转拼豆图纸工具：自动映射色卡、生成带行列标号与耗材统计的高清图纸，支持 PNG / PDF 导出与批量处理。

## 双版本

| 版本 | 目录 | 技术栈 | 适用 |
|---|---|---|---|
| **Tk 版**（保底） | `main.py` + `ui/` | Python + Tkinter | macOS / Windows，Tk 8.6+ |
| **SwiftUI 版**（主推） | `app/` | SwiftUI (macOS 14+) | macOS 原生体验 |

两版共用同一核心引擎（`core/`），Swift 版通过 `core_server.py`（stdio JSON 协议）调用。

## 功能

- 图片 → 色卡自动映射（MARD 221 / 佩勒 24 / 哈马 16 / 基础 8 / My Colors）
- 网格设置：宽/高/每格像素独立调节；比例模式（原始比例 / 等比完整 / 1:1 / 4:3 / 3:4 / 16:9 / 9:16 / 自定义），固定比例精确生效
- 行列标号 / 网格线 / 颜色图例 / 耗材统计 / 成品效果预览
- 预览缩放（25%~400%）、滚轮缩放、拖动平移、适应窗口、双击居中
- 导出：PNG / PDF（适应 A4 单页 或 1:1 实物大小 5mm/颗 多页拼接，含出血与页码）
- 批量队列：快照设置、缩略图、取消、防覆盖文件名、断点恢复
- 历史记录（自动迁移旧格式）、设置持久化、撤销（结构化快照）、快捷键、拖拽选图
- Swift 版额外：特效库 14 项（描边/灰度/抖动/限色/风格预设/大头等）、手动格子编辑（点击换色/撤销）、进度追踪（自动保存续做）、色卡窗口

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

## 测试（交付门禁，三套必须全绿）

```bash
conda run -n pindou python tests/run_tests.py   # 引擎+模型+服务层无界面自动化
conda run -n pindou python tests/gui_smoke.py   # Tk 版 GUI 冒烟（零弹窗零交互）
cd app && swift test                            # Swift 版（VM + 引擎协议 + 回归）
```

当前基线：`run_tests` 148 项 / `gui_smoke` 69 项 / `swift test` 51 项，全部通过。

## 工程说明

架构设计、数据流、比例模式语义、开发规范详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 数据文件（自动生成，已 gitignore）

- `output/` 输出图片
- `history.json` 历史记录
- `app_settings.json` 用户偏好
- `queue_state.json` 批量队列
- `track/` Swift 版进度追踪
