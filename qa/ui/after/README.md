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

---

## 5. T9 老钱风主题（2026-10-21 追加）

- 主题：暖羊皮纸 + 深咖墨 + 黄铜/干邑；**全局移除朱红/绿**（旧 #B03D25 / #3E6B4F 已删）。
- 开始页：PLATE 00 hero（Lead 提供 `app/Sources/PerlerApp/Resources/hero_photo_to_beads.jpg`，经 `EditorialAssets.heroPhotoToBeads` 加载）+ 双框线 + 四角 crop marks + 黄铜渐变标题 + PHOTOGRAPH/BEADS 双列图注；右侧示例图版改为图录式（编号/名称/尺寸/颗数/黄铜箭头）。
- 工作台/画廊/色卡/状态条全部使用新 tokens；报头下方双发丝线 + fleuron；Ghost 按钮暖纸底黄铜发丝线；进度条干邑；状态点青铜。
- 新增选题截图：
  | 场景 | 亮色 | 暗色 |
  |---|---|---|
  | 开始页 | real_empty_light_1280x800.png | real_empty_dark_1280x800.png |
  | 工作台 | harness_current_1280_light_v2.png | harness_current_1280_dark_v2.png |
  | 特效画廊 | harness_effects_gallery_light_v2.png | harness_effects_gallery_dark_v2.png |
  | 色卡 | harness_colorschart_light_v2.png | harness_colorschart_dark_v2.png |
- tokens 明细与对比度实测、红绿移除验收见 qa/ui/theme/README.md。
- T8 缩放证据（zoom 100/200/400 + offset）仍在：harness_zoom_100/200/400_light.png。

## 6. T8 补修：双 .gesture 叠加吞掉拖拽事件（view-verify 复现 → 已修）

- **根因**：plate 同时挂载 `.gesture(dragGesture, including: vm.editMode ? .none : .all)` 与 `.gesture(editGesture, including: vm.editMode ? .all : .none)`；非编辑模式下外层 editGesture 的 mask `.none` 会把内层 dragGesture 整个吞掉（事件级验证 0 次 onChanged）。T8 首轮只验证了数学/闭包链，**未验证事件到达**，属误判。
- **修复**：改为单一条件手势 —— 抽出 `plateBase`，`Group { if vm.editMode { plateBase.gesture(editGesture) } else { plateBase.gesture(dragGesture) } }`，不再保留双 `.gesture` 叠加结构；双击居中保留；编辑模式不拖拽。
- **事件到达级验证**（新增 `UIShot dragcheck`：真实 ContentView + 注入 VM + 合成 NSEvent 走 app 事件循环）：
  - zoom=200 拖拽：`vm.offset` 从 (0,0) → **(112, -64)**，窗口像素位移 **689,040 px**（`t8_drag_before.png` / `t8_drag_after.png`）
  - 编辑模式拖拽：`vm.offset` 保持 (0,0) ✔
  - fit 模式拖拽：事件到达（`fitToWindow` → false，zoom=76.5），图恰好适配时 offset 保持 0（正确：无空间可平移）✔
  - 结果：**DRAGCHECK PASS**，日志 `t8_dragcheck.log`
- 复跑：`PERLER_REPO_ROOT=$PWD TMPDIR=$PWD/qa/ui/tmp qa/ui/render/.build/debug/UIShot dragcheck`
## 7. P3 残余修复：滚轮/双指缩放锚点 y 轴镜像（view-verify R1）

- **问题**：`PreviewInputCatcher.EventCatcherView` 默认非 flipped（左下原点），`self.convert(event.locationInWindow, from: nil)` 得到的 y 直接作为 SwiftUI 锚点（左上原点）→ 非居中锚点缩放时上下镜像。
- **修复（最小改动）**：EventCatcherView `override var isFlipped: Bool { true }`（坐标与 SwiftUI 一致）+ 扣掉图版 16pt padding：`PreviewViewport.viewportPoint(fromPlatePoint:inset:)`；滚轮/双指 delta 方向未动（不改变缩放方向语义）。
- **验证**：新增 `testViewportPointFromPlatePointAccountsForInsetAndTopLeftOrigin`；swift build 通过；swift test **111/111**；dragcheck 回归仍 DRAGCHECK PASS。
- **独立复验（view-verify T10 §11，2026-10-21）**：isFlipped/inset/viewportPoint 4 点误差全 0；onZoom(2.0, 视口锚点 (177.2, 88.4)) @100%→200% → offset (128.8, +156.6)，与独立公式零误差，旧镜像值 −156.6 未出现 → **R1 通过**。仅剩人工滚轮验收（AX 限制）。
- 未 commit/push。
## 8. 人工验收清单（引用 view-verify 报告）

