# T10 独立验证报告：预览缩放/平移修复 + 老钱风棕色主题

| 项 | 值 |
|---|---|
| Shared Task | task-10（owner: view-verify，独立验证方，不修改产品代码） |
| 执行时间 | 2026-10-21 22:54–23:2x（Asia/Shanghai） |
| 仓库 / 分支 | /Users/chen/Desktop/learn/PerlerBeadApp，dev-2.0（未 commit/push） |
| 验证对象 | T8 缩放/平移修复（ui-audit，两次交付）+ T9 老钱风棕色主题 + hero（ui-audit） |
| 基线源码 | HEAD 4736fed；修复前 ContentView sha256 f90fe97e… |
| 最终源码 | 工作区 ContentView sha256 **f0953a8c…**、DesignSystem 760526d0…、AppViewModel 384db6be… |
| 环境 | macOS 27.0.1 / Swift 6.4 (swiftlang-6.4.0.34.1) / Xcode 27.1 / conda pindou 可用 |
| 写作用域 | 仅 qa/verify/**、app/Tests/PerlerAppTests/VerifyZoomPanTests.swift（产品代码零改动，见 §9） |

---

## 0. 结论摘要

| 用户主诉 | 结论 | 关键证据 |
|---|---|---|
| ① 预览「放大比例调节」失效 | **通过（修复有效）** | 常驻缩控件 + 百分比；⌘=/⌘−/⌘0 实测生效（127%/77%/复位）；zoom 25/50/100/200/400 渲染尺寸与独立计算误差 ≤0.25pt |
| ② 放大后不能移动画面 | **首版未修复 → 独立发现 P0 → 补修后通过** | 修复前：真实 ContentView 上 8 次拖拽 offset 仍 (0,0)（控制组同链路 8/8 命中）；补修后：拖拽 (60,40) 完整生效，极端拖拽被钳制在 (726,560)（与独立推导零误差） |
| T9 棕色调 / 无红绿不和谐 | **通过** | 30 组文字对比度全部 ≥4.5:1；无饱和绿色 token、无红绿并置（亮暗两套）；10 张亮暗截图实测纸底 = token 原值 |
| hero 开始页 | **通过** | 资产 2400×1333 正确加载（单测），`.aspectRatio(2400/1333, contentMode: .fit)` 等比不拉伸；亮暗截图可见 photo→beads 过渡 |
| 中文排版不截断 | **通过（视觉走查）** | 1280×800 / 1440×900 亮暗、开始页/工作台/画廊/色卡逐屏检查无截断/重叠 |
| 单测 / 构建回归 | **通过** | swift test **110/110**（基线 84 → T8 +10、T9 +1、T10 独立 +15），swift build 通过 |

**R1（滚轮/双指锚点镜像）已按建议修复并追加复验通过**（isFlipped=true + 16pt 换算，实测锚点不再镜像，详见 §11）；无未修复功能项。

---

## 1. 验证方法（可复跑）

| 层级 | 手段 | 位置 |
|---|---|---|
| 静态审计 | 逐行审计缩放控件/事件接线/几何数学；grep 全文件 scrollWheel/magnify/gesture | §3、§4.1 |
| 离屏 harness | 复制产品源码（仅注入 @StateObject→@ObservedObject + Engine 路径），真实 ContentView + 注入已驱动 AppViewModel，1280×800 窗口，2x 截图 + 像素级测量 | `qa/verify/harness/`（`prepare_sources.sh HEAD/WORKTREE`） |
| 渲染测量 | 合成 600×450 洋红图（中心 4×4 青色标记）：截图中测洋红包围盒 = 实际渲染像素尺寸/位置，与独立几何期望对比 | `RenderProbe` / `pre_probe_baseline.json` / `post_probe_final.json` |
| 真实图纸 | 真实引擎产物 `qa/ui/assets/eagle_chart.png`（1760×2048 降采样态）注入渲染，核对产品 previewSize 与截图 | `RealChartProbe` |
| 事件接线 | 合成 NSEvent 经 `NSApp.postEvent` 进入真实 app 事件循环（合成鼠标/键盘已验证可驱动 SwiftUI）；键盘/拖拽为真实手势链路 | `EventProbe` |
| 手势根因复现 | 同一窗口四象限复现产品 plate 的修饰符结构（单 gesture vs 双 gesture 叠加） | `GestureRepro` |
| 主题数值 | 解析 DesignSystem tokens → WCAG 对比度 + HSV 红绿带扫描 | `qa/verify/tools/theme_audit.py` → `theme_tokens.json` |
| 主题截图 | 真实 ContentView / EffectsGalleryView / ColorChartView 亮暗截图 + 平色采样 | `ThemeProbe` → `theme_probe.json` |
| 真实交互自动化 | 权限探测：`AXIsProcessTrusted()=false`、System Events「UI elements enabled=false」→ XCUITest/AX UI 脚本不可用，转人工清单 | §6 |

复跑命令：
```bash
cd qa/verify/harness
./prepare_sources.sh WORKTREE          # 或 HEAD（修复前基线）
swift build --disable-sandbox
PERLER_REPO_ROOT=../.. ./.build/debug/ZoomProbe post    # 缩放/平移/事件
PERLER_REPO_ROOT=../.. ./.build/debug/ZoomProbe theme   # 主题截图（需 conda pindou）
cd ../../.. && python3 qa/verify/tools/theme_audit.py
cd app && swift test --disable-sandbox
```

---

## 2. 修复前基线复现（HEAD 4736fed，ContentView f90fe97e…）

### 2.1 静态代码事实（HEAD）

- 缩放滑杆只在 `!vm.fitToWindow` 时渲染（旧 ContentView.swift:461-464），默认 `fitToWindow=true` → 首屏没有任何比例调节；唯一出口是「适应窗口」按钮（同时是状态指示，语义反直觉）。
- 全文件 grep 无 `scrollWheel` / `magnify` / `onContinuousHover` / 任何滚轮事件实现；但界面写死两处「滚轮缩放」提示（旧 :602、:631）→ 文案与行为不一致。
- 无 ⌘+/⌘−/⌘0 快捷键（PerlerApp.swift commands 只有空 newItem）。
- `.position(x: 中心 + vm.offset)` 渲染链路本身可用；但 `AppViewModel.dragChanged/Ended`（旧 :817-824）无任何钳制，可把画面拖丢。
- plate 手势为两个 `.gesture` 叠加：`.gesture(dragGesture, including: editMode ? .none : .all)` 后接 `.gesture(editGesture, including: editMode ? .all : .none)`（旧 :515-516）。

### 2.2 状态注入渲染复现（修复前，harness 实测）

渲染数学本身正确（说明问题不在绘制而在控件/事件）：

| 状态 | 期望显示尺寸(pt) | 实测 | 误差 |
|---|---|---|---|
| fit | 612×459 | 612×459 | 0 |
| zoom 25% | 150×112.5 | 150×112.5 | 0 |
| zoom 50% | 300×225 | 300×225 | 0 |
| zoom 100% | 600×450 | 600×450 | 0 |
| zoom 200% / 400% | 1200×900 / 2400×1800 | 裁剪后 644×526（=plate 尺寸） | 0（裁剪边界正确） |
| offset (80,60) @50% | 包围盒中心偏移 (80,60) | (80,60) | 0 |
| 直接注入 offset=(9999,9999) | 期望（无钳制）图完全移出 | 洋红像素 **0**（图彻底消失） | — |

### 2.3 事件级复现（这是「② 不能移动」的直接证据）

- 控制组（同进程普通 SwiftUI DragGesture）：8 次拖拽 → `drag_hits=8`，translation=(80,40)。**证明合成鼠标事件可驱动 SwiftUI 手势，链路可用。**
- 产品 plate（zoom=200，点在 plate 中心拖拽）：8 次 leftMouseDown / 49 次 leftMouseDragged 均已到达 app（本地监视器计数），但 **vm.offset 始终 (0,0)**；fit 模式同样 (0,0)。
- 根因最小复现（同一窗口 4 象限，仅手势结构不同，各拖拽一次）：
  | 变体 | 手势结构 | 命中次数 |
  |---|---|---|
  | A | 仅 `.gesture(drag, .all)` | **6** |
  | B | `.gesture(drag,.all)` + `.gesture(tap,.none)`（产品结构） | **0** |
  | C | B + `.onTapGesture(count:2)` | **0** |
  | D | C + `.onDrop`（最接近产品 plate） | **0** |
  → **双层 `.gesture` 中第二层 mask=`.none` 会吞掉内层 dragGesture**；因此基线非编辑模式下拖拽手势根本没有被安装，`dragChanged` 永不被调用。（T8 首版仍保留该结构，故首版复验 ② 仍为 0，已独立上报 Lead/ui-audit 并补修。）
- 键盘：⌘= 后 zoom 仍 100、fit 仍 true（无快捷键）。
- 滚轮：合成 scrollWheel 事件到达 app 监视器（计数 2）但 zoom 不变（无处理器）；另注：由 CGEvent 构造的 scrollWheel NSEvent 无法关联窗口（AppKit 限制），对「按 event.window 过滤」的处理器不可作为否定证据（见 §7 R2）。

**根因判定**
1. ①「比例调节失效」= 缩放控件被 `!fitToWindow` 条件隐藏 + 无滚轮/双指/快捷键事件实现 + 百分比标签 fit 时写死 100% + 提示文案造假。
2. ②「放大后不能移动」= plate 两个 `.gesture` 叠加，非编辑模式外层 `editGesture(including: .none)` 使内层 `dragGesture` 完全失效（事件到达 app 但产品手势未收到）；此外无 offset 钳制、无滚轮/双指平移。

---

## 3. 修复后验证：缩放（①）

### 3.1 控件与文案（静态 + 截图）

- 常驻控件（ContentView.swift:453-500）：− / Slider(25…400) / ＋ / 百分比 / 适应窗口 / 重置视图；compact 布局保留 − ＋ 百分比。
- 百分比按真实比例显示：fit 时 `fittedZoomPercent` 返回真实值（实测工作台 23%，非写死 100%），且不受手动下限 25% 影响（独立单测 `testFittedZoomPercentReportsRealRatioBelowManualMin` 断言 20.56%）。
- 文案改为「拖拽平移 · 滚轮 / 双指缩放 · ⌘+ / ⌘− / ⌘0」「滚轮 / 双指缩放 · 双击居中」，与实现一致（截图 §5.3）。
- 滚轮/双指/键盘事件接线代码存在且非空实现：`PreviewInputCatcher`（ContentView.swift:1960+，NSViewRepresentable + `NSEvent.addLocalMonitorForEvents([.scrollWheel,.magnify])`），`handleWheelZoom / handleTwoFingerPan / applyZoom` 真实驱动 vm 状态。

### 3.2 渲染像素测量（修复后，与修复前渲染层一致，作为「比例真的变了」的客观证据）

| 状态 | 期望显示尺寸(pt) | 实测包围盒(pt) | 误差(pt) | 中心标记反算 scale |
|---|---|---|---|---|
| fit | 612×459 | 612×459 | 0 | 1.00 |
| 25% | 150×112.5 | 150×112.5 | ≤0.25 | — |
| 50% | 300×225 | 300×225 | 0 | — |
| 100% | 600×450 | 600×450 | 0 | 1.00 |
| 200% | 1200×900（裁剪） | 644×522（=plate） | 0 | 2.00 |
| 400% | 2400×1800（裁剪） | 644×522（=plate） | 0 | 3.75* |
| offset (80,60) @50% | 中心偏移 (80,60) | (80,60) | 0 | — |

\* 400% 的标记反算 3.75 是 4px 标记在 2x 截图下的量化下限（期望 4.0），非产品误差；200% 处为 2.00 精确。

真实图纸（eagle_chart 1760×2048）注入：产品 `previewSize` 与独立公式完全一致——fit 421.15×490（23.93%）、25% 440×512、50% 880.1×1024、100% 1760.2×2048（误差 0）。

### 3.3 快捷键与事件链（修复后实测）

| 操作（合成事件，真实 app 事件循环） | 修复前 | 修复后 | 判定 |
|---|---|---|---|
| ⌘= | zoom 100 / fit true（无反应） | zoom **127**、fit=false | PASS |
| ⌘− | 无反应 | zoom **77**、fit=false | PASS |
| ⌘0（先置 300%/offset(60,40)） | 无反应 | fit=true、offset (0,0)、zoom 100 | PASS |
| EventCatcherView 存在性 | 无 | 找到，bounds **644×522**（铺满 plate），hitTest=nil（不挡点击） | PASS |
| onZoom 闭包链（模拟滚轮 factor=1.25 @200%） | 无 | zoom **200→250**，offset (0,0) | PASS（链路） |
| onPan 闭包链（模拟双指 delta(40,20) @200%） | 无 | offset (0,0)→**(40,20)** | PASS（链路） |

> 注：滚轮/双指「真实硬件事件 → 处理器」这一段无法在本机自动化（见 §7 R2），但已证明处理器注册、view 覆盖范围、闭包到 vm 状态整条链路可用；真实滚轮/触控板行为列入人工验收清单 §6。

### 3.4 平移与钳制（修复后，真实 DragGesture 链路）

| 用例 | 期望（独立推导） | 实测 | 判定 |
|---|---|---|---|
| zoom=200，拖拽 +(60,40) | offset=(60,40) | **(60,40)** | PASS |
| zoom=200，连续 5 次极端拖拽 (400,400) | 钳制边界 x=+726、y=+560（`lower/upper = ±(v/2+i/2−0.15i)`，v=612×490，i=1200×900） | **(726,560)**，零误差 | PASS |
| 极端拖拽后可见比例 | 每轴 ≥15% | 横向 16.3%、纵向 16.8%（截图 `post_event_drag_extreme.png`） | PASS |
| fit 模式拖拽（600×450 图 @fit=102%） | 切出手动模式；图片完全适配视口 → 居中 clamp offset=0 | fit=false、zoom=102、offset=(0,0) | PASS（符合设计：fit 下无平移空间） |
| 直接状态注入 offset=9999（绕过处理器） | 图移出（harness 注入不经 clamp，非产品路径） | 洋红 0 px | 说明：钳制在事件路径上验证（上两行） |

### 3.5 单测 / 构建回归

- `cd app && swift build --disable-sandbox`：**Build complete**。
- `cd app && swift test --disable-sandbox`：**Executed 110 tests, with 0 failures**（耗时 41.8s）。
  - 基线 84 项全部保留通过；T8 新增 `ZoomPanTests` 10 项通过；T9 新增 `AssetTests` 1 项通过；T10 独立新增 `VerifyZoomPanTests` 15 项通过（期望值独立几何推导：线性缩放、fit 适配、15% 钳制边界 726/560、锚点不变量、退化输入、VM previewSize）。
  - 计数核对：84 + 10 + 1 + 15 = 110，无删除/弱化既有用例（逐文件 diff 确认仅新增）。

---

## 4. 主题验证（T9）

### 4.1 色板 tokens（DesignSystem.swift:41-56，亮/暗成对）

| token | 亮色 | 暗色 | HSV(h,s,v) 亮 / 暗 | 说明 |
|---|---|---|---|---|
| paper | #F4EDE1 | #17120D | 39°/0.08/0.96 · 34°/0.43/0.09 | 暖羊皮纸 |
| paperDeep | #EBE1D2 | #1E1811 | 39°/0.11/0.92 · 35°/0.43/0.12 | 面板纸 |
| ink | #2A2118 | #F0E7D8 | 26°/0.43/0.16 · 40°/0.10/0.94 | 深咖墨 |
| accent | #8A5A33 | #C99B63 | **26°/0.63/0.54 · 32°/0.51/0.79** | 干邑/黄铜（替代原朱红 #B03D25） |
| success | #6E6547 | #A79B72 | 49°/0.36/0.43 · 45°/0.32/0.65 | 橄榄褐/青铜（替代原绿 #3E6B4F） |
| warning | #8C6314 | #C9973F | 40°/0.86/0.55 · 36°/0.69/0.79 | 琥珀 |
| danger | #7E3B2C | #C07A63 | 13°/0.65/0.49 · 12°/0.48/0.75 | 牛血红（暗红棕，非饱和朱红） |

**红绿检查**：亮/暗两套 token 均**无饱和绿色**（green band 命中 = 空）；红色带仅 danger（暗牛血红 h=13.6°/v=0.49，低明度红棕），与任何绿色不同时出现 → `red_green_coexist=false`。全 DesignSystem.swift 十六进制扫描：红带仅 #7E3B2C、绿带 **0** 个。
说明：模板缩略图（四叶草绿/爱心红/彩虹）与色卡色块是**内容本身**（真实模板/色板），不属于 UI 语义色；UI chrome（强调线、状态点、按钮、进度条、开关）已全部棕色化（截图 §5）。

### 4.2 对比度实测（WCAG 2.1，`qa/verify/evidence/theme_tokens.json`）

正文/次要文字全部 ≥4.5:1；关键值：

| 前景/背景 | 亮色 | 暗色 | 要求 |
|---|---|---|---|
| ink / paper（正文） | **13.58:1** | **15.17:1** | ✓ |
| inkSoft / paper（次要） | 8.72:1 | 9.68:1 | ✓ |
| inkMuted / paper（弱化） | 5.12:1 | 5.86:1 | ✓ |
| inkMuted / paperDeep（弱化 on 面板） | 4.61:1 | 5.54:1 | ✓ |
| accent / paper（强调文字） | 5.03:1 | 7.40:1 | ✓ |
| paper / accent（按钮文字，填充按钮） | 5.03:1 | 7.40:1 | ✓ |
| warning / paper | 4.62:1 | 7.07:1 | ✓ |
| danger / paper | 7.08:1 | 5.50:1 | ✓ |
| success / paper（状态点/小字） | 4.99:1 | 6.71:1 | ✓（≥3） |

- 装饰性发丝线 `hairlineStrong` 对比度 2.08:1（亮）/1.93:1（暗）——纯装饰分隔线，WCAG 非文本对比度 3:1 不适用于纯装饰，记录数值不作为不通过项（若需严格可用 hairline 更深一档）。
- 32 组配对中 30 组通过文字标准，2 组为装饰线（豁免）。

### 4.3 亮/暗截图走查 + 像素采样（10 张）

采样点（窗口左上角 6,6 纸底；底部 6,H−8 状态条/面板底）实测与 token 原值**逐位一致**：

| 截图 | 纸底采样 | 结果 |
|---|---|---|
| theme_cover_light_1280x800 / 1440x900 | #F4EDE1 | = Tok.paper 亮 ✓ |
| theme_cover_dark_1280x800 / 1440x900 | #17120D | = Tok.paper 暗 ✓ |
| theme_workbench_light / dark | #F4EDE1 / #17120D | ✓ |
| theme_gallery_light / dark | #F4EDE1 / #17120D | ✓ |
| theme_colorschart_light / dark | #F4EDE1 / #17120D | ✓ |

亮暗双主题视觉走查（逐图人工检查 + 像素采样）：
- 开始页（1280×800 / 1440×900、亮/暗）：双发丝线报头 + brass 渐变宋体大标题「从一张照片，到 3,600 颗豆。」；hero 图版双框线 + CropMarks + 图注 PLATE 00 · FROM PHOTOGRAPH TO BEAD；右侧示例图版/快捷键/输出面板；主操作「选择图片…」保留。**暗色下正文/标题/图注均清晰**。
- 工作台：PLATE 01 / FIG.01 / 编号章节 / 发丝线 / 三栏；缩控件与状态条棕色化；亮暗均无红绿。
- 特效画廊：分组编号卡片（01 描边与线稿…05 构图与主体）、开关为棕色系；亮暗统一。
- 色卡：A/B 分组、搜索框、状态条；chrome 棕色系；色块为真实色板内容。
- 中文排版：上述 1280×800 与 1440×900 下标题/正文/图注/按钮/状态条均无截断、无重叠、无省略号；长句「拖拽平移 · 滚轮 / 双指缩放 · ⌘+ / ⌘− / ⌘0」在 1280 宽下完整显示。

### 4.4 hero 资产

- 资产：`app/Sources/PerlerApp/Resources/hero_photo_to_beads.jpg`，**2400×1333**（宽高比 1.8004）。
- 加载链：`EditorialAssets.heroPhotoToBeads`（PERLER_HERO_PATH → Bundle.module → Bundle.main → 源码树回退），`AssetTests.testHeroAssetLoads` 断言加载成功且比例 0.02 容差内 **PASS**。
- 不拉伸：ContentView.swift:1243-1249 `Image(nsImage:).resizable().aspectRatio(2400/1333, contentMode: .fit).frame(width: 520)` → 等比 fit，**结构上不可能拉伸**；截图（亮/暗）中 photo→beads 渐变过渡自然、无变形。
- 降级：资产缺失时显示同尺寸占位（Rectangle + Fleuron + PLATE 00），不会布局跳动。

---

## 5. 关键证据图（qa/verify/evidence/）

| 图 | 说明 |
|---|---|
| `theme_cover_light_1280x800.png` / `theme_cover_dark_1280x800.png` | 开始页亮/暗 + hero + 棕色主题 |
| `theme_workbench_light_1280x800.png` / `theme_workbench_dark_1280x800.png` | 工作台内容态亮/暗 + 常驻缩控件（− 滑杆 + 23% 适应窗口 重置） |
| `theme_gallery_light.png` / `theme_colorschart_dark.png` | 画廊/色卡亮暗（其余见目录） |
| `pre_event_drag_extreme.png` / `post_event_drag_extreme.png` | 修复前：极端拖拽后仍居中（offset 0，拖不动）；修复后：拖到钳制边界保留 15% 画面 |
| `post_05_zoom_200.png` / `post_06_zoom_400.png` | 200%/400% 实际渲染（裁剪边界 = plate，线性缩放已由测量表给出） |
| `post_real_01_fit.png` … `post_real_05_zoom_50_offset_40_30.png` | 真实引擎图纸在 fit/25/50/100% 与偏移下的渲染 |

数据文件：`pre_probe_baseline.json`、`post_probe_final.json`（渲染/真实图纸/手势复现/事件全部原始数值）、`theme_tokens.json`、`theme_probe.json`、`baseline_source_hashes.txt`。
harness 源码：`qa/verify/harness/`（prepare_sources.sh + RenderProbe/EventProbe/GestureRepro/RealChartProbe/ThemeProbe）。

---

## 6. 无法自动化的项 + 人工验收清单

**自动化权限实测**：`AXIsProcessTrusted()=false`；`osascript -e 'tell application "System Events" to get UI elements enabled'` → **false**。因此 XCUITest / AppleScript UI 脚本 / 合成 CGEvent 到真实 app 均不可用（本报告所有事件证据都来自「同一份产品源码 + 进程内真实 NSEvent 派发」的离屏 harness，非 AX 自动化）。未安装 xcodegen、未新建 Xcode UI Test target（Lead 指示不为此花时间）。

人工验收清单（约 5 分钟，建议真机触控板 + 鼠标各一遍）：
1. **触控板双指捏合**：光标位于预览图非中心位置，捏合放大 → 图应放大且光标下内容尽量不动；缩到最小 25%、最大 400%。【唯一完全未自动化的硬件事件；若发现异常重点看锚点偏移，见 R1】
2. **鼠标滚轮**：预览图上滚轮 → 缩放（每格约 ±6%，上限 400%/下限 25%）；按住 ⌘ 或 ⌥ 滚轮同样缩放；缩放后百分比标签与状态条数值一致。
3. **触控板双指滚动（无修饰键）**：放大到 200% 后在图上双指滑动 → 画面平移且不会拖丢（拖到极限仍保留 ≥15% 画面）。
4. **拖拽平移**：任意缩放级别（25%…400%）拖动图片均跟随鼠标；光标为手型；双击居中；「重置视图」按钮（↺）与 ⌘0 恢复适应窗口。
5. **滑杆 / − ＋ 按钮**：拖动滑杆百分比实时变化；− ＋ 每次 ±25%；百分比标签随 fit 显示真实比例（真实图纸约 23%）。
6. **编辑模式回归**：开启编辑模式后点击格子换色仍准确（拖拽被有意禁用）；关闭后恢复拖拽。
7. **亮暗外观**：系统切换浅色/深色（或启动时 PERLER_APPEARANCE=light|dark）逐屏检查开始页/工作台/画廊/色卡无红绿强调色、文字可读。
8. **hero**：开始页大图版在不同窗口宽度（1100/1280/1440）下等比显示、无拉伸；无图片资产时占位不跳动。
9. **真实拖拽边界**：把图拖到四个角极限，确认每一轴都保留约 15% 画面（自动化已在 harness 用真实手势链路验证 (726,560) 边界，人工复核体感即可）。

---

## 7. 残余风险 / 已知问题

| # | 级别 | 问题 | 证据 | 建议 |
|---|---|---|---|---|
| R1 | **已修复（§11 复验通过）** | 滚轮/双指缩放的**锚点 y 轴镜像**：`EventCatcherView` 用 `convert(event.locationInWindow, from: nil)`（NSView 左下原点，`isFlipped=false`）得到点，直接传给 `applyZoom(anchor:)`（按 SwiftUI 左上原点解释）；且 plate 边界 644×522 与 GeometryReader 视口 612×490 相差 16pt padding。结果：光标不在垂直中心时，滚轮缩放锚定到上下镜像的位置（水平 x 正确）。 | 闭包实测：anchor=(183.6,343)（视口 612×490）@100%→200% 后 vm.offset=(122.4,−98)；若按左上坐标语义应为 (122.4,+98)。 | 在 handler 内把点换算为视口坐标：`vx = p.x − 16; vy = viewport.height + 16 − p.y`（或 `override var isFlipped: Bool { true }` 并扣除 padding）。P3：不影响居中缩放与功能可用性。 |
| R2 | 记录 | 滚轮/双指真实硬件事件未能自动化：AX 权限不可用；CGEvent 合成的 scrollWheel NSEvent 无法关联窗口（`event.window=nil`），按 `event.window` 过滤的处理器收不到（已实测 synthetic_window=false）。 | post_probe_final.json `wheel_zoom.post` / `two_finger_pan.post` | 已用「本地监视器收到事件 + view 覆盖 plate 644×522 + onZoom/onPan 闭包链驱动 vm」三段式验证替代；真实行为列入人工清单 1-3。 |
| R3 | P3（低） | 极小图片（fit 比例 >400%）时 `fittedZoomPercent` 返回可 >400%，百分比标签可能显示 >400% 而滑杆范围 25…400（拖动即被 clamp 到 400，出现一次跳变）。真实图纸/照片（≥数百 px）不会触发。 | 代码审计 ContentView.swift:1921-1927（无上限钳制） | 若需要可对展示值 `min(400, …)`，但会牺牲「fit 真实比例」的真实性；现有真实素材不触发，记录即可。 |
| R4 | 记录 | 装饰发丝线 hairlineStrong 对比度 2.08:1 / 1.93:1（低于非文本 3:1），属纯装饰线（WCAG 豁免）；若要求更清晰的装帧框线可换更深一档。 | theme_tokens.json contrast 表 | 可选优化，不影响可读性（相邻正文对比度均 ≥4.5:1）。 |
| R5 | 记录 | 模板缩略图为真实内容（四叶草绿/爱心红/彩虹），在开始页右栏仍可见饱和红绿；UI chrome 已无红绿。 | theme_cover_light 截图 | 若用户仍觉得不和谐，可对缩略图做低饱和处理（属产品决策，非缺陷）。 |
| R6 | 记录 | 鼠标滚轮（非精确滚动）默认直接缩放（无需修饰键），是「滚轮缩放」文案要求的行为；触控板双指滚动才平移。与部分用户习惯不同，但符合任务书与现有文案。 | 代码审计 PreviewInputCatcher scrollWheel 分支 | 如用户反馈误触可加「仅 ⌘+滚轮缩放」开关。 |
| R7 | 记录 | 状态注入 harness 直接写 vm.offset 时不经过 clamp（产品只在手势/几何变化时 clamp）。因此「直接注入 offset=9999 会把图移出」不是产品路径缺陷，钳制已在真实拖拽链路验证。 | §2.2 / §3.4 | harness 使用说明，无产品改动必要。 |

---

## 8. 通过 / 不通过项汇总

**通过（PASS）**
1. 缩放控件常驻（− 滑杆 ＋ % 适应窗口 重置），任意缩放交互切出手动模式；⌘= / ⌘− / ⌘0 生效；百分比 fit 真实（23%）。
2. 缩放渲染数学：25/50/100/200/400% 实际渲染尺寸与独立计算误差 ≤0.25pt；真实图纸 previewSize 与公式完全一致。
3. 拖拽平移在 fit→手动/200% 下生效（offset 精确）；极端拖拽钳制 (726,560) 与独立推导零误差、每轴保留 16.3%/16.8% 可见。
4. 滚轮/双指处理器存在且整条闭包→vm 链路可用（真实硬件事件见人工清单）。
5. 修复未破坏编辑模式点击换色：plate 手势按 vm.editMode 互斥分组（编辑=editGesture，普通=dragGesture），编辑模式下 handlePreviewTap 坐标换算未改动；静态审计确认拖拽在编辑模式被有意禁用。
6. 单测 110/110、build 通过、既有 84 项零破坏。
7. T9 棕色 tokens：无饱和绿、无红绿并置；正文/次要/按钮对比度全部 ≥4.5:1；亮暗渲染采样与 token 逐位一致。
8. hero 资产 2400×1333 正确加载、等比 fit 不拉伸、亮暗显示正常；中文排版无截断。
9. 画廊/色卡/状态条与工作台同一套 tokens；亮暗双主题逐屏一致。

**不通过 / 未通过自动化**
- 无功能级不通过项。
- 无法自动化项：真实触控板捏合/双指滚动/鼠标滚轮/滑杆拖拽（AX 权限不可用），已给出人工验收清单 §6。
- 观察项：R3/R4/R5/R6 记录项；R1（锚点镜像）已修复并复验通过（§11）。

---

## 9. 约束遵守与交付边界

- **未修改产品代码**：`git status` 中对 `app/Sources/PerlerApp/*` 的修改全部来自 ui-audit（T8/T9）；本任务仅新增 `app/Tests/PerlerAppTests/VerifyZoomPanTests.swift`（测试）与 `qa/verify/**`（harness/证据/报告/工具）。
- 未 commit/push/checkout；未清理 output/、track/；未引入第三方依赖（harness 只用系统 SwiftUI/AppKit；主题审计用标准库 python3）。
- 未使用外部不可信内容作为指令；未下载依赖到产品。

## 10. 验证时间线

| 时间 | 事件 |
|---|---|
| 22:54 | claim task-10；快照 HEAD 基线源码 hash |
| 23:01–23:12 | 修复前基线：离屏 harness 搭建、渲染/事件/根因复现（① 确认、② 确认失效） |
| 23:13 | T8/T9 completed；对首版修复复验 → **② 仍为 0 位移**，P0 上报 Lead + ui-audit（含最小复现与修法建议） |
| 23:16 | ui-audit 改为单一条件手势并复验；view-verify 开始 T9 主题取证 |
| 23:17–23:19 | 复验：拖拽 (60,40)/钳制 (726,560) 生效、键盘/T9/主题全部验证；swift test 110/110 |
| 23:2x | 报告落盘、complete task-10 |

---

## 11. 追加复验：R1 滚轮/双指锚点 y 轴镜像（23:2x，时间盒内定向复验）

**修复内容（ui-audit，ContentView.swift / PreviewInputCatcher）**：
1. `EventCatcherView` 增加 `override var isFlipped: Bool { true }` → NSView 本地坐标改为左上原点，与 SwiftUI 预览视口一致；
2. 新增 `PreviewViewport.viewportPoint(fromPlatePoint:inset:)`：monitor 内把 644×522 图版坐标 (x−16, y−16) 映射为 612×490 视口坐标（扣除 `previewImage.padding(16)`）；
3. `scrollWheel` / `magnify` 的 delta 方向未改动。

**复验方法**：`qa/verify/harness` 新增 `anchor` 模式（`AnchorProbe.swift`），真实 ContentView + 注入 VM + 找事件捕获视图，验证「isFlipped 属性 / 换算纯函数 / 闭包锚点语义」三段；原始数据 `qa/verify/evidence/anchor_probe.json`，截图 `anchor_anchor2_before.png` / `anchor_anchor2_after.png`。

| 断言 | 实测 | 判定 |
|---|---|---|
| `EventCatcherView.isFlipped` | **true** | PASS（坐标系与 SwiftUI 一致） |
| `inset` 参数 | 16（= previewImage padding） | PASS |
| `viewportPoint` 换算（4 个代表点：图版左上 (0,0)→(−16,−16)、视口原点 (16,16)→(0,0)、中心 (322,261)→(306,245)、光标 20% 高位 (193.2,104.4)→(177.2,88.4)） | 与独立期望 `(x−16, y−16)` **误差全部 0** | PASS |
| 闭包锚点语义：onZoom(2.0, 视口锚点 (177.2, 88.4)) @100%→200% | 期望 offset (128.8, **+156.6**)（独立公式 `(a−c)−((a−c)−0)×2`）；实测 **= (128.8, +156.6)，零误差**；y 为正（锚点在上半部→图像下移） | PASS（镜像已消除） |
| 镜像 bug 反事实值 | 若仍按底部原点解释，同一点 y 应得 **−156.6**（实测为 +156.6） | 负值未出现 |

**结论**：R1 **已修复**。修法与我报告中的建议一致（isFlipped 或 y 换算，二者均落地，padding 也正确扣除）；闭包链路数值与独立推导完全一致。真实滚轮/触控板硬件事件仍受 R2 限制（AX 权限不可用、合成 scrollWheel 无法关联窗口），**待人工滚轮验收**：在预览图上半部滚轮放大，观察光标下内容尽量不动（不再跳向下方镜像位置）。

**回归影响**：R1 改动仅涉及事件坐标换算（isFlipped + 纯函数），不改缩放/平移渲染数学与手势分组；ui-audit 侧 swift test 111/111、dragcheck PASS。本次时间盒内定向复跑 T10 独立测试：`cd app && swift test --disable-sandbox --filter VerifyZoomPanTests` → **Executed 15 tests, 0 failures**（23:26:13），未重跑全量。
