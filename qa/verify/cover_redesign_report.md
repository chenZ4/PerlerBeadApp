# T13 独立验证报告：开始页改版（去示例面板 + 左侧整块 hero）

| 项 | 值 |
|---|---|
| Task | task-13（owner: view-verify；T13 独立验证，不修改产品代码） |
| 验证对象 | T12 开始页改版（ui-audit）：删除示例图版面板 + 左侧整块背景大图 + 右侧文案/操作列 |
| 源码状态 | 工作区 ContentView.swift sha256 0d25bf37259a…（2026-10-21 23:35:49，T12 最终版）；DesignSystem 760526d0…（T10 后未再改） |
| 环境 | macOS 27.0.1 / Swift 6.4 / Xcode 27.1；屏幕 1470×956，可见区 1470×861（1440×900 的真实窗口会被系统压到 834–861pt，1440×900 场景改用离屏精确尺寸渲染，见 §9） |
| 方法 | 复用 T10 离屏 harness（真实 ContentView 源码 + 注入 VM），新增 cover 探针：4 场景截图 + 定位产品发丝线测量版心 + OCR 文本核对 + 工作台/画廊像素 diff |
| 写作用域 | qa/verify/**（产品代码零改动；未 commit/push） |

---

## 0. 结论摘要

| 检查项 | 结论 | 关键量化证据 |
|---|---|---|
| ① 示例面板/彩色缩略图彻底移除 | **PASS** | 封面 OCR 无「示例图版/四叶草/小幽灵/彩虹/笑脸/SAMPLES/CATALOGUE」；四场景 hero 以外区域彩色像素 = 0（对比 T10 旧封面右栏 486 px）；ContentView 已无 TemplateThumb 引用 |
| ② 左侧 hero 真正铺满 | **PASS** | 1280×800：hero = 879×682.5pt（窗口宽 68.7%、内容区高 100%），左/上/下贴边（0/79/761.5）；四边图像活性 99.2–100%，hero 内纸底残留 0.07%，非「框住小图」；1440×900 离屏：1026×785.5（71.25% 宽、100% 高）、纸底残留 0.26% |
| ② scaledToFill 无变形 | **PASS** | 代码审计 .resizable().aspectRatio(contentMode: .fill).frame(maxWidth:.infinity,maxHeight:.infinity).clipped() = 结构性等比裁切，不可能拉伸；截图鹰眼/网格比例自然 |
| ③ 图注/scrim 可读性 | **PASS** | 图注文字带（左下 y≈689–732）近似对比度 7.16:1（1280）/ 6.93:1（1440）；scrim 使图注区背景亮度 = hero 中部的 6.7%（1280）/ 12.5%（1440）→ 渐隐 scrim 生效、文字清晰 |
| ④ 主 CTA 首屏可见 | **PASS** | OCR 命中「选择图片⋯」bbox (976.4, 315.0, 77.0×18.0)pt，完全在 1280×800 首屏内；「或拖入图片 · ⌘O」提示同时可见 |
| ⑤ 快捷键/输出表无截断 | **PASS**（附 P2 观察） | OCR 命中 打开图片/生成图纸/对比原图/按住按钮/PNG 图纸/3670×4270/MARD 221；裁剪放大目检「缩放 / 重置」「PDF A4 / 1:1 实物」「色卡 MARD 221 · 4 套」完整；OCR 无异常省略号。P2 右内边距压缩问题已修复（修复前 0–18.5pt → 修复后 30.0–30.5pt，见 §9.1），文字无截断 |
| ⑥ 工作台/画廊未被破坏 | **PASS** | 与 T10 期截图逐像素对比：工作台 changed_fraction 0.0081%（mean 0.008）、画廊 0%（完全一致） |
| ⑦ swift test 全绿 / 总数 | **PASS** | swift build 通过；swift test Executed 111 tests, 0 failures（Lead 删除旧横向 hero 资产/用例后 AssetTests 由 2→1）；合计 249+92+12+111 = 464（T12 时点为 112/465，差异仅此一项） |

**P2（右内边距压缩）已修复并复测通过（见 §9.1）**：修复后 1280×800 竖分隔线 = 849.0pt（= 1280 − 431），右内边距恢复到 **30.0–30.5pt**；1440×900 分隔线 1009.0pt、右内边距 30–31.5pt；hero 仍铺满左侧（849×682.5 / 1009×785.5，四边图像活性 100%/99.2%，纸底残留 0.07%/0.26%），无文字截断、无回归。

---

## 1. 验证方法（可复跑）

    cd qa/verify/harness
    ./prepare_sources.sh WORKTREE && swift build --disable-sandbox
    PERLER_REPO_ROOT=../.. ./.build/debug/ZoomProbe cover      # 4 场景 + OCR + 回归 → qa/verify/evidence/cover_probe.json
    PERLER_REPO_ROOT=../.. ./.build/debug/ZoomProbe layouttest # 版心/根尺寸根因（R1 证据）
    cd ../../.. && python3 qa/verify/tools/theme_audit.py      # 主题 tokens 复核（T10 工具）

- 版心测量：不依赖视觉估猜——利用产品自身的竖分隔发丝线（hairlineStrong）与底部/顶部发丝线定位：先找「body 高度上 >80% 命中发丝线色」的竖线 = 右列左边界，再找全宽底部/顶部发丝线 = hero 上下边界；四边「图像活性」= 距边 2px 内侧采样非精确纸底比例；「纸底残留」= hero 内部精确纸底色占比。
- OCR：Vision VNRecognizeTextRequest（zh-Hans + en-US，accurate）识别 1280 light 截图，输出 bbox 与文本；用于示例面板关键词消失、CTA 首屏、快捷键/输出文本完整性、右侧越界检测。
- 1440×900：本机可见高度 861pt，真实窗口无法达到 900pt 内容高；该场景用 NSHostingView 离屏精确 1440×900 渲染（同源码）。同时保留 1280×800 真实窗口渲染（window 模式）。
- 回归：工作台（注入真实图纸）与画廊（EffectsGalleryView）与 T10 期同配置截图做逐像素 diff。

---

## 2. ① 示例面板 / 彩色缩略图彻底移除

| 证据 | 结果 |
|---|---|
| OCR 关键词（示例图版 / 示例 / SAMPLES / CATALOGUE / 内置模板 / 四叶草 / 小幽灵 / 彩虹 / 笑脸） | 全部未出现（sample_panel_texts_found = []） |
| hero 以外区域「饱和彩色像素」（S>0.55、V>0.35、排除暖棕色相）：1280 light / 1280 dark / 1440 light / 1440 dark | 0 / 0 / 0 / 0 |
| 对照：T10 旧封面右栏（示例面板区）同口径 | 486 px（旧面板彩色缩略图已不存在） |
| 代码审计 | ContentView.swift 中已无 TemplateThumb 引用；封面只保留 hero + 右侧文案/快捷键/输出列 |

结论：封面整页只剩「纸 / 墨 / 黄铜 + 老鹰图」，无任何彩色模板缩略图。✅

---

## 3. ② 左侧 hero 是否真正铺满（像素测量）

| 场景 | hero 矩形(pt) | 宽占窗口 | 高占内容区 | 左/上/下贴边误差 | 四边图像活性 L/R/T/B | hero 内纸底残留 | 框住小图? |
|---|---|---|---|---|---|---|---|
| 1280×800 light（真实窗口） | (0, 79) 879×682.5 | 68.7% | 100% | 0 / 0 / 0 pt | 99.2% / 100% / 100% / 100% | 0.07% | 否 |
| 1280×800 dark（真实窗口） | 同上 | 68.7% | 100% | 0 / 0 / 0 pt | 100% / 91.7%* / 100% / 80%* | 1.2%* | 否 |
| 1440×900 light（离屏精确） | (0, 76) 1026×785.5 | 71.25% | 100% | 0 / −3† / 0 pt | 99.2% / 99.2% / † / 100% | 0.26% | 否 |
| 1440×900 dark（离屏精确） | 同上 | 71.25% | 100% | 0 / −3† / 0 pt | 99.2% / 91.7%* / † / 81.7%* | 1.5%* | 否 |

\* 暗色下 hero 底部 scrim（#17120D 74% 渐隐）与暗色纸底 #17120D 非常接近，个别边缘像素被判为「精确纸底」→ 数值偏低；视觉检查截图确认无纸边留白（见 cover_1280x800_dark.png）。
† 1440 离屏渲染中顶部 DoubleRule 的行识别有 ±3pt 量化偏差，使顶部边缘采样落在 rule 间隙；宽度/高度/左右/底部与「无纸底」结论不受影响，视觉确认顶部为图像。

- 对照代码期望：hero 宽 = 窗口宽 − 右列(430) − 竖发丝线(1)。1280 实测 879（= 窗口 1280 − 401）但右列被压到 400（见 §9 R1）；1440 离屏实测 1026（= 1440 − 414，右列 413）——均为「左列占满、单条竖线、右列约 400–430」，符合 T12 规格「右列约 400–460pt」。
- 非框住小图：hero 内纸底残留 ≤0.26%（亮色），且四边均为图像；T10 旧封面 hero 是 520pt 宽、带 16pt 纸底边框的框住小图（旧截图 theme_cover_light_1280x800.png），现已彻底变为全幅背景。
- scaledToFill 无变形（代码审计）：ContentView.swift:75-95 Image(nsImage: hero).resizable().aspectRatio(contentMode: .fill).frame(maxWidth: .infinity, maxHeight: .infinity).clipped() → 等比填充 + 裁剪，结构性不可能拉伸；素材 2400×1800（4:3，AssetTests.testCoverHeroAssetLoads 断言比例 0.02 容差内通过）。

---

## 4. ③ 图注 / scrim 可读性

| 场景 | 图注文字带位置(pt) | 近似对比度（p95/p20 亮度） | scrim 变暗比（图注带背景 / hero 中部背景） |
|---|---|---|---|
| 1280×800 light / dark | y≈689–732（hero 左下） | 7.16 : 1 | 0.067（图注区背景亮度仅为中部 6.7% → 底部渐隐 scrim 明确生效） |
| 1440×900 light / dark | y≈789–796 | 6.93 : 1 | 0.125 |

- 图注内容（OCR 可见）：PLATE 00 · FROM PHOTOGRAPH TO BEAD / PHOTOGRAPH 清晰原片 · 保留明暗层次 / BEADS 逐级像素化 · MARD 221 映射，奶油色/黄铜色小字叠在 scrim 上，亮暗两主题均清晰；不遮挡鹰眼主体（构图目检）。
- 对比度虽以近似法（p95/p20）测得，但均远超 4.5:1；亮/暗两主题图注颜色为固定奶油色（#E8DCC8/#C9A063），背景为 scrim 压暗后的图像 → 可读性稳定。

---

## 5. ④ 主 CTA 首屏可见且可点

- OCR 命中「选择图片⋯」：bbox = (976.4, 315.0, 77.0×18.0)pt → 完全位于 1280×800 首屏内，无滚动；按钮本体为 210×40pt 的墨色填充按钮（Button("选择图片 …") { chooseImage() }）。
- 「或拖入图片 · ⌘O」拖入提示同时可见（OCR 命中「或拖入图片」）。
- 1440 场景同样在首屏内（见截图）。

---

## 6. ⑤ 快捷键 / 输出表无截断

- OCR 命中：打开图片、生成图纸、对比原图、按住按钮、PNG 图纸、3670×4270 px、MARD 221、SHORTCUTS、OUTPUT、色卡。
- OCR 未直接识别的小字行（缩放 / 重置、PDF 行）已用右侧列裁剪放大图目检验证：缩放 / 重置 ⌘+/⌘−/⌘0、PDF A4 / 1:1 实物、色卡 MARD 221 · 4 套 均完整显示，无省略号、无截断。
- OCR 全表无「…」异常截断（唯一含「⋯」的是 CTA 文案「选择图片⋯」本身，属设计文案）。
- 行高与间距：快捷键 4 行 + 输出 3 行全部落在内容区（底边距窗口 39pt 状态条之上），1280×800 无滚动。

**P2 观察**：右对齐胶囊/数值距窗口右缘仅 0–2pt（1280 harness）/ 约 18.5pt（ui-audit 真实 app 截图），设计值为 30pt → 见 §9 R1（文字未截断）。

---

## 7. ⑥ 工作台 / 画廊未被破坏

| 界面 | 与 T10 期同配置截图逐像素 diff | 结论 |
|---|---|---|
| 工作台（真实图纸内容，1280×800 light） | changed_fraction = 0.0081%，mean_abs_diff = 0.008（0–255 尺度） | 未受影响（差异为渲染抖动/亚像素） |
| 特效画廊（1180×780 light） | changed_fraction = 0%，mean_abs_diff = 0 | 完全一致 |

工作台截图亦确认图纸/缩控件/侧栏模板入口正常显示（cover_regression_workbench_light.png）。

---

## 8. ⑦ 单测 / 构建回归

- cd app && swift build --disable-sandbox → Build complete。
- cd app && swift test --disable-sandbox → Executed 111 tests, with 0 failures（T13 首轮时 112；Lead 随后删除旧横向 hero 资产与旧 AssetTests 用例，AssetTests 2→1，故当前 111）。
- 总数核对：run_tests 249 + gui_smoke 92 + stress_protocol 12 + swift test 111 = 464（与 Lead 最新口径一致；T12 时点曾为 112/465，差异仅为被删除的旧 hero 资产用例）。
- T10 的 VerifyZoomPanTests（15 项）仍全绿，未被封面改版破坏。

---

## 9. 观察项 / 残余风险

| # | 级别 | 问题 | 测量 | 建议 |
|---|---|---|---|---|
| R1 | **已修复（§9.1 复测通过）** | 封面页「固有最小宽度」> 窗口宽度，右列右内边距被压缩：hero 用 .aspectRatio(contentMode: .fill) + .frame(maxWidth/.maxHeight: .infinity) 时，SwiftUI 为图片算出「理想宽度 ≈ 内容区高 × 4/3」，使整页最小宽度 ≈ 内容区高×4/3 + 431；1280×800 时 ≈1290–1310pt → 右列 30pt 右内边距被窗口裁掉。 | 1280×800：竖分隔线在 879pt（= 1280 − 400 − 1），keyRow 发丝线/右对齐胶囊延伸至 1279.5pt（贴窗边）；真实 app 截图同口径：分隔线 861、最右内容 1261.5（右内边距 18.5pt）；layouttest：plain 根尺寸 1340.33、forced 1280 后 separator 仍 879 → 最小宽度由内部布局决定；1440×900 离屏：分隔线 1026、最右内容 1427（右内边距 13pt）。 | 让 hero 不贡献最小宽度：例如 coverHero.background(...)/.overlay 方式铺图，或对图片容器加 .frame(minWidth: 0) / .layoutPriority(-1)；也可在 1280 窄窗时把右列改为 400pt（本已在 T12 规格 400–460 内）。属视觉润色，不阻塞功能与验收。 |
| R2 | 记录 | 1440×900 场景非真实窗口：本机屏幕可见高 861pt，真实窗口内容高最多 834–861pt；该场景用离屏精确尺寸渲染（同源码/同字体），真实 app 在 1440×861 下实测右内边距 30pt 正常（ui-audit real_empty_light_1440x900.png：分隔线 1009.5、最右内容 1410）。 | — | 用户实机（屏幕更大）1440×900 窗口下 R1 仍会出现（离屏 1440×900 已复现右内边距 13pt），建议一并修 R1。 |
| R3 | 记录 | 暗色下 hero 底部 scrim 与暗纸底颜色接近，自动「纸底边缘」指标偏低（bottom 80%、right 91.7%），但视觉截图确认无纸边；该偏差是测量分类而非产品缺陷。 | — | 无需处理。 |

**通过/不通过汇总**：①–⑦ 全部 PASS；无功能级不通过项；仅 R1（右内边距压缩，P2）建议后续润色修复。

---

## 9.1 追加复测：P2 右内边距压缩（修复后，23:52）

**ui-audit 修复方案**（ContentView.swift，sha256 7a9a68ff…，mtime 23:49:50）：
1. coverHero 铺底改为 Rectangle + GeometryReader 内 .resizable().scaledToFill().frame(geo.size).clipped() → 图片不再向布局贡献「理想宽度」，切断最小宽度传播；
2. 右列改为 frame(minWidth: 400, idealWidth: 430, maxWidth: 430)。

**复测方法**：同一 harness（prepare WORKTREE 后重编译），复用 layouttest（根尺寸/版心）+ cover（4 场景 + 边缘/纸底/CTA/回归），并用逐像素扫描测右内边距（keyRow 发丝线/右对齐胶囊距窗口右缘）。

| 指标 | 修复前 | 修复后 | 判定 |
|---|---|---|---|
| layouttest plain 根尺寸（窗口 1280×800） | 1340.33 × 800（溢出） | **1280 × 800** | PASS（不再溢出） |
| 1280×800 竖分隔线 | 879pt | **849.0pt = 1280 − 431**，与代码期望误差 0 | PASS |
| 1280×800 右内边距（最右非纸底像素） | 0–2pt（贴窗边） | **30.0–30.5pt**（实测最右 1249.5–1250.0） | PASS（设计 30pt） |
| 1440×900 竖分隔线（离屏精确） | 1026pt | **1009.0pt = 1440 − 431**，误差 0 | PASS |
| 1440×900 右内边距 | 13pt | **30–31.5pt**（实测最右 1408.5–1410.0） | PASS |
| hero 尺寸 1280×800 | 879×682.5 | 849×682.5（窗口宽 **66.3%** × 内容区高 **100%**） | PASS（仍铺满左侧，无回退） |
| hero 尺寸 1440×900 | 1026×785.5 | 1009×785.5（**70.06%** × **100%**） | PASS |
| hero 四边图像活性（1280 light） | 99.2/100/100/100% | **100/100/100/100%** | PASS（无纸边） |
| hero 内纸底残留（1280 light / 1440 light） | 0.07% / 0.26% | **0.07% / 0.26%**（持平） | PASS |
| 图注对比度（1280） | 7.16:1 | **7.32:1** | PASS |
| CTA 首屏 / 彩色缩略图残留 | 可见 / 0 | **可见 / 0** | PASS |
| 工作台 / 画廊回归 diff | 0.008% / 0% | **0.008% / 0%**（未变） | PASS |

结论：**P2 已修复**，实测与 ui-audit 自测口径一致（分隔线 849/1009、右内边距 30pt），且 hero 铺满指标无回退。截图（cover_1280x800_*.png / cover_1440x900_*.png）与 cover_probe.json / layout_probe.json 已更新为修复后版本。

## 10. 证据清单（qa/verify/evidence/）

| 文件 | 说明 |
|---|---|
| cover_1280x800_light.png / cover_1280x800_dark.png | 1280×800 真实窗口亮/暗封面（hero 全幅 + 右列 + 图注） |
| cover_1440x900_light.png / cover_1440x900_dark.png | 1440×900 离屏精确尺寸亮/暗封面 |
| cover_rightcrop_1280x800.png / cover_rightcrop_1440x900.png | 右列裁剪放大（快捷键/输出表完整性目检） |
| cover_regression_workbench_light.png / cover_regression_gallery_light.png | 工作台/画廊回归截图 |
| cover_probe.json | 全部测量原始数值（版心/边缘/纸底/图注对比度/OCR checks/回归 diff） |
| layout_probe.json | R1 根因（根尺寸 1340.33、forced 1280 后 separator 仍 879） |
| theme_cover_light_1280x800.png（T10 期） | 改版前对照：框住小图 + 示例面板 |

---

## 11. 验证时间线

| 时间 | 事件 |
|---|---|
| 23:35 | T12 完成（ContentView 0d25bf37）；T13 claim |
| 23:38–23:45 | 封面探针搭建：4 场景渲染、发丝线定位版心、OCR（示例面板/CTA/截断）、工作台/画廊 diff |
| 23:45–23:47 | 修正测量（发丝线版心法 / 1440 离屏精确尺寸 / 暗色 scrim 说明）+ layouttest 定位 R1 根因 |
| 23:47 | swift test 112/112（当时合计 465）；报告落盘，complete task-13，消息 Lead/ui-audit |
| 23:49 | ui-audit 按 P2 建议修复（GeometryReader 铺图 + 右列 400/430） |
| 23:52 | P2 复测通过：根尺寸 1280（不再溢出）、分隔线 849/1009、右内边距 30pt、hero 无回退；Lead 删旧 hero 资产后 swift test 111（合计 464） |