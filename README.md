# 拼豆图纸 (PerlerBeadApp)

图片转拼豆图纸工具：自动映射色卡、生成带行列标号与耗材统计的高清图纸，支持 PNG / PDF 导出与批量处理。

支持 macOS / Windows（需 Tk 8.6+）。

## 环境准备

建议使用 conda 环境（系统 Python 的 Tk 8.5 无法运行本程序）：

```bash
conda create -n pindou python=3.11 -y
conda run -n pindou pip install -r requirements.txt
```

pip 镜像（可选，国内加速）：`https://mirrors.cloud.tencent.com/pypi/simple/`

## 运行

```bash
conda run -n pindou python main.py
```

或直接运行 `./run.sh`（macOS）/ `run.bat`（Windows）。

## 测试

```bash
conda run -n pindou python tests/run_tests.py   # 无界面自动化测试（45 项）
conda run -n pindou python tests/gui_smoke.py   # GUI 冒烟测试（53 项）
```

测试报告详见 `TEST_REPORT.md`。

## 功能

- 图片 → 色卡自动映射（MARD 221 / 佩勒 24 / 哈马 16 / 基础 8）
- 每格像素独立调节（默认 60px/格，输出清晰度与格子数解耦）
- 行列标号 / 网格线 / 颜色图例 / 耗材统计 / 成品效果预览
- 预览缩放（25%~400%）、滚轮缩放、拖动平移、适应窗口
- 导出：PNG / PDF（适应 A4 单页 或 1:1 实物大小 5mm/颗 多页拼接，含出血与页码）
- 批量队列：快照设置、缩略图、取消、断点恢复
- 历史记录（自动迁移旧格式）、设置持久化、快捷键（Cmd/Ctrl+O/S/P/E/±）、拖拽选图

## 数据文件（自动生成，已 gitignore）

- `output/` 输出图片
- `history.json` 历史记录
- `app_settings.json` 用户偏好
- `queue_state.json` 批量队列
