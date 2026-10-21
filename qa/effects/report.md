# 特效「代码可行、效果不可行」独立复现与根因报告（T1）

- Shared Task task-1；写作用域仅 `qa/effects/`；未改产品源码/测试/output/；未 commit/push；未与并发门禁套件同时运行。
- 环境：conda `pindou` Python 3.11.15 / Pillow 12.3.0 / numpy 2.4.6 / OpenCV 4.14.0；60×60×16px（另做 100×100 复验），MARD-221。
- 交付：本报告 + `qa/effects/probe.py`（182 例矩阵+11 类专项探针）+ `qa/effects/protocol_probe.py`（真实 core_server 行协议）+ `qa/effects/artifacts/`（323 文件/12MB，单图 ≤1MB）。
- 素材：真实照片×2（海雕 512²、macOS 系统壁纸航拍 270²）、扁平卡通（白底粗描边猫脸 512²）、透明背景 RGBA（渐变心形 512²）、反例（浅蓝底+白色主体幽灵 512²）。

## 0. 结论速览

**代码路径全部可行（协议 15/15 与直接引擎逐像素一致、全部 ok），但 15 项特效真实使用中仅 6 项 A 级；6 项语义错误/破坏性，2 项过弱，1 项静默失效。用户主诉成立；首因还有 UI 改开关后预览根本不重算。**

### 15 项分级（A 可见且语义正确 / B 太弱 / C 失效 / D 语义错误或破坏性）

| 特效 | 阶段 | 关键量化 | 级 | 根因 |
|---|---|---|---|---|
| outline_cell 邻接描边 | grid | 照片描边珠 **65.9%**（L 37.6→11.4）、风景 71.9%、卡通 31.9%、100×100 61.9% | **D** | 「相邻异色一律描边」在连续调图必成黑网 |
| outline_edge 线稿描边 | pre+grid | 照片 6.8% 格变化、仅 13.4% 变更格有 ≥2 邻居；卡通 1.7%/0% 连续；透明图 0% | **D** | FIND_EDGES+NEAREST 降采样=孤立噪点；alpha 不参与 |
| preset 风格色板 | grid | 照片 99.8% 格变化、用色 52→6、**L 37.7→78.0**、近白 6.2%→28.4% | **D** | 直接最近色映射到 6 个浅色 → 洗白 |
| bg_remove 背景去除 | pre | 白幽灵**白色主体删除率 100%**；白底卡通耗材 3600→1266（−65%）但成品像素仅变 4.57% | **D** | 无连通域/边界泛洪；白珠与空格同色 |
| cel_shade 赛璐璐 | pre | 卡通 99.8% 格变化、L 85.4→62.9、**色相漂移 158°**、白底→灰；照片压暗 20% | **D** | RGB floor 分桶（255→192）压暗+串色 |
| neon 霓虹 | pre | 照片 L −8.7/彩度 +0.7；卡通 L −20.8/彩度 −1.0；图纸背景仍纯白 | **D** | 只有 Color+Brightness，无暗底/辉光 |
| chibi 大头 | geo | 4 素材真实检测 0 脸 → 与基线逐像素相同、ok、无 warning；模拟命中网格 60×60→**60×67**、**40.2% 白珠**、alpha 丢失 | **C**/D | 无脸静默返回；命中即破坏画布/透明 |
| crop 裁剪 | geo | 10~90% 裁剪 Δ格 63.6%；开关默认 0/0/1/1=**0 变化**；非方形裁剪 60×60→**60×38** | A / D(网格) | 默认恒等；改宽高比覆盖网格 |
| adjust 画面调整 | pre | UI 默认 sat=1.2：照片 17.4%/卡通 8.8% 格变化、中位 ΔE 0、p95≈12~14 | **B** | 默认低于量化可见阈值 |
| max_colors 限色数 | grid | 照片 52→12 色但仅 14.6% 格变化；卡通 6.6%；5 色透明图 0% | **B** | 生效但弱；≤N 时静默 no-op |
| dither 抖动 | pre(特判) | strength 0=基线逐像素同；1.0 照片 43.1%/风景 52.3%/卡通 15.6%；用色 52→64 | **A**/B(扁平) | 生效；仅渐变有意义、无 strength UI |
| mirror 镜像 | geo | 照片 66.7%、风景 86.9%、透明 20.3% 格变化 | **A** | 无 |
| grayscale 灰度 | pre | 用色 52→15、平均彩度 7.7→0.9（卡通 13.9→0.27） | **A**/D(RGBA) | convert L→RGB 丢 alpha |
| duotone 双色调 | pre | 照片 82.8% 格变化、用色 11、彩度→0.51 | **A**/D(RGBA) | convert("L") 丢 alpha |
| dark_chart 深色底 | chart | 图纸 bg [30,30,30]、暗像素 61.5%、自定义色生效；**finished 与基线逐像素相同** | **A**(图纸) | 只改 chart |

