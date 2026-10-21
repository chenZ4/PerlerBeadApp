# 拼豆图纸 · 工程说明（中文）

> 面向长期维护的开发说明：项目结构、分层设计、数据流、关键语义、测试与规范。
> 最后更新：2026-10-21（2.5.0 特效质量重做 + 老钱风编辑杂志 UI + 自动预览 + 缩放/平移修复）

## 1. 项目结构

```
PerlerBeadApp/
├── core/                      # 核心引擎（双版本共用，零 Tk/SwiftUI 依赖）
│   ├── models.py              # 领域模型：GenerateParams/QueueItem/UndoSnapshot/BatchResult
│   │                          #   纯函数：hex_to_rgb、parse_* 钳制、link_dimensions 比例联动
│   ├── processor.py           # ImageProcessor：图片→图纸渲染管线（含 exact_grid/fit_box 语义）
│   ├── colors.py              # 色卡加载/匹配（CIELAB D65 感知色距）+ display_to_internal 换算
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
│       ├── AppViewModel.swift # 交互逻辑（可测试：模拟用户操作+真实引擎；含参数变更自动预览防抖）
│       ├── ContentView.swift  # 编辑杂志风主界面（报头/三栏/图版图注/特效画廊 sheet）
│       ├── DesignSystem.swift # 老钱风 tokens（暖纸/深咖/干邑黄铜）/字体/原子组件（亮暗双主题）
│       ├── EditorialAssets.swift # 内置素材加载（SPM Bundle.module / Xcode bundle / 源码树回退）
│       ├── Resources/         # 内置素材（开始页封面大图 2400×1800：照片→拼豆对角过渡）
│       ├── Engine.swift       # 引擎协议客户端（stdio 行协议，主线程回调）
│       ├── Models.swift       # GenerateResult 等协议模型（含 warnings 兼容解码）
│       └── ColorChartView.swift
├── core_server.py             # 引擎服务化入口（JSON 行协议，Swift 版调用）
├── data/                      # 色卡 JSON（4 套）+ 内置模板 JSON（6 个）
├── tests/
│   ├── run_tests.py           # 引擎+模型+服务层自动化（279 项，2026-10-22 基线）
│   └── gui_smoke.py           # Tk 版 GUI 冒烟（92 项，零弹窗零交互）
└── app/Tests/PerlerAppTests/  # Swift 测试（111 项 = 既有 84 + 缩放/平移 11 + 独立验证 15 + hero 资源 1）
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

**响应 warnings 字段（2026-10-21）**：`generate` / `edit` 响应可带 `warnings: [String]`，
承载非致命提示：大头未检测到人脸、背景去除目标色未触边而跳过、几何特效改写网格、
抖动 strength 被钳制、未知特效 id 等。Swift `GenerateResult` 兼容解码（缺失=[]），
由 `AppViewModel` 拼进状态栏；旧客户端忽略该字段即可，属向后兼容扩展。

**参数变更自动预览（2026-10-21）**：`AppViewModel` 的网格/特效参数 `didSet` 与 UI 显式
`uiNotifyParametersChanged()` 双通道调用 `parametersDidChange()` → 置 `needsRegenerate`
并 500ms 防抖触发 `scheduleAutoPreview()`；忙时排队、手动「生成」优先并取消 pending。
预览重算走同一 `generate` op（非独立低清通道），100×100 网格约 1s。

### 3.5 预览缩放/平移（2026-10-21 二轮修复）

- **状态**：`AppViewModel.zoom`（25~400%）、`fitToWindow`、`offset`；fit 与手动缩放互斥且可无缝切换。
- **UI**：`ContentView` 预览右上角常驻 −/滑块/＋/百分比/适应窗口/重置；任意缩放交互自动切出 fit。
- **事件**：`PreviewInputCatcher`（NSViewRepresentable + `NSEvent.addLocalMonitorForEvents`，命中测试穿透）
  捕获 `scrollWheel` / `magnify`：鼠标滚轮（及 ⌘/⌥+滚动）以光标为锚点缩放；触控板双指滚动平移；
  pinch 缩放；仅当事件窗口/光标在预览区时消费，不干扰左右 ScrollView。
- **数学**：`PreviewViewport` 纯函数（displaySize / fittedZoomPercent / clampZoom / anchoredOffset /
  clampOffset）——锚点缩放保持光标下像素不动；offset 钳制为「大图至少 15% 可见、小图居中」。
  单测 `app/Tests/PerlerAppTests/ZoomPanTests.swift`。
- **快捷键**：⌘+ / ⌘− / ⌘0（重置视图）；双击居中；编辑模式下禁用拖拽（点击换色优先）。

### 3.6 开始页封面（2.5.1）

- 布局：左侧为整幅封面大图（2400×1800，左上清晰照片→右下拼豆对角过渡 + 渐进像素化 + 拼豆格线），
  铺满内容区高度与左侧宽度，无边框；底部渐隐 scrim + 奶油色图注；右侧为 430pt 固定操作列
  （标题 / CTA / 快捷键 / 输出）。封面不出现任何彩色模板缩略图（示例图版面版已移除，
  模板入口保留在工作台侧栏下拉）。
- 布局注意：hero 用 `GeometryReader` 显式尺寸 + 铺底 `Rectangle`，图片不参与 HStack 理想宽计算，
  否则 `.aspectRatio(.fill)` 会把右列 430pt 压到 400、吃掉 30pt 右内边距（2.5.1 已修）。
- 素材加载：`EditorialAssets.heroPhotoToBeadsCover`（SPM Bundle.module / Xcode Bundle.main / 源码树回退）。

### 3.7 生成图/成品/PDF 风格统一（2.6.0）

- **tokens 单一来源**：`core/models.py` 的 EDITORIAL_* 常量（paper/paperDeep/paperMat/ink/inkSoft/
  inkMuted/hairline/hairlineStrong/accent + dark 组）与 App `DesignSystem.swift`、`qa/ui/theme/README.md`
  同源；`core/processor.py` 只消费这些常量，不允许散落新色值。
- **图纸**：paper 底、默认网格线 hairline（`DEFAULT_GRID_COLOR #D5C4AC`，显式旧值仍兼容）、
  行列标号 paperDeep + ink + 每 5 个 accent、图例 4–5 列编辑式（MATERIALS 标题/双线/方形色块/右对齐数量）、
  页脚 PLATE + Didot/Georgia 大数字 + 元数据行；旧蓝色 (0,120,215) 全量移除。
