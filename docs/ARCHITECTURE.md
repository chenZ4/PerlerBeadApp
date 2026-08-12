# 拼豆图纸 · 工程说明（中文）

> 面向长期维护的开发说明：项目结构、分层设计、数据流、关键语义、测试与规范。
> 最后更新：2026-08-13（OOP 化重构完成版）

## 1. 项目结构

```
PerlerBeadApp/
├── core/                      # 核心引擎（双版本共用，零 Tk/SwiftUI 依赖）
│   ├── models.py              # 领域模型：GenerateParams/QueueItem/UndoSnapshot/BatchResult
│   │                          #   纯函数：hex_to_rgb、parse_* 钳制、link_dimensions 比例联动
│   ├── processor.py           # ImageProcessor：图片→图纸渲染管线（含 exact_grid/fit_box 语义）
│   ├── colors.py              # 色卡加载/匹配（numpy 加权 RGB）+ display_to_internal 换算
│   ├── templates.py           # 内置模板库（data/templates/*.json → PIL 图）
│   ├── history_manager.py     # HistoryManager（支持自定义 file_path 便于测试隔离）
│   ├── settings.py            # SettingsStore 类（偏好+队列持久化；旧模块函数保留 dict 兼容）
│   ├── my_colors.py           # My Colors 自定义调色板
│   ├── effects/               # 特效库（geometric/preprocess/grid/chart 四阶段管线）
│   └── services/              # 服务层（业务逻辑零 UI 依赖，可无界面单测）
│       ├── chart_service.py   # ChartService：单图生成/保存/PDF 导出
│       └── batch_service.py   # BatchService：批量队列处理（进度/取消回调式）
├── ui/                        # Tk 版界面（仅 Tk 版使用）
│   ├── app_controller.py      # AppController：组合根（装配面板/状态/服务 + 事件路由）
│   ├── state.py               # AppState：参数快照+图片资源+结构化撤销栈+观察者通知
│   ├── panels/                # 面板组件（各管各的 widget 与交互，经回调通信）
│   │   ├── settings_panel.py  #   图片源/网格/色卡/画布（字段联动内聚在面板）
│   │   ├── preview_panel.py   #   预览渲染/缩放/拖动（图片渲染完全内聚）
│   │   ├── queue_panel.py     #   批量队列 UI
│   │   ├── history_panel.py   #   历史记录 UI
│   │   └── stats_panel.py     #   颜色统计 UI
│   ├── color_chart_ui.py      # 色卡窗口（独立类，滚动网格+搜索+复制）
│   ├── widgets.py             # 通用小组件（section_title 等）
│   ├── theme.py / fonts.py    # 主题与字体
├── app/                       # SwiftUI 版（macOS 14+）
│   └── Sources/PerlerApp/
│       ├── AppViewModel.swift # 交互逻辑（可测试：模拟用户操作+真实引擎）
│       ├── ContentView.swift  # 主界面（GridFieldRow 独立 View 结构体）
│       ├── Engine.swift       # 引擎协议客户端（stdio 行协议，主线程回调）
│       ├── Models.swift       # GenerateResult 等协议模型
│       └── ColorChartView.swift
├── core_server.py             # 引擎服务化入口（JSON 行协议，Swift 版调用）
├── data/                      # 色卡 JSON（4 套）+ 内置模板 JSON（6 个）
├── tests/
│   ├── run_tests.py           # 引擎+模型+服务层自动化（148 项）
│   └── gui_smoke.py           # Tk 版 GUI 冒烟（69 项，零弹窗零交互）
└── app/Tests/PerlerAppTests/  # Swift 测试（51 项）
```

## 2. 分层设计（Tk 版 OOP 化后的目标架构）

```
┌─────────────────────────────────────────────┐
│  AppController（组合根）                      │
│  · 装配 panels/state/services                │
│  · 菜单/快捷键/拖拽/模态守卫                  │
│  · 动作路由：选图→生成→状态→面板刷新          │
└───────┬──────────────┬───────────────┬──────┘
        │回调           │读写            │调用
┌───────▼──────┐ ┌─────▼──────┐ ┌──────▼──────────────┐
│ panels/      │ │ AppState   │ │ services/            │
│ 只做交互与   │ │ 参数快照    │ │ ChartService         │
│ widget 构建  │ │ 图片资源    │ │ BatchService         │
│              │ │ 撤销栈      │ └──────────┬───────────┘
└──────────────┘ │ 观察者通知  │            │
                 └─────────────┘ ┌──────────▼───────────┐
                                 │ core.processor 引擎  │
                                 │ core.models 领域模型 │
                                 └──────────────────────┘
```

规则：

1. **业务逻辑零 Tk 依赖**：`core/models.py`、`core/services/` 不 import tkinter，可无界面单测。
2. **面板之间不互相调用**：只通过回调与控制器通信；状态读写走 `AppState`。
3. **参数唯一事实来源**：`GenerateParams` 快照。面板 `current_params()` 输出快照，`apply_params()` 写回控件（撤销/历史/模板加载用）。
4. **图片生命周期集中管理**：`AppState.replace_*` 负责旧图 `close()`，防内存泄漏。

## 3. 关键数据流