统计：A 6（mirror/crop/grayscale/duotone/dither/dark_chart，其中 3 项有附加缺陷）、B 2（adjust/max_colors）、C 1（chibi）、D 6（outline_cell/outline_edge/preset/bg_remove/cel_shade/neon）。

### Top 缺陷

| # | 级 | 缺陷 | 证据 |
|---|---|---|---|
| 1 | P0 | 改特效开关/参数后预览**不重算**，无脏标记/无提示/无 A-B | `ContentView.swift:78-145` 15 个 Toggle 无 onChange；generate 仅绑定 `:149` 按钮；`ui_static.json` dirty/stale=0 |
| 2 | P0 | 邻接描边黑网 | 描边珠 65.9%（照片）/71.9%（风景）；`photo_eagle/chart_outline_cell.png` |
| 3 | P0 | 风格色板洗白 | Δ格 99.8%、L +40.3、近白 6.2→28.4% |
| 4 | P0 | RGBA+灰度/赛璐璐/双色调 → 透明空格变实心珠 | 918→3600 颗（+292%），协议一致 |
| 5 | P0 | bg_remove 删白色主体/高光，白底图又看不出 | 幽灵主体删除 100%；白底卡通 −65% 耗材但成品像素仅变 4.57% |
| 6 | P1 | cel 压暗+串色 | 卡通 L −22.5、色相 158° |
| 7 | P1 | outline_edge 噪点/不可见 | 连续性 13.4%（照片）/0%（卡通） |
| 8 | P1 | 组合顺序毁效果；15 全开=单色 | 描边+马卡龙：描边珠 65.9%→**0%**；全开用色 **1** |
| 9 | P1 | neon 无霓虹感 | L −8.7、彩度 ±1、图纸背景白 |
| 10 | P1 | chibi 静默失效/命中破坏 | 0/4 检测；60×67、40% 白珠 |
| 11 | P2 | 几何特效静默改写网格 | 60×38 / 60×67 |
| 12 | P2 | 协议静默吞参数/未知 id；dither 绕过上限；错误只有「生成失败」且 stdout 被污染 | 第 5 节 |
| 13 | P2 | UI 只暴露 9/15 参数、从不请求 `op=effects`、schema 硬编码副本 | `ui_static.json` |
| 14 | P3 | dark_chart 在「成品效果」视图无反馈 | finished 逐像素同 |

**门禁为何全绿**：`app/Tests/PerlerAppTests/EffectsExposureTests.swift:58-120` 只断言 15 项装配/参数携带/生成不报错，无像素断言；TEST_REPORT 2.3.0 的 F2 也只是点状调参。本报告判据 = 真实使用语义 + 与基线量化差异 + 目视。

## 1. 事实基线

### 四阶段挂载点（`core/processor.py`）

| 阶段 | 位置 | 对象 | 说明 |
|---|---|---|---|
| geometric | `:119-127` | 原图 PIL | 可改尺寸→之后重算最终网格 |
| preprocess | `:126` + `:173-188` | 原图 PIL | 颜色/alpha/ctx.edge_mask；dither 在映射处特判 |
| grid | `:230-259` | 色卡索引矩阵 | outline_cell/max_colors/preset；重建 stats/耗材 |
| chart | `:289-299` | render_opts | 仅 dark_chart；**不影响 finished** |
| finished | `:313-323` | 白底纯色块 | 固定白底 |