- **色号可读性**：珠色上的色号文字按 WCAG 在 ink/paperMat 中取对比度更高者（全 MARD 最坏约 3:1，
  run_tests 有断言；个别中间调珠可能 2.3–4.5，属已知 P3 观察）。
- **CJK 混排**：PIL 不做字体回退，含中文的串禁止整串用 mono；`processor._text_runs/_draw_mixed_text`
  按中文/ASCII 拆段（中文 body、数字 mono、同基线），run_tests 有「CJK 串不得用 mono」守卫。
- **dark_chart**：espresso #17120D / panel #1E1811 / cream ink / brass accent。
- **PDF**：A4 图表页 paper + 细框 + 页码（不重复图表内 PLATE 页脚）；BOM 页编辑式材料表；
  1:1 页纸底 + 裁切角线；页面尺寸/页数/裁切语义与 2.5.x 一致（run_tests 断言）。
- **golden 语义**：`tests/golden/golden_matrix.json` 只哈希 finished 的纯珠像素区（满覆盖素材无背景），
  因此「底色/文字/PDF 改版」不改变哈希；若改的是珠色映射/特效算法才需重生成。

## 4. 比例模式语义（核心易错点）

| 模式 | 引擎参数 | 行为 |
|---|---|---|
| 原始比例（宽为基准） | 均不传 | **WYSIWYG**：请求为「联动配对」时原样生效；模糊请求以宽为基准 |
| 等比完整（适应框内） | `fit_box=True` | **WYSIWYG**：请求为「联动配对」时原样生效；模糊请求等比放入框内 |
| 1:1 / 4:3 / 3:4 / 16:9 / 9:16 | `exact_grid=True` | **精确网格**，不被源图比例覆盖 |
| 自定义 | 均不传 | 同原始比例 |