### 3.1 生成（Tk 版）

```
用户改参数 → SettingsPanel 回调 → AppController._on_dimension_change/_on_setting_change
  → AppState.save_state()（压撤销栈）→ _trigger_preview()（800ms 防抖）
  → generate_preview() → _sync_params_from_panel()（面板→GenerateParams 快照）
  → ChartService.generate(image_path, params) → processor.process_image(...)
  → AppState.apply_result(result) + PreviewPanel.set_images(...) + StatsPanel.update(...)
```

### 3.2 批量队列

```
QueuePanel 按钮 → AppController.enqueue_item（QueueItem 快照入队 + 持久化）
  → process_queue → BatchService.process(items, out_dir, on_progress, is_cancelled)
  → 每项：ChartService 管线 → 导出 PNG/PDF → HistoryManager.add_record
  → BatchResult(success/failed/cancelled_remaining) → 面板汇总 + 消息框
```

### 3.3 撤销

```
AppState.previous_states: List[UndoSnapshot]（上限 10）
undo() → 弹栈 → 面板 apply_params + 恢复 selected_file → 重新生成预览
注意：首快照的 selected_file 可能为 None（选图前保存），undo 时仅当非空才恢复，
避免把选图状态误清空（历史 bug 已修复）。
```

### 3.4 Swift 版引擎协议（core_server.py）

stdio 行协议（JSON 一行一条）：

```
请求: {"id":1,"op":"generate","params":{...}}
响应: {"id":1,"ok":true,...}
事件: {"id":1,"event":"progress","progress":0.5}
取消: {"id":1,"op":"cancel"}
```

Swift 侧 `Engine` 处理行缓冲、超时（15s）、退出快速失败、回调强制主线程。

## 4. 比例模式语义（核心易错点）

| 模式 | 引擎参数 | 行为 |
|---|---|---|
| 原始比例（宽为基准） | 均不传 | 以较宽一侧为基准，另一侧按源图比例重算（可能忽略输入的一侧） |
| 等比完整（适应框内） | `fit_box=True` | 请求框内等比完整放入 |
| 1:1 / 4:3 / 3:4 / 16:9 / 9:16 | `exact_grid=True` | **精确网格**，不被源图比例覆盖 |
| 自定义 | 均不传 | 同原始比例 |

历史主诉「设 40×40 结果被源图比例覆盖成 40×30」的根因：界面选了固定比例但未传
`exact_grid`。**Tk 版 2026-08-13 已修复**（`ChartService`/`BatchService` 统一处理），
Swift 版 2.1.3 已修复。

比例联动规则（`core.models.link_dimensions`，Tk 与 Swift 行为对齐）：
- 双向联动：编辑宽 → 高跟随；编辑高 → 宽跟随（四舍五入 `round()`）
- Swift 版生成前按 `lastEditedDim` 自动联动兜底

## 5. 测试策略

| 套件 | 覆盖 | 命令 |
|---|---|---|
| `tests/run_tests.py` | 引擎管线/色卡/模板/BOM/PDF/特效/协议/模型/服务 | `conda run -n pindou python tests/run_tests.py` |
| `tests/gui_smoke.py` | Tk 版全流程（面板/队列/撤销/拖动/持久化/内存） | `conda run -n pindou python tests/gui_smoke.py` |
| `app/` swift test | Swift VM + 引擎协议 + 网格回归 | `cd app && swift test` |

约定：

- **测试门禁**：三套全绿才可交付；不采信口头结果，必须由执行者独立跑出绿。
- gui_smoke 全程零弹窗零交互（打桩 filedialog/messagebox）。
- 测试数据隔离：`HistoryManager(file_path=...)`、临时目录；不得污染仓库根目录的
  `history.json` / `app_settings.json` / `queue_state.json`。
- 已知无害现象：`run_tests` 中「文件不存在返回 None」用例会打印一条引擎 traceback
  （processor 的容错日志），属预期输出，不影响结果。

## 6. 开发规范

1. **分步提交**：每阶段一个本地 commit，中文消息，不 push（由仓库所有者手动推送）。
2. **提交前回归**：改 UI 跑 gui_smoke；改 core 跑 run_tests；改 Swift 跑 swift test。
3. **加功能先加测试**：修复 bug 必须带回归用例（本次修复均附带）。
4. **不要破坏兼容层**：`core_server.py` 协议字段、历史/队列 JSON 字段是持久化契约，
   改动必须保留旧格式读取（`GenerateParams.from_dict` / `QueueItem.from_legacy` 兼容
   `canvas_size`/`output_size` 等旧字段名）。
5. **常量单一来源**：比例/尺寸/颜色常量以 `core/models.py` 为准；Tk 与 Swift 各自
   从模型层取值或保持语义一致。

## 7. 已知限制

- Tk 版暂无特效面板（特效仅在 Swift 版暴露，引擎层已支持）。
- 1:1 PDF 的出血/页码为栅格绘制，拼贴效果需打印后人工确认。
- Windows 端 Tk 主题与快捷键逻辑已实现，需在 Windows 机器跑一次 gui_smoke 确认。
- 原始比例模式下引擎会以较宽一侧为基准，另一侧输入可能被忽略（语义如此，见第 4 节）。