事实：未注册 id/无该阶段 handler 静默跳过（`registry.py:76-83`）；参数经 `_coerce_params` 钳制（`:33-62`），但 **dither strength 在 processor 特判路径读原始参数、绕过 schema**（`processor.py:175-185`）；`outline_edge` 声明 preprocess 但 handler 是 preprocess+grid 两阶段（`outline.py:102-113`）；RGBA 输入保 alpha（`processor.py:110-118,168-171`）但对透明格跳过统计（空格不计耗材）。

### 15 项「代码做了什么→哪步→是否体现」

| 特效 | 实现（文件:行） | 图纸 | 成品 |
|---|---|---|---|
| chibi | `geometry.py:9-61`：cv2 人脸；无脸/无 cv2 直接 return；命中裁剪放大 1.4/压身 0.75、新建 RGB 白底画布 | 命中改尺寸 | 白边/白珠 |
| mirror | `geometry.py:64-78` transpose | 是 | 是 |
| crop | `geometry.py:81-103` 相对坐标 crop，非法区间静默返回原图 | 改宽高比则改网格 | 是 |
| grayscale | `filters.py:9-23` convert L→RGB | 是 | 是（RGBA 丢 alpha） |
| adjust | `filters.py:26-50` 三个 ImageEnhance | 弱 | 弱 |
| dither | `filters.py:53-64` 占位；真实 `processor.py:173-188` + `colors.py:174-206` Lab Floyd–Steinberg | 是 | 是 |
| cel_shade | `filters2.py:10-30` floor 分桶 RGB 逐通道 | 压暗/串色 | 同 |
| neon | `filters2.py:33-51` Color(1.5)+Brightness(0.75) | 变暗 | 变暗 |
| duotone | `filters2.py:54-74` L→c1..c2 | 是 | 是（RGBA 丢 alpha） |
| bg_remove | `filters2.py:77-97` 全图色距阈值 alpha=0，无连通域 | 空格无格线 | 弱 |
| outline_edge | `outline.py:67-99` FIND_EDGES→阈值→ctx.edge_mask；grid NEAREST 缩放替换 | 噪点 | 噪点 |
| outline_cell | `outline.py:18-64` 4 邻域异色标记+膨胀后替换 | 黑网 | 黑网 |
| max_colors | `presets.py:38-70` Top-N + Lab 最近映射 | 弱 | 弱 |
| preset | `presets.py:73-107` 预设最近色→色卡 | 洗白 | 洗白 |
| dark_chart | `filters.py:67-83` 只写 render_opts | 是 | **否** |

### Swift 装配顺序（`AppViewModel.swift:379-423`）

`chibi→mirror→crop→grayscale→adjust→cel_shade→neon→duotone→bg_remove→outline_edge→dither→outline_cell→max_colors→preset→dark_chart`。结构性冲突：preset 在 outline_cell 后→描边被映射掉；grayscale/cel/duotone 在 bg_remove 前→alpha 已丢；dark_chart 只改图纸；用户不可调顺序/不可见冲突；UI 从不请求 `op=effects`（`Engine.swift` 无该 op，仅 `EngineTests.swift:52` 用），15 项列表/默认值/顺序为硬编码副本。

## 2. 实验设计

素材与参数：见文件头；60×60×16px（另 100×100×16px）；MARD-221；save=False；UI 默认 show_grid/legend/labels=True；特效参数=Swift 开关默认值；组合按 Swift 顺序 + 反序对照；15 全开。

指标（finished 逐格采样）：Δcells（格子最大通道差>12 占比）、median/p95 CIELAB ΔE76、outline_bead_share（=#1A1A1A 最近色卡色 27,18,19）、chart_grid_area Δ、beads/colors/grid、mean_l/chroma/near_white（洗白/压暗）。