**联动配对与引擎 WYSIWYG（2026-09-08 修复，主诉「联动没解决/生成尺寸对不上」）**：

- 联动配对 = 编辑侧值 + 另一侧按公式半上舍入（`math.floor(x+0.5)`，对齐 Swift `.rounded()`；
  **Python 内建 `round()` 是银行家舍入，x.5 向下，联动公式禁用**）。
  固定比例按比例联动；原始比例/等比完整按源图像素比联动。
- 引擎收到请求后与「宽基准/高基准」两个保比例候选**精确匹配**，命中即原样生效
  （UI 显示什么，图纸就是什么）。历史根因：引擎 `int()` 截断 + 固定按较宽侧重算，
  与 UI 的 `rounded()` 联动值差 1（160 组合实测 68 组不一致，如 4:3 图输入宽 40 →
  UI 显示 40×30、引擎出 40×29）。
- 未命中（模糊请求，如旧客户端直接传任意值）保持旧语义：原始比例=宽基准、等比完整=min scale。

比例联动规则（`core.models.link_dimensions`，Tk 与 Swift 对齐）：
- **双向实时联动**：改宽 → 高逐键跟随；改高 → 宽逐键跟随
  （Tk 版 KeyRelease 绑定；Swift 版 NSTextField 桥接，绕过 SwiftUI TextField
  在 macOS 上「程序化绑定不重绘其他字段」的缺陷）
- 原始比例/等比完整按源图像素比联动（无图时按 1:1 兜底联动——改一侧另一侧必须动）
- 半输入/清空不联动（两侧均为合法整数才联动）；程序写入的联动回声不覆盖 `lastEditedDim`，
  生成前固定比例按 `lastEditedDim` 自动联动兜底

## 5. 测试策略

| 套件 | 覆盖 | 命令 |
|---|---|---|
| `tests/run_tests.py` | 引擎管线/色卡(Lab)/模板/BOM/PDF/特效/协议/模型/服务/WYSIWYG 联动 | `conda run -n pindou python tests/run_tests.py` |
| `tests/gui_smoke.py` | Tk 版全流程（面板/实时联动/队列/撤销/拖动/持久化/内存） | `conda run -n pindou python tests/gui_smoke.py` |
| `app/` swift test | Swift VM + 引擎协议 + 网格/特效回归 | `cd app && swift test` |

约定：

- **测试门禁**：各套件全绿才可交付；不采信口头结果，必须由执行者独立跑出绿。
- **套件不可并发跑**：swift test 会起真实引擎子进程写共享 `output/` 并触发裁剪，
  与 run_tests 并发会互相删掉对方的中间产物（实测 2 项假失败）。必须顺序执行。
- gui_smoke 全程零弹窗零交互（打桩 filedialog/messagebox）；Tk 合成 `event_generate`
  KeyRelease 不触发 widget 绑定，实时联动用例直调 `settings_panel._on_key_release`。
- 测试数据隔离：`HistoryManager(file_path=...)`、临时目录；不得污染仓库根目录的
  `history.json` / `app_settings.json` / `queue_state.json`。
  **2026-10-21 起**：run_tests/gui_smoke/stress_protocol 顶层将 `OUTPUT_DIR`/`TRACK_DIR`/
  `SETTINGS_FILE`/`QUEUE_FILE`/`HISTORY_FILE`/`MY_COLORS_FILE` 全部重定向到 tempdir（子进程
  通过 `engine_bootstrap.py` 注入后再 import），跑测试不再删除/改写用户 `track/` 与根 JSON；
  `core_server.py` 支持 `PERLER_*` 环境变量覆盖路径，CI/最终门禁对 `swift test` 也做零副作用校验。