自动化已覆盖事件链路/数学/像素位移/主题 tokens/对比度；**滚轮与双指真实手势**受 macOS AX 权限限制无法自动合成，需人工走查。清单见 view-verify 报告 `qa/verify/zoom_pan_and_theme_report.md` §6（9 条）：

1. 非中心位置捏合/滚轮缩放：光标下内容尽量不动（R1 锚点最终验证点）
2. 双指捏合缩放（触控板）
3. 双指滚动平移
4. 拖拽边界（大图至少 15% 可见，不丢图）
5. 滑杆 + −/＋ + 百分比（交互自动切出适应窗口）
6. 编辑模式回归（点击换色、拖拽禁用、双击居中）
7. 亮/暗外观切换
8. 开始页 hero（不拉伸/不裁切主体、双框/crop marks/图注）
9. 拖拽极限（连续极端拖拽后仍在版心内）

发现问题时把「操作 + 现象 + 截图」发 view-verify（同一 harness 可定位）。
## 9. T12 开始页改版：删除示例面板 + 左侧整块背景大图 hero（用户四轮反馈）

- **删除**：封面右侧「示例图版 / 内置模板」整块（coverRail + 彩色模板缩略图）；TemplateThumb 一并清理（只被封面使用）。模板入口保留在工作台侧栏「模板」下拉中。
- **新版开始页**：左 = `EditorialAssets.heroPhotoToBeadsCover`（2400×1800，4:3 对角过渡）`.resizable().aspectRatio(contentMode: .fill).clipped()` 铺满整个左侧内容区（无边距/无框住小图）；底部深色 scrim + 左下奶油色图注（PLATE 00 · FROM PHOTOGRAPH TO BEAD；PHOTOGRAPH / BEADS 双列微说明），不遮鹰眼主体。右 = 430pt 纸底操作列：eyebrow、黄铜渐变标题「从一张照片，到 3,600 颗豆。」、standfirst、「选择图片 …」主 CTA + 拖入提示、快捷键 4 行 / 输出 3 行紧凑表、本机处理说明。
- **整页只剩纸/墨/黄铜**：无任何彩色缩略图；亮暗双主题；1280×800 不滚动、CTA 首屏可见；1440 宽 hero 自然扩展（右列固定 430）。
- 截图（已更新）：real_empty_{light,dark}_1280x800.png、real_empty_{light,dark}_1440x900.png。
- 未改 Package.swift / Resources / EditorialAssets / AssetTests；swift build 通过；swift test **112/112**；未 commit/push。
## 10. T13 P2 补修：封面固有最小宽度导致右列被压缩/右内边距被裁

- **问题（view-verify T13）**：hero 的 `.aspectRatio(contentMode: .fill)` 让图片理想宽 ≈ 内容高×4/3（≈910pt），+ 右列 430 → 整页固有最小宽 ≈1290–1310pt；1280×800 下右列被压到 400、设计 30pt 右内边距被裁到 0–18.5pt。
- **修复**：hero 不参与 HStack 理想宽度计算——铺底 `Rectangle` + `GeometryReader` 内 `.resizable().scaledToFill().frame(geo.size).clipped()`；右列 `frame(minWidth: 400, idealWidth: 430, maxWidth: 430)`。
- **实测（截图逐像素测量）**：1280×800 分隔线 849.0pt / 右列 431pt / 内容右内边距 **30.0pt**；1440 分隔线 1009.0pt / 右列 431pt / 右内边距 **30.0pt**；亮/暗一致，无裁切。
- 构建通过；swift test **112/112**；未 commit/push。