隔离：直接引擎 save=False；协议用真实 `core_server.py`，仅重定向 OUTPUT_DIR 到 `qa/effects/tmp_protocol/` 防止与门禁互相裁剪；未运行 run_tests/gui_smoke/stress_protocol/swift test。

产物：`qa/effects/artifacts/metrics.json`（182 例）、`probe_notes.json`、`summary_table.md`、`effects_registry.json`、`ui_static.json`、`protocol/protocol_results.json`、各素材 `contact_sheet_finished.jpg` / `contact_sheet_diff.jpg`。

## 3. 逐项证据（数值+图）

D 级：
- **outline_cell**：照片 Δcells 50.3%、描边珠 65.86%、L 37.65→11.42、用色 52→15；风景 71.86%；卡通 31.94%（五官被黑块吞）；100×100 61.87%。width 1/2/3 与 outer 都试过（w2 41.1%、w3 48.6%、outer 38.1%），**不是调参能救**。图：`photo_eagle/chart_outline_cell.png`、`cartoon_cat/contact_sheet_finished.jpg`。
- **outline_edge**：照片 6.83% 格变化、变更格 ≥2 邻居仅 13.4%（均值 0.56）→ 86.6% 孤立点；卡通 1.72%/0% 连续；透明图 0%（alpha 忽略）；threshold 100→2.03%、20→12.67%、w2→24.3% 只是更粗噪点。图：`photo_eagle/chart_outline_edge.png`、`photo_eagle/edge_mask.png`。
- **preset**：照片 99.78% 格变化、52→6 色、**L +40.3**、近白 6.2%→28.4%、中位 ΔE 46.1；风景 L 52→74；卡通 L 85→94、近白 63.6%→82.3%；5 套预设全洗白。图：`photo_eagle/chart_preset_pastel.png`、`photo_sky/contact_sheet_finished.jpg`。
- **bg_remove**：幽灵白色主体删除 100%、背景删除 0%（定向反例）；照片白雕头/黄喙高光删 111 格（tol60→955 格）；白底卡通 3600→1266 颗但成品像素仅 4.57% 变化、图纸网格区 18.2%；透明源图 no-op。图：`cartoon_ghost/bgremove_checkerboard.png`（棋盘格上白主体全透明）、`photo_eagle/bgremove_deleted_overlay.png`（红格=被删）。
- **cel_shade**：卡通 99.83% 格变化、L 85.4→62.9、白底(255)→灰(192)、色相漂移 158.2°；照片 L 37.7→29.9；风景 52→39.8。图：`cartoon_cat/chart_cel4.png`、`transparent_icon/contact_sheet_finished.jpg`。
- **neon**：照片 L −8.7/彩度 +0.69；卡通 L −20.8/彩度 −1.0；风景彩度 +4.2（唯一略有效）；图纸背景仍白；叠加 dark 底也无辉光。图：`photo_eagle/contact_sheet_finished.jpg` 第 2 行。

C 级：**chibi**：4 素材 haarcascade 检测 0 脸 → 逐像素同基线、ok=true、**响应无 warning**；cv2 缺失路径 `except ImportError: return img` 同样静默；模拟命中（QA monkeypatch）：网格 60×60→**60×67**、成品 **40.17% 纯白填充珠**、透明源 geometric 输出 RGBA→RGB、输出 512×571。图：`photo_eagle/chibi_patched_finished.png`。

B 级：**adjust**：默认 sat=1.2：照片 17.36% 格变化/中位 ΔE 0/p95 14.0，卡通 8.83%，风景 25.94%。量化下限：MARD-221 相邻色 ΔE 中位 7.97；亮度 1.05→22.9% 格变化、饱和度 1.2→18.9%、1.5→37.9% → 小步调整大量被吞。**max_colors**：照片 52→12 色、Δcells 14.61%；卡通 6.56%；风景 24.44%；5 色透明图 0%。