- **门禁有效性边界**：4 套件共 437 项全绿只证明代码路径/结构断言；特效视觉质量、UI 外观
  与「切特效是否自动重绘」尚无自动断言（见 `qa/gates/report.md` 盲区清单）。改特效/UI 必须
  人工看前后对比图（`qa/effects/fixes/`、`qa/ui/after/`）或补视觉回归。
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

- Tk 版暂无特效面板（特效仅在 Swift 版暴露）；Tk 界面尚未做编辑杂志风重设计（Phase 4）。
- 1:1 PDF 的出血/页码为栅格绘制，拼贴效果需打印后人工确认。
- Windows 端 Tk 主题与快捷键逻辑已实现，需在 Windows 机器跑一次 gui_smoke 确认。
- 邻接描边（outline_cell）2026-10-21 已改为「相邻格 CIELAB ΔE 超阈值 + 分位自适应」：
  照片不再全图黑网，但深色低对比照片的描边可能又太弱（描边珠约 27%，含基线暗珠）；
  可调 `min_delta_e`/`percentile`/`width`。
- 线稿描边（outline_edge）改为网格尺度 DoG+滞后阈值+去孤点；对复杂照片仍是「风格化线稿」，
  不等同于人工勾线。
- 霓虹（neon）仍是 Color+Brightness 近似，未实现真正的暗底/辉光（T5 未重做，待后续）。
- 大头（chibi）依赖 OpenCV Haar 人脸检测；无脸/缺 cv2 时返回 warning 并跳过，不再静默；
  真实人脸路径仅用 monkeypatch 验证，缺真人素材回归。
- 风格色板（preset）改为保结构量化后再映射，照片不会被洗白，但仍是强风格化（用色 ≤ 预设色数）。
- 特效画廊目前无逐项实时缩略图（Phase 2，需新增 effectPreviews 协议）；现为编号卡片 + 参数 + 前后对比。
- 色卡匹配为 CIELAB（D65）感知距离：golden 基准于 2026-09-08 与 2026-10-21（outline_cell 语义变更）
  重生成（`tests/golden/update_golden.py --matrix`），再改匹配/特效算法需同步重生成。
  golden 只哈希 finished 纯珠像素区：改底色/字体/PDF 版式不会触发 golden 变化（2.6.0 已验证）。
- 生成图风格统一（2.6.0）后，中间调珠色上个别色号文字对比度可能只有 2.3–4.5:1（中位 10.7–13.25）；
  属 P3 观察项，必要时可再提高字号/描边。
- 默认网格线由历史冷灰 #C8C8C8 改为暖发丝线 #D5C4AC（新默认；显式旧值/旧设置仍兼容）。
- Tk 兜底界面本轮未做老钱风统一（用户明确暂不处理）；Tk 预览中图纸内容已是新 editorial 风格。
- XCUITest 不在 4 套交付门禁内，且需要 macOS 自动化权限；本机 `AXIsProcessTrusted=false`，
  无法自动化驱动真实 app 选图（UI 验证用真机空状态截图 + 同源码离屏 harness）。
- 缩放/平移的滚轮与双指手感依赖真实设备；自动化只能验证数学与状态渲染，触控板方向/速度手感
  需人工验收（独立验证清单见 `qa/verify/`）。
- 开始页 hero 资产由本地示例照片 + 引擎生成，未引入第三方素材；**公开发布/上架前应替换为
  明确授权的照片**（当前仅适合本地/个人使用）。
- 老钱风 UI 使用 macOS 系统字体（宋体/New York/Didot/PingFang），不打包字体；跨平台或分发包
  需引入 OFL 字体（Noto Serif SC 等）并附许可。