A 级：mirror（66.7%/86.9%/20.3% 格变化）、crop（10~90% 裁剪 63.6%；但默认参数 0 变化、非方形裁剪 60×60→60×38）、grayscale（用色 52→15、彩度 0.9；RGBA 丢 alpha）、duotone（Δcells 82.8%、用色 11、彩度 0.51；RGBA 丢 alpha）、dither（strength 0=基线逐像素同；1.0 照片 43.1%/风景 52.3%/卡通 15.6%；用色 52→64）、dark_chart（图纸 bg [30,30,30]、暗像素 61.5%、自定义色生效；finished 逐像素同）。

## 4. 组合与顺序

| 组合 | 量化 | 结论 |
|---|---|---|
| 描边+限色12 | 描边珠仍 65.86%，仅用色 52→12 | 黑网没救 |
| 描边+马卡龙（Swift 序） | 描边珠 65.86%→**0%**，用色 3 | preset 后执行把描边映射掉 |
| 反序（preset→描边） | 描边珠 16.53%（视觉可用） | 正确顺序 UI 不可达 |
| 灰度+抖动 | Δcells 53.0%、用色 27 | 可用 |
| **15 全开** | **用色=1**、Δcells≈100%、耗材 3600 | 灾难：无互斥/冲突策略 |

证据：`photo_eagle/chart_combo_outline_preset.png`、`photo_eagle/chart_combo_all15.png`、`cartoon_cat/chart_order_rev_preset_outline.png`、`summary_table.md`。

## 5. 专项探针与协议验证

- **量化下限**：MARD-221 相邻色 ΔE min 0.35/p10 2.98/median 7.97/p90 14.31；亮度曲线 1.02→10.5%、1.05→22.9%、1.10→40.5%、1.20→56.3%；饱和度 1.05→6.0%、1.2→18.9%、1.5→37.9% → 小于约半个色卡间距的调整会被吞掉。
- **dither strength**：photo_sky 上 0/0.5/1.0/1.5/5.0 与基线格差异 0/34.6%/52.3%/66.6%/99.7%（逐级生效）；但 **5.0 超出 schema max=1.5 未被钳制**，输出崩坏。
- **alpha 丢失**：透明心形基线 918 颗（=alpha 覆盖率 25.45%×3600，正确）；grayscale/cel_shade/duotone 后 **3600 颗（+292%）**；adjust/neon/bg_remove/outline_edge 保 alpha（918）。
- **协议验证**（真实 `core_server.py`，仅重定向 OUTPUT_DIR 到 `qa/effects/tmp_protocol/`；请求与 Swift `generate()` 完全一致）：
  1) **15/15 单特效 ok=true，grid/beads/colors 与直接引擎全等、成品图逐像素一致** → 协议层不破坏 effects。
  2) 参数静默：`max:"8"`≡8（int 强转）；`maxColors:8`（错名）→默认 12；`direction:"diagonal"`→水平；`preset:"unknown"`→pastel；mirror 未知参数被丢；outline width 99→3；非法/空 HEX→默认色；**未知特效 id "outline_edges"→ok=true、结果=基线、无 warning**。
  3) dither：strength 生效（s0=无抖动、逐级增强、5.0 未被钳制、`s_abc` 回退 1.0 与显式 1.0 逐像素同）。
  4) outline_edge 两阶段：协议与直接调用逐像素一致 → preprocess 的 ctx.edge_mask + grid 落色均执行；叠在 grayscale 后变化 41.56% → 顺序敏感。
  5) dark_chart：图纸背景 [30,30,30]、自定义 [32,32,64]、暗像素 61.5%；finished 与基线逐像素相同。
  6) bg_remove：白底卡通 beads 1266、透明格 2334、sum(color_stats)=1266=total_beads → 透明格不计耗材。
  7) chibi：ok=true、grid 不变、成品=基线、无 warning 字段 → 静默。
  8) 顺序：描边+限色 描边珠 0.6586 vs 反序 0.5722；描边+马卡龙 0.0 vs 反序 0.1653 → 顺序即结果。
  9) edit：overrides 单元格颜色=指定色号（覆盖赢过 effects，35fa440 修复有效）。
  10) 协议缺陷：响应无 `effects_applied`/warnings 回显；非法 effects 类型时错误="生成失败"（无细节），且 `core/processor.py` 的 `print("[错误] 处理失败")` 写进 **stdout** 污染 JSON 行协议（实测捕获 `[错误] 处理失败：'str' object has no attribute 'get'`）；Swift `Engine.handleLine` JSON 解析失败静默丢弃 → 用户只看到笼统失败。

## 6. Swift UI 可用性缺陷

1. **开关/参数变化不重算、无脏标记**：`ContentView.swift:78-145` 15 个 Toggle 直接绑定 `$vm.xxxOn`，**无 onChange**；唯一 `generate()` 在 `:149` 按钮；全仓 `dirty|stale|需重新生成` 命中 0；只有 template/ratio/previewGeo 三处 onChange（`:43,63,279`）→ 拨开关看到的图永远不变，状态栏仍显示上次「完成」。
2. **无 before/after、无提示**：subtle 特效（adjust/max_colors/dark_chart）无法自证。
3. **预览默认图纸**：`showFinished=false`（`AppViewModel.swift:211`）；dark_chart 只改 chart、finished 不变 → 在「成品效果」下开深色底完全无反馈（`ContentView.swift:227,247`）。
4. **参数暴露 9/15**：outline_cell 仅开关（color/width/outer 不可调）、outline_edge 仅开关（threshold/color/width）、dither 仅开关（strength）、dark_chart 仅开关、grayscale contrast、chibi 两参数均无控件 → 最需要救的 6 项恰好不能调。
5. **schema 双份**：UI 从不请求 `op=effects`（仅 tests 用），15 项顺序/默认值硬编码在 `AppViewModel.effectsParams()`，与引擎 schema 漂移。
6. **描述/引导缺失**：全仓无 tooltip/`.help(`；特效面板无四阶段分组、无顺序说明、无冲突提示（描边+风格色板、全开=单色不可预知）。
7. **默认参数即空操作**：crop 默认 0/0/1/1（0 变化）；max_colors 在 ≤N 色图无变化；chibi 无脸无提示；bg_remove 在透明图无变化 —— 全部静默。
8. **双 UI 能力不一致**：Tk 版（`ui/`、`main.py`）无任何特效入口（grep 0 命中；ARCHITECTURE.md:183 注明）。

## 7. 修复建议

### 可最小修复（实现 bug/暴露面）

| # | 缺陷 | 最小修复 | 文件:函数 |
|---|---|---|---|
| F1 | 透明 PNG 经 grayscale/cel/duotone 丢 alpha（+292% 耗材） | 拆 alpha：处理 RGB 后 merge 回来；RGBA 输入保持 RGBA | `filters.py:_grayscale`、`filters2.py:_cel_shade/_duotone` |
| F2 | cel 取整压暗+串色 | 桶公式端点对齐/改 Lab 明度分桶保留 a*b*（或换聚类量化） | `filters2.py:_cel_shade` |
| F3 | dither strength 绕过 schema 上限 | processor 特判处 clamp 0~1.5 | `processor.py:173-188` |
| F4 | 未知 id/参数/非法值静默、错误不透明、stdout 污染 | apply_phase 收集 warning；异常改 stderr；协议加 `warnings` 字段；非法 effects 返回具体 error | `registry.py`、`processor.py:391-395`、`core_server.py:_generate` |
| F5 | 描边把透明空格填成珠 | grid 描边跳过 `idx<0` 的空格 | `outline.py:_apply_outline` |
| F6 | 几何特效静默改写请求网格 | final grid≠请求时返回 warning（"60×60→60×38"） | `processor.py:129-155` + warnings |
| F7 | chibi 静默失效 | ctx.warnings 记录无脸/无 cv2；命中时保持画布/alpha | `geometry.py:_chibi` |
| F8 | crop 开关默认空操作 | 开启时默认内缩 0.1~0.9 | `AppViewModel.swift`（cropOn didSet） |
| F9 | UI 开关不重算 | `needsRegenerate` + `scheduleAutoPreview()`（~500ms debounce、忙时排队/取消旧请求、不覆盖手动生成） | `AppViewModel.swift` |
| F10 | dark_chart 只在图纸 | UI 明示「仅图纸」 | 文案（ContentView 由 ui-audit） |

### 需要重新设计算法（调参救不了）

| 特效 | 现状根因 | 期望能力 |
|---|---|---|
| outline_cell | 无边缘强度判据，照片处处异色 | 相邻 Lab/CIEDE2000 差阈值描边 + 先区域简化再描；照片描边珠 ≤15%、平涂卡通保留轮廓 |
| outline_edge | 全分辨率 FIND_EDGES+NEAREST=孤立点；忽略 alpha | 网格尺度边缘（DoG/Canny+形态学闭运算）+ 滞后阈值 + 去孤点；alpha 边界纳入；已有深描边的图不重复涂黑 |
| preset | 6 个浅色最近邻=洗白 | 保结构量化/亮度秩保持后再套预设色；用色 ≤ 预设色数、明度分布接近原图 |
| bg_remove | 无连通域约束 | 从边界泛洪/连通域（或 GrabCut）保留内部同色主体；支持 auto 角落取色；透明格不计耗材 |
| cel_shade | RGB floor 分桶压暗+串色 | 边缘保留平滑 + Lab 色阶/聚类平涂，保留色相形状；透明保持 |
| neon | 只有 Color+Brightness | 暗底 + 高饱和 + 亮部泛光；与 dark_chart 解耦 |
| chibi | 裁剪粘贴改画布/丢 alpha；无脸静默 | 局部形变保持画布/透明；失败明确 warning |
| 组合架构 | 固定顺序、风格化在描边后、无互斥 | 阶段内优先级/冲突规则；全开仍有可读结果 |

优先级：P0 = F1/F5 + outline_cell/preset/bg_remove 算法 + F9 自动预览；P1 = outline_edge/cel/neon 算法 + F3/F4 + F6/F7；P2 = adjust 默认值、max_colors no-op 提示、F8、参数暴露补齐。

## 8. 复现命令与产物

`bash`
cd /Users/chen/Desktop/learn/PerlerBeadApp
PYTHONPATH=. /opt/homebrew/Caskroom/miniconda/base/envs/pindou/bin/python qa/effects/make_inputs.py
PYTHONPATH=. /opt/homebrew/Caskroom/miniconda/base/envs/pindou/bin/python qa/effects/probe.py          # ~85s, save=False
PYTHONPATH=. /opt/homebrew/Caskroom/miniconda/base/envs/pindou/bin/python qa/effects/protocol_probe.py  # OUTPUT_DIR 隔离
`

- 数据：`qa/effects/artifacts/metrics.json` / `probe_notes.json` / `summary_table.md` / `protocol/protocol_results.json`。
- 关键图：`photo_eagle/chart_outline_cell.png`、`photo_eagle/chart_preset_pastel.png`、`photo_eagle/chart_outline_edge.png`、`photo_eagle/chart_dark_chart.png`、`photo_eagle/bgremove_deleted_overlay.png`、`cartoon_ghost/bgremove_checkerboard.png`、`transparent_icon/alpha_loss_grayscale_finished.png`、`photo_eagle/chibi_patched_finished.png`、`photo_eagle/grid100_outline_cell_finished.png`、各素材 `contact_sheet_finished.jpg` / `contact_sheet_diff.jpg`。

## 9. 未决问题/局限

- chibi 真实人脸路径未覆盖（本地无真人照片）：已用运行时 monkeypatch 验证「命中后」破坏，不改产品代码。
- 100×100 只复验 6 项关键特效；更细网格与其它色卡（hama_16/perler_24）未穷举。
- 描边珠占比以 #1A1A1A 最近色卡色 (27,18,19) 近似，换色卡需重算。
- 未做真机截图/App 内交互（门禁并发纪律 + UI 由 ui-audit 重设计）；UI 结论均为代码级证据。
- 本报告与 412 项门禁不冲突：门禁验证接口/装配/回归，不验证视觉语义；建议将上述量化阈值纳入 run_tests 作为视觉结构门禁。
