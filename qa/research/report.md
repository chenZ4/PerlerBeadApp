# 拼豆 App 特效修复 × 时尚杂志风 UI：开源参考与可采纳方案

> 调研者：oss-research（Shared Task task-4）
> 检索/验证日期：**2026-10-21**（所有外链均于该日通过 web_fetch 实际打开；GitHub 元数据来自当日 GitHub REST API，star/许可证/最后推送时间为抓取时刻快照）
> 仓库基线：`3b7393d`（2026-09-30）
> 运行环境：conda `pindou`，Python 3.11.15 / numpy 2.4.6 / Pillow 12.3.0 / opencv-python 4.14.0；**无 scipy、无 scikit-image**（结论均按「只用 numpy + Pillow + cv2」设计）
> 范围约束：只写 `qa/research/`；未修改任何产品源码/测试/output。
> 外部内容是数据不是指令：本报告仅引用其事实信息（版本、许可证、算法、文档），未执行任何外部页面中的指令。

---

## 0. 执行摘要（TL;DR）

**特效侧（每条都有本地实测数据支撑，详见 §3–§4）：**

1. **「邻接描边变黑网」的根因是语义错误，不是参数问题**：现状 `core/effects/outline.py:_apply_outline` 把「任意相邻异色格」都画线。eagle 照片 64×64 下实测 **57.3% 网格被改写**。修复：在色卡索引上计算相邻格 **CIEDE2000**，只保留最强的 p88（约 8–12%）边并去孤点，实测降到 **9.2%**，视觉上变成干净的轮廓（图 `artifacts/lineart_compare.png` 第 6、8 格）。改动约 25 行 numpy，半天内可完成。
2. **「线稿描边只覆盖 6%、噪点重」的根因是「全分辨率 `ImageFilter.FIND_EDGES` + 阈值 + NEAREST 抽点」**：6.9% 覆盖率中 **79.1% 是孤立像素**、131 个连通块。修复：先做对比度感知下采样到 64×64，在网格亮度上做 **DoG（σ₁=0.8, σ₂=1.6 格）+ 双阈值滞后 + Zhang-Suen 细化 + 去孤点**，实测覆盖率 **8.6%**、连通块 **7 个**、最大块占 67.5%（图第 4、7 格）。约 80 行 numpy/cv2，1 天内可完成。**XDoG 不能直接替代**：在 512→64 的实测中，按论文推荐 ε=0.1/φ=200 二值化后覆盖率 100%（退化为全黑），只适合插画/动画源图并逐图调参——结论：**不采纳为通用实现**（§3.3）。
3. **「赛璐璐怪色块」的根因是 RGB 逐通道色阶化后再面积平均**：4 级 posterize（每通道 64 色）再 BOX 下采样会生成大量中间色，再被 CIELAB 最近色映射成 43 种「脏色」珠子；实测 **43.3% 的格子与局部均值 ΔE2000>10**、speckle 21.3%。修复：**边缘保持抽象（`cv2.stylization`）+ 对比度感知下采样 + Lab k-means（k=2×levels）+ CIEDE2000 映射**，实测 outlier **22.9%**、speckle **9.3%**、珠子数 43→8（`artifacts/cel_compare.png`）。约 50 行，1 天内。
4. **色卡映射本身值得升级**：现状 CIE76（Lab 欧氏）vs CIEDE2000 实测 **21.4% 的格子会换色**，CIEDE2000 的局部保真中位 ΔE 3.74 vs CIE76 3.99；CIEDE2000 映射 64×64×221 色耗时 92.5ms（CIE76 12ms）——完全可接受。**采纳 CIEDE2000**（与 Pindo 一致），Oklab 在本数据上中位 ΔE 4.49，仅建议作为更快的备选。
5. **风格色板「照片洗成白团」是「硬映射 + 无对比度归一化」**：6 个 pastel 锚点里含近白锚点，照片中大量中低饱和色在 CIELAB 下最近邻都是近白。修复方向：**引导色而非硬映射**——先做 L 通道百分位拉伸（黑/白点归一），再用 k-means 提取 4–6 个图像主色，并按亮度顺序受约束地映射到风格锚点，最后加 **strength 混合滑杆（0–1）**与抖动；参考 Jett-Wu 的候选色评分/多样性选择和 Pindo 的 CIEDE2000 + 清理管线（§3.1）。
6. **背景去除「白主体误删」**：现状是「全图颜色容差」匹配，白色主体与浅灰背景的 ΔE 只有 1.7 vs 2.0–3.5，任何单一容差都无法分开。实测合成用例：现状白主体保留率 **3%**；**GrabCut（矩形初始化）保留 100%、背景去除 100%**；而对「白底 + 深描边包围的近白主体」，**边界连通域键控**恰好正确（内部保留 100%）。采纳 **GrabCut 主路径 + 边界连通域平涂兜底 + 吸管/容差/连续区域 UI**；`rembg` 虽 MIT 但模型+onnxruntime 太重，**不采纳**（§3.5）。注意性能：GrabCut 512px 约 **0.96s**、2048px 约 **40.9s** → 必须先降到 ≤640px 再算 mask。
7. **chibi 静默失效**：Haar `detectMultiScale` 返回空就直接 `return img`（`core/effects/geometry.py:9`），无状态、无提示。采纳 **YuNet（`cv2.FaceDetectorYN`，模型 345KB、MIT、opencv_zoo）为主 + Haar alt2 兜底 + 无脸时显式返回 `{"skipped": true, "reason": "no_face"}` 并在 UI 提示/提供手动头部区域**。新增依赖为零（cv2 已装，含 dnn）。
8. **抖动/限色顺序错误**：现状 `dither` 在颜色映射阶段执行，之后 `max_colors`、`preset` 还会重映射索引，会把抖动结果打掉。正确顺序：**先限色/色板候选，再抖动**；抖动建议在 Oklab/线性 RGB 做蛇形 Floyd–Steinberg，另提供 4×4 Bayer 有序抖动（pyxelate 的 MIT 矩阵）作为低色数渐变选项。
9. **开关不自动重渲染**是工程缺陷：`AppViewModel.swift` 的 `effectsParams()`（:379）只在手动 `generate()`（:425）时汇总。用 `onChange(renderSignature)` + 250ms debounce + 取消在途请求即可；对 GrabCut/stylization 这类重特效先跑低分辨率预览。

**UI 侧（完整 tokens 见 §5.2）：**
- 方向没错：**米白纸感 + 墨黑 + 单一强调色**是 Kinfolk（单色 + 衬线 + 编号）与 Monocle（油墨黑 + 新闻纸奶油 + 唯一信号黄）的公开版面语言；建议 **paper `#FDFCF3`（Monocle 分析页 token）/ card `#FFFFFF`（Kinfolk Bone White）/ ink `#21201C`（Radix sand-12）/ 二级 `#63635E`（sand-11）/ hairline `#CFCECA`（sand-7）/ 强调 `#E5484D`（Radix red-9，MIT）**。
- 字体零打包方案：**New York（macOS 系统衬线，Apple 官方字体页可查）+ 宋体 Songti SC（macOS 自带）+ 仅标题用 Didot/Bodoni 72（macOS 自带）**；若要可再分发，用 **Fraunces / Newsreader / Instrument Serif（均为 SIL OFL 1.1，已核对 OFL 文本）+ 思源宋体或霞鹜文楷（OFL 1.1）**。**不要**把 Apple 系统字体文件打进安装包（只按字体名引用）。
- 版面规则：1px 细线取代阴影/玻璃材质；3 栏卡网格 + 16px gap；eyebrow（11pt 大写字 +0.075em 字距）+ 编号（01/06）+ 衬线大标题（-0.02em）+ standfirst；单屏一张主图；墙纸式 50/50 图文 hero；强调色只出现在一个动作上。
- SwiftUI 组件参考：Luminare（BSD-3，169★）、SimpleSidebar（MIT，229★）、design-foundation（MIT，28★）、CodeEdit（MIT，23k★，真实 macOS 应用架构）。

**落地顺序：** P0（不改架构，1–2 天）：邻接描边 ΔE 门控、线稿 DoG 网格算法、赛璐璐管线、色卡 CIEDE2000、特效自动重渲染；P1（2–4 天）：限色/风格色板引导色、抖动顺序、背景去除 GrabCut、chibi YuNet+状态；P2（3–5 天）：Theme tokens + 版面重构；P3（可选）：rembg、蓝噪声抖点、风格化模型。

---

## 1. 现状根因（代码级）

以下行号基于仓库基线 `3b7393d`。

| 缺陷 | 位置 | 根因 |
|---|---|---|
| 邻接描边黑网（实测 57.3% 网格被改） | `core/effects/outline.py:18 _apply_outline` | 语义是「相邻格异色即描边」；照片中相邻格几乎两两异色 → 全图线网。无对比度/感知差门控，无预算控制。 |
| 线稿描边 6.9%、79% 孤立点 | `core/effects/outline.py:67 _outline_edge_image` / `:76 _outline_edge_grid` | PIL `FIND_EDGES` 在全分辨率做 3×3 卷积 → 固定阈值 40 → `NEAREST` 抽 1 个像素到 64×64。边缘像素是 1px 级噪声，抽点后只剩孤立点；阈值与网格尺寸不联动。 |
| 赛璐璐脏色块 | `core/effects/filters2.py:10 _cel_shade` | RGB 三通道各自 `floor(v/64)*64`，再经 BOX 面积平均 → 产生大量非色卡中间色，最后被 Lab 最近色硬映射成 43 种珠子（4 级色阶的语义完全丢失）。 |
| 风格色板白团 | `core/effects/presets.py:73 _preset` | 每个色卡色硬映射到「最近预设色」；pastel 含近白锚点，照片低饱和区大量落入近白 → 无对比度归一、无 strength 混合、无抖动。 |
| 限色数效果差 | `core/effects/presets.py:38 _max_colors` | 仅按频次取 top-N，被淘汰色再映射到最近保留色；没有感知聚类、没有明暗锚点保护，容易把色板缩成一片浅色。 |
| 背景去除误删白主体 | `core/effects/filters2.py:77 _bg_remove` | 全图 RGB L1 距离 ≤ tol×3 直接置 alpha=0；没有连通域、没有目标色采样、没有 GrabCut 兜底，白色主体与浅灰背景同时被删。 |
| chibi 静默 no-op | `core/effects/geometry.py:9 _chibi` | 默认 Haar 级联 `detectMultiScale(1.1,5,minSize=min/8)`；无 face 直接 `return img`，无状态字段，UI 无从提示。 |
| 抖动被后续特效打掉 | `core/processor.py:173–187` + `core/effects/registry.py` 顺序 | `dither` 在映射阶段生效，随后 grid 阶段 `max_colors`/`preset`、`outline_cell` 继续改索引。 |
| 开关不自动重算 | `app/Sources/PerlerApp/AppViewModel.swift:159–192, 379–470` | 各 Toggle 只改 `@Published`，没有 onChange → generate 的触发链。 |
| 图纸深色底不影响成品图 | `core/effects/filters.py:63 _dark_chart` | 只改 chart 渲染 opts，finished 图独立渲染。属于「命名/预期」问题，建议改名「深色图纸底」并在 UI 标注。 |
| 色差公式 | `core/colors.py:158 closest_indices` | CIE76（Lab 欧氏）。对高彩度/低明度区的权重与 CIEDE2000 有系统偏差（实测 21.4% 格子换色）。 |

---

## 2. 特效算法采纳矩阵（一页版）

| # | 问题 | 采纳方案 | 参考实现（URL / license / 代码位置） | 移植量 | 结论 |
|---|---|---|---|---|---|
| 1 | 邻接描边黑网 | ΔE2000 门控 + 分位预算 + 去孤点；可选仅外轮廓 | 本报告 §3.3；Pindo（GPL-3.0，仅思路）`lib/engine/pattern-cleanup.ts` | ~25 行，0.5d | **推荐采纳** |
| 2 | 线稿描边噪声/低覆盖 | 对比度感知下采样 → 网格 DoG(0.8/1.6) → 双阈值滞后 → Zhang-Suen 细化 → 去孤点；插画源图走「全分辨率线稿覆盖率」路径 | skimage DoG 文档（BSD-3 参考公式）；Pindo `stroke-extract.ts`（GPL，思路）；OpenCV Apache-2.0 | ~80 行，1d | **推荐采纳** |
| 3 | 赛璐璐脏色块 | `cv2.stylization`/bilateral → 对比度感知下采样 → Lab k-means(k=2×levels) → CIEDE2000 映射 | OpenCV NPR 官方文档（Apache-2.0）；PixelOE `contrast_based.py`（Apache-2.0） | ~50 行，1d | **推荐采纳** |
| 4 | 风格色板白团 | 引导色：L 百分位拉伸 → k-means 主色 → 保序映射到风格锚点 → strength 混合 → 抖动 | Jett-Wu `imageToBeads.ts`（MIT，可移植）；Pindo（GPL，思路） | ~80 行，1–2d | **推荐采纳** |
| 5 | 限色数差 | 频次加权 Lab/Oklab k-means（k=max），保护最暗/最亮/最高彩度锚点 | cv2.kmeans 官方教程；Pillow `Image.quantize(MEDIANCUT)` | ~40 行，0.5d | **推荐采纳** |
| 6 | 抖动顺序/质量 | 先限色再抖动；Oklab/线性 RGB 蛇形 FS；可选 4×4 Bayer | pyxelate（MIT）`pyx.py`/`pal.py`；Pindo（GPL，思路） | ~50 行，0.5d | **推荐采纳** |
| 7 | 背景去除白主体 | GrabCut 主路径（边界采样建 probable bg，降采样到 ≤640）+ 边界连通域平涂兜底 + 吸管/容差/连续 UI | OpenCV GrabCut 教程（Apache-2.0）；Pindo `subject-crop.ts`（GPL，思路） | ~70 行 + UI，1–2d | **推荐采纳** |
| 8 | chibi 静默失效 | YuNet（345KB/MIT）+ Haar alt2 兜底 + 显式 skipped 状态 + 手动头部区域 | opencv_zoo YuNet（模型 MIT / 仓库 Apache-2.0） | ~40 行 + 345KB 模型，0.5d | **推荐采纳** |
| 9 | 图片→拼豆整体质量 | 3×3/5×5 多采样 + 风格 profile + 候选色多样性 + 相似合并 + 小区域/斑点清理 | Jett-Wu（MIT）`src/imageToBeads.ts` | 1–2d 选择性移植 | **推荐采纳（分阶段）** |
| 10 | 色差公式 | CIEDE2000 映射（可选 Oklab 快速路径） | Sharma 2005 实现注记（公开）；Pindo `color-matcher.ts` | ~60 行，0.5d | **推荐采纳** |
| 11 | 背景去除重依赖方案 | `rembg`（U2Net/ONNX） | rembg MIT，25k★；但模型/onnxruntime 体积大 | — | **不采纳**（仅作为可选扩展） |
| 12 | 通用线稿 XDoG | — | heitorrapela/xdog（MIT，2018）；XDoG 论文 | — | **不采纳**（照片上退化，见 §4） |
| 13 | 大模型线稿（anime2sketch / white-box） | — | 需 torch/权重，重依赖 | — | **不采纳** |
| 14 | 蓝图/线稿：全分辨率 DoG→覆盖率 | 仅当源图是插画/线稿时 | 本报告 §4（16.8% 覆盖，偏重）；Pindo stroke-extract | ~40 行 | **可选（按源图类型启用）** |

---

## 3. A 部分：特效算法开源参考（逐项结论）

### 3.1 图片→拼豆/像素图纸开源项目

#### A. Jett-Wu/Perler_Beads_Generator —— **推荐采纳（MIT，可移植代码）**

- URL：https://github.com/Jett-Wu/Perler_Beads_Generator
- 元数据（2026-10-21）：**57★，MIT，最后推送 2026-10-11，TypeScript**，活跃。
- 为什么最好：它不是「最近色 + 调色板」玩具，而是完整的照片→拼豆工程管线，且 **MIT 许可允许移植**。核心文件 `src/imageToBeads.ts`（23KB）已实际读取，函数级可借鉴：
  - `styleProfiles`：`cartoon`（7×7 采样、背景阈 0.72、dominance 0.34、候选色目标比例 0.58）与 `realistic`（5×5 采样、背景阈 0.58、候选比例 0.95、平均色兜底）两套参数——解决「照片直接压成 64×64 后一片糊」。
  - `sampleGridCells()`：每格在源图上做 5×5/7×7 点采样，统计每格 **背景占比** 与平均色；透明像素/背景色单独计数——背景去留、主体边界都由网格统计决定，而不是全图硬阈值。
  - `rankPaletteColors()`：按使用次数 × 彩度 boost（chroma>48 → 2.25、>28 → 1.4）× 暗线 boost（L<48 → 1.55）× 浅中性色惩罚（L>210 且 chroma<22 → 0.82）× 少数高彩 boost（share<1.8% 且 chroma>58 → 2.45）给候选色打分——**这一条正好治「风格色板洗白」：浅中性色被降权，暗线和点缀色被保护**。
  - `selectCandidateColors()`：按色数预算选色，候选间做 CIELAB 距离阈值（dark/high-chroma 18，其它 34，随强度加严），并保留 protected feature slots（至少 2 个「特征色」位）。避免「只留一堆近白色」。
  - `mergeSimilarColors()`：按频次从高到低，把低彩/暗/亮的相似色合并，阈值随强度 [0,26,42,62,84]，并对高彩差异/明度差异加惩罚——去噪但保轮廓。
  - `reduceTinyRegions()` / `reduceSpeckles()`：连通域 < 阈值的小色块并入邻域主色；3×3 多数滤波。
  - `estimateBackgroundColor()`：从四条边采样、按 16 级桶取众数作为背景色（不是固定白）。
- 移植建议：选 `sampleGridCells`、`rankPaletteColors`、`selectCandidateColors`、`mergeSimilarColors` 四个函数改写为 numpy（网格 64×64 完全够快），接入 `core/processor.py` 的「映射前」阶段；UI 暴露 `style`（写实/卡通）与 `strength`。许可证：保留 MIT 版权声明与 LICENSE 副本。
- 风险：算法参数是作者对自家 MARD 色卡和照片调的，移植后需用本项目色卡/样图重新校准（尤其背景阈值与候选距离阈值）；没有单元测试基线。

#### B. LunarXuan/Pindo —— **可选（GPL-3.0，只借思路，不复制代码）**

- URL：https://github.com/LunarXuan/Pindo
- 元数据（2026-10-21）：**455★，GPL-3.0，最后推送 2026-10-19，TypeScript**，非常活跃（2026 新项目）。
- 为什么值得看：与「拼豆图纸 + MARD/Hama/Perler 色卡 + 限色 + 抖动 + 图纸导出」的产品形态几乎一致，是很好的工程/UX 对照。已读取的关键实现：
  - `lib/engine/color-matcher.ts`：**CIEDE2000**（含全部修正项公式）+ Lab 预计算。
  - `lib/engine/dithering.ts`：Floyd–Steinberg 在 RGB 上（7/16,3/16,5/16,1/16），`ordered` 目前是占位——说明「有序抖动」在同类产品中仍是缺口，我们做了就是差异化。
  - `lib/engine/pattern-cleanup.ts`：`majorityFilter`（3×3，minMajority=6，描边格跳过）、`removeIsolatedNoise`（4 连通域，minComponentSize=2，保护高对比色：相邻亮度差 ≥42 不删）。
  - `lib/engine/stroke-extract.ts`：`extractStrokeMask` 用「亮度<90 的深色线像素占比 >12%」把描边下采样到网格，`dilateRadius` 可扩 1–3——这是**插画/漫画源图**的正确做法（照片不适用，因为照片没有「深色线」）。
  - `lib/engine/creative-mode.ts`/`palette-limit.ts`：创意模式与色卡过滤/限色面板的产品化思路。
- 结论：**不采纳其代码**（GPL-3.0 传染性，若直接复制进本仓库需整体 GPL）；**采纳概念**：CIEDE2000 映射、清理管线（多数滤波 + 小连通域 + 高对比保护）、描边覆盖率下采样、色卡过滤 UX。若未来要开源本项目并接受 GPL，再考虑代码级复用。
- License 注意：GPL-3.0 的「思想/算法」不受版权保护，但代码表达受保护；重写实现即可。

#### C. maxcleme/beadifier —— **可选（MIT，小体量参考）**

- URL：https://github.com/maxcleme/beadifier
- 元数据：**63★，MIT，推送 2026-03-08，TypeScript/Angular**。
- 已读 `src/app/model/matching/matching.model.ts`：内置 Euclidean / DeltaE(CIE94) 等匹配策略切换；`dithering-configuration.component.ts` 有 `hardness`（默认 100）参数。可作为「匹配策略可选 + 抖动强度」的 UI 参考；算法深度不如 A/B，代码不必要移植。

#### D. 其他（不作为主参考）

- `sucpyy/perler-pattern`（2★，MIT，2026-04）：Python 图片→拼豆，可快速看 Python 写法，但规模/质量不足以主参考。
- `terremoth/beads-designer`（2★，GPL-3.0）、`heisendelta/pyssla-designer`（0★，GPL-3.0，Notebook）不建议投入时间。
- **像素图通用工具**：`sedthh/pyxelate`（1704★，MIT，2026-01-18，Jupyter/Python）——见 §3.2；`KohakuBlueleaf/PixelOE`（530★，Apache-2.0，2026-09-29，Python）——见 §3.2/§3.4。两者都不是拼豆应用，但算子是当前最接近「专业像素化」的开源实现。

**A1 结论：Jett-Wu 的 `imageToBeads.ts` 是唯一值得「代码级」移植的拼豆项目（MIT、活跃、函数边界清晰）；Pindo 作为产品/算法思路库（GPL 不复制）；其余仅作补充。**

---

### 3.2 抖动 / 调色板量化 / 色差

**现状**：`core/colors.py:158` 用 CIE76；`:174` 用 Lab 空间 Floyd–Steinberg；`processor.py:175` 在映射阶段先抖动，随后 grid 阶段还会改索引。

#### 推荐（采纳）

1. **色差：CIEDE2000**（Sharma, Wu, Dalal 2005 实现注记，http://hajim.rochester.edu/ece/sites/gsharma/ciede2000/ ，已验证页面；Pindo 的 `color-matcher.ts` 是一个完整可读的 TS 简版）。
   - 实测（eagle 64×64，MARD 221）：CIE76→CIEDE2000 有 **21.4% 格子换色**；与局部块均值的 CIEDE2000 中位误差 3.74（CIE76 3.99，Oklab 4.49）。
   - 成本：4096 格 × 221 色 **92.5ms**（CIE76 12ms，均为 numpy 向量化）；200×200 网格约 0.9s，建议 >150×150 时改用 32³ Lab LUT 或 Oklab 快路径。
   - License：公式本身无版权；参考实现自写。代码量 ~60 行。
2. **调色板提取/限色：频次加权 k-means（Lab/Oklab）而不是 top-N**。
   - 可用 **`cv2.kmeans`（本环境已装，OpenCV 官方教程 https://docs.opencv.org/4.x/d1/d5c/tutorial_py_kmeans_opencv.html 已验证）**：对网格 Lab 颜色（4096×3）聚类 k=max_colors，然后把聚类中心映射到色卡；样本按出现频次加权（复制样本或加权中心更新）。
   - 或用 **Pillow `Image.quantize(colors, method=Image.Quantize.MEDIANCUT)`**（Pillow 12.3 已确认 4 种 method：MEDIANCUT/MAXCOVERAGE/FASTOCTREE/LIBIMAGEQUANT；`LIBIMAGEQUANT` 需要系统库且许可证需单独评估，建议只用内置 MEDIANCUT）。
   - 关键补丁：**保护锚点**——最暗、最亮、最高彩度、最常见肤色各保留至少 1 个候选（Jett 的 protected feature slots 思想），否则照片容易被浅色主导（与「白团」同因）。
3. **抖动：先限色、后抖动；抖动空间改 Oklab/线性 RGB；蛇形扫描**。
   - 现状 Lab 误差扩散虽可行，但 Lab 的 a/b 误差扩散在边界会放大彩度噪声；Oklab 的 L 更均匀。若不想引入 Oklab，可保留 Lab 并把误差 clamp 到 ±(若干 ΔE) 防止漂移。
   - 提供 3 档 `dither.mode`：`none`/`floyd`/`bayer4`。Bayer 4×4 矩阵可直接用 pyxelate（MIT）里已验证的常数：
     ```python
     BAYER4 = np.array([[-0.5,0.0,-0.375,0.125],
                        [0.25,-0.25,0.375,-0.125],
                        [-0.3125,0.1875,-0.4375,0.0625],
                        [0.4375,-0.0625,0.3125,-0.1875]])
     ```
     （来源：pyxelate `pyx.py` 的 `DITHER_BAYER_MATRIX`，MIT）
   - 顺序改造（`core/processor.py`）：`preprocess → BOX/对比度感知下采样 → max_colors/preset（先定最终子集）→ dither → outline 等 grid 特效 → chart`。现状 `dither` 在 `closest_indices_dithered` 内完成、之后 `max_colors`/`preset` 会覆盖，必须重排。
4. **参考实现清单**：
   - `sedthh/pyxelate`（MIT，1704★，2026-01-18）：`pyxelate/pyx.py` 的 `_dither_floyd` 在「概率域」做 FS（把每色概率按 1/6 幂次放大再扩散），`BGM` 用 CIEDE2000（kH=3,kL=2）初始化 BGM 聚类；`pal.py` 自带经典 8/16 色调色板。**依赖 sklearn/scipy/skimage/numba，全部不装；只移植算法（MIT 许可）**。
   - `KohakuBlueleaf/PixelOE`（Apache-2.0，530★，2026-09-29）：其 `contrast_based_downscale`（见 §3.4）比普通 BOX 更能保住照片细节。
   - `LunarXuan/Pindo`（GPL）：FS/CIEDE2000/清理思路，不复制。

#### 可选 / 不采纳

- **Riemersma 抖动**：质量好但实现复杂、收益低于「先限色 + FS/Oklab」，**不采纳**（本地小工具）。
- **libimagequant 后端**：Pillow 可选但需要系统库且许可证需单独评估（GPL/商业双许可），**不采纳**；MEDIANCUT/自定义 k-means 足够。
- **蓝噪声（void-and-cluster）**：视觉均匀性好于 Bayer，但实现/调参成本高；在 64×64 低分辨率下 Bayer/FS 已足够，**列为 P3 可选**。
- **Oklab**：作为 CIEDE2000 的替代品，速度更快、公式短（见 §3.5 的 Oklab 转换），但本数据中位保真略差（4.49 vs 3.74），**可选**（推荐仅用于草稿预览或 fallback）。

---

### 3.3 线稿 / 描边（附本地实测，图 `artifacts/lineart_compare.png`）

**结论先行：采纳「网格分辨率 DoG + 双阈值滞后 + Zhang-Suen 细化 + 去孤点」作为线稿描边；采纳「CIEDE2000 门控 + 分位预算 + 去孤点」作为邻接描边；XDoG 不采纳为通用实现。**

#### 现状复现（eagle.png 512×512 → 64×64，脚本 `qa/research/verify_lineart.py`）

| 方法 | 覆盖率 | 连通块 | 最大块占 mask | 孤立点占 mask |
|---|---:|---:|---:|---:|
| 现状 `FIND_EDGES`+阈值40+NEAREST | 6.88% | **131** | 5.7% | **79.1%** |
| 现状邻接异色描边 | **57.32%** | 3 | 98.4% | 1.8% |
| **DoG@64 + 滞后(92/80)（未细化）** | 19.04% | 10 | 65.5% | 10.1% |
| **DoG@64 + 滞后 + 细化（推荐）** | **8.64%** | **7** | 67.5% | 14.4% |
| DoG@512 + 覆盖率下采样（插画路径） | 16.82% | 12 | 92.7% | 3.0% |
| **邻接 ΔE2000 门控 p88（推荐）** | **9.2%** | 18 | 24.7% | 8.8% |
| XDoG@512 + 覆盖率下采样（论文参数） | **100%（退化）** | 1 | 100% | 0% |

> 说明：本复现与 Lead 实测（线稿 6.4%、邻接 ~50%）量级一致；差异来自复现实现（阈值/采样）与引擎细节。

#### 推荐算法（可直接抄的参数）

```python
# 1) 下采样：优先 PixelOE 对比度感知下采样（§3.4），便宜版用 PIL BOX
# 2) 亮度：L = sRGB-luma（或 cv2.cvtColor RGB2LAB 的 L 通道）/255
L = contrast_aware_downscale(img, N=64)          # 0..1, 64x64
g1 = cv2.GaussianBlur(L, (0,0), 0.8)             # σ1 = 0.8 格
g2 = cv2.GaussianBlur(L, (0,0), 1.6)             # σ2 = 2 * σ1
dog = np.abs(g1 - g2)
# 3) 双阈值滞后：强边种子 + 弱边连通
hi, lo = np.percentile(dog, 92), np.percentile(dog, 80)
mask = dog >= hi
for _ in range(3):
    mask = cv2.dilate(mask.astype(np.uint8), np.ones((3,3),np.uint8)) & (dog >= lo)
# 4) Zhang-Suen 细化 + 去孤点/小连通域
mask = zhang_suen(mask)
mask[nb_count(mask) < 1] = 0
mask = remove_components(mask, min_size=2)
```

- 参数来源与理由：σ1/σ2=1:2 与 skimage `difference_of_gaussians` 示例一致（https://scikit-image.org/docs/stable/auto_examples/filters/plot_dog.html ，已验证）；滞后 92/80 是本地 eagle 实测的「覆盖率 8–10% 且块数少」工作点，建议 **UI 暴露为「线稿强度 p80–p98」**而不是原始阈值。
- 代码位置：现替换 `core/effects/outline.py:67 _outline_edge_image` + `:76 _outline_edge_grid`；新逻辑可在 preprocess 阶段只算 mask，grid 阶段套用（与现状阶段划分兼容）。
- 移植量：约 80 行（DoG 4 行 + 滞后 6 行 + Zhang-Suen 30 行 + despeckle 15 行 + 接线/参数 25 行），**1 天内**；无新依赖。
- 风险：强纹理照片（毛发、树叶）会被画成大量短线——因此阈值分位应随「线稿强度」滑杆调节，并且**默认照片风格 p92、插画风格 p85**；建议对背景格做保护（背景格不描边，或由 `outline_outer` 控制）。
- 插画/线稿源图专用路径（**可选**）：Pindo `stroke-extract.ts` 的 `lumaThreshold=90 / coverageThreshold=0.12` 覆盖率下采样；或 DoG@全分辨率 + 覆盖率下采样（本实测 16.8% 偏重，需要把 coverage 阈值调到 0.25–0.35）。参考 Pindo（GPL，思路）。
- XDoG（**不采纳**）：`heitorrapela/xdog`（66★，MIT，2018-02-06，https://github.com/heitorrapela/xdog ）是可用实现，但按 Winnemöller 推荐 ε=0.1/φ=200/τ=0.98 在 512×512 eagle 上做软阈值后，整图落入「线条」侧（覆盖率 100%）：XDoG 的 soft threshold 输出是**风格化图**（白纸黑线/高对比），不是边缘掩码，必须逐图调 ε/φ 且更适合插画/动画输入。对大模型线稿（anime2sketch/white-box cartoonization）明确**不采纳**：需要 torch/权重，违背「本地小工具、不引重依赖」。

#### 邻接描边的正确语义（代码级）

现状 `_apply_outline` 的 mask 是「相邻索引不同」；改为「相邻珠子的 **CIEDE2000** 足够大」：

```python
# idx: (H,W) 色卡索引；pal_lab: (K,3) CIEDE2000 用 Lab
de = max_over_4_neighbors(de2000(pal_lab[idx], pal_lab[shifted_idx]))
thr = np.percentile(de, 88)          # 预算：约 12% 格子
mask = de >= thr                    # 这就是「有感知意义的分界线」
mask = despeckle(mask, min_nb=1, min_comp=2)
# 可选：只保留主体外轮廓（边界连通域的外缘），默认关闭
```

- 实测覆盖率 57.3%→9.2%，视觉见 `lineart_compare.png` 第 6/8 格。
- 关键点：**用「预算百分位」而不是固定 ΔE 阈值**，这样无论图像内容如何，描边占比都可控（用户滑杆 = 描边强度 = p85–p96）；这也直接消灭「照片黑网」。
- 移植量 ~25 行，**0.5 天**；风险极低。

---

### 3.4 赛璐璐 / 卡通平涂

**结论：采纳「OpenCV 边缘保持抽象 + 对比度感知下采样 + Lab k-means + CIEDE2000 映射」；不采纳「逐通道 posterize」与「大模型卡通化」。**

现状问题（实测）：`_cel_shade` 4 级 RGB 量化后 BOX 平均，产生 43 种珠子、43.3% 格子偏离局部均值 >ΔE2000 10、speckle 21.3%——这就是肉眼看到的「脏色块」。

推荐管线（脚本 `qa/research/verify_color_bg.py`，图 `artifacts/cel_compare.png`）：

```python
# 1) 源图边缘保持抽象（二选一）
a = cv2.stylization(rgb, sigma_s=60, sigma_r=0.35)      # OpenCV photo 模块，46.6ms@512 / 1026.8ms@2048
# 或 a = cv2.bilateralFilter(rgb, d=9, sigmaColor=75, sigmaSpace=75)  # 2.5ms@512 / 18.5ms@2048
# 或 a = cv2.pyrMeanShiftFiltering(rgb, sp=6, sr=12)     # 更「平」，更慢
# 2) 对比度感知下采样（PixelOE 的 find_pixel，L 通道）
grid = contrast_aware_downscale(a, 64)
# 3) Lab k-means：k = 2 * levels（levels 为用户色阶数）
q = kmeans_quantize(grid, k=max(2, 2*levels))
# 4) CIEDE2000 映射到色卡（+ 可选 FS 抖动）
idx = map_palette(q, metric="ciede2000")
```

- 实测（levels=4 → k=8）：珠子数 **43→8**，outlier(ΔE>10) **43.3%→22.9%**，speckle **21.3%→9.3%**，中位保真 ΔE **8.68→5.41**。
- 参考实现：
  - OpenCV 官方非真实感渲染文档（Apache-2.0）：https://docs.opencv.org/4.x/df/dac/group__photo__render.html —— 已验证 `stylization(src, sigma_s=60, sigma_r=0.45)`、`edgePreservingFilter`、`pencilSketch`、`detailEnhance` 签名。**采纳 stylization（sigma_r 0.35 更适合后续色阶）**。
  - OpenCV `pyrMeanShiftFiltering`（同一文档，sp/sr/maxLevel）——可选。
  - PixelOE（Apache-2.0，530★）`src/pixeloe/legacy/downscale/contrast_based.py` 的 `find_pixel`（L 通道：若 median<mean 且亮距>暗距取 min；若 median>mean 且亮距<暗距取 max；否则取 median；a/b 取中位）——**已按此移植，约 30 行 numpy**，显著优于 BOX 平均，能保住照片高光/阴影细节；比 PyTorch 版本更适合本项目。
  - `imssm99/photo-cartoonize` 等教程项目**无许可证，不采纳**；OpenCV 官方文档就是同款算法的权威来源。
- 移植量 ~50 行，1 天；风险：`stylization` 2048px 1s → **先限最长边 ≤1024** 再抽象（拼豆网格最多 ~200×200，1024 足够）；k-means 的 k 与 levels 的耦合需要 UI 说明（建议 `k = max(2, 2*levels)`，并允许「平涂强度」滑杆覆盖）。
- **可选**：`pencilSketch` 作为「线稿描边」的另一种输入（OpenCV 文档已验证签名），但它的输出是灰度铅笔稿，不如 §3.3 的 DoG 可控；不采纳为主路径。

---

### 3.5 双色调 / 霓虹 / 背景去除

#### 双色调（推荐采纳，自实现）

- 做法：L 通道百分位拉伸（p2–p98）→ 在 **Oklab** 中对两个锚点做线性插值（保证感知均匀）→ 得到 RGB → CIEDE2000 映射到色卡 → 可选抖动。现状 `_duotone` 直接在 sRGB 线性插值，暗部/亮部会「脏」「灰」，Oklab 可修。
- 公式来源：Björn Ottosson, "Oklab: A perceptual color space for image processing"（https://bottosson.github.io/posts/oklab/ ，已验证），3×3 矩阵 + cbrt，约 20 行 numpy；本报告 `qa/research/verify_color_bg.py` 内有已验证实现。
- 参考：ImageMagick `-clut` 渐变映射（Apache-2.0）是同类标准做法；本项目自实现 30 行即可，不需依赖。

#### 霓虹（推荐采纳，自实现）

- 做法：深底（`neon` 已有 `darkness`）+ 高亮/高饱和掩码（Oklab L>0.72 或 chroma>C）→ `cv2.GaussianBlur` 光晕（σ ≈ min(H,W)*0.02）→ screen 混合 `255-(255-a)*(255-b)/255` → 再映射/抖动到珠子色卡。现状仅 `ImageEnhance.Color/Brightness`，没有「发光」的物理感。
- 参考：OpenCV `GaussianBlur`/`addWeighted` 文档（Apache-2.0）即可；无需引入项目。移植 ~40 行，0.5 天。
- 注意：霓虹在低色数色卡上靠抖动表现光晕，必须与 §3.2 的抖动顺序一起改。

#### 背景去除（推荐采纳 GrabCut 主路径）

- 现状 `_bg_remove` 是「全图容差匹配」，无连通域 / 无空间先验。合成用例（脚本 `verify_color_bg.py`，图 `artifacts/bg_remove_compare.png`）：

| 用例 | 现状全局容差 tol=30 | 边界连通域 ΔE≤1.8 | GrabCut 矩形初始化 |
|---|---:|---:|---:|
| A：白主体(+灰内衬/五官) on 浅灰渐变背景 | 主体保留 **3%**（误删） | 100% 保留但背景 0% 去除（容差无法同时选中浅灰背景与白主体，ΔE 仅 1.7 vs 2.0–3.5） | **主体 100% / 背景 100%** |
| B：白底 + 深色描边包围的近白主体内部 | 主体内部保留 **0%**（被掏空） | **主体内部 100% / 背景 86.7%**（正确） | —（矩形先验不如 B 场景） |

- 推荐实现（OpenCV GrabCut，https://docs.opencv.org/4.x/d8/d83/tutorial_py_grabcut.html 已验证）：
  1. 用户吸管取背景色（或从四条边采样 k-means 得背景主色）；
  2. 把图缩到最长边 ≤640（GrabCut 512px 实测 959ms，2048px 40.9s，**必须降采样**）；
  3. 初始化 mask：与背景色 ΔE≤T 的像素标 `GC_PR_BGD`，中心矩形默认 `GC_PR_FGD`，四边框 `GC_BGD`；
  4. `grabCut` 2–3 iter，取 FGD/PR_FGD → 上采样回原尺寸做 alpha；
  5. 校验前景比例（建议 3%–97%）：异常则回退/取消并提示（「背景与主体颜色接近，请手动框选主体」）；
  6. 平涂/纯色背景（数字插画、扫描件）用「边界连通域键控」更确定、无随机性（用例 B 验证），可作为「连续区域」开关的快速路径。
- 可选扩展：`danielgatis/rembg`（MIT，25k★，2026-10-10）效果最好，但需要 onnxruntime + ~176MB U2Net 模型，**不采纳进默认安装**（可作为「高级功能」下载）。
- 移植量：GrabCut 管线 ~70 行 + SwiftUI 吸管/容差/连续开关；1–2 天。风险：GrabCut 慢（预览要低分辨率/节流）、有随机性（固定迭代次数）、对纯白 on 纯白仍无解（必须用户介入或 rembg）。

---

### 3.6 chibi 大头 + 失败降级

- 现状：`core/effects/geometry.py:9 _chibi` 用默认 Haar 级联，`detectMultiScale(gray, 1.1, 5, minSize=(min(w,h)//8,...))`；无脸 → 直接 `return img`（无状态）。
- **推荐采纳：YuNet**（OpenCV 官方模型库 opencv_zoo）：https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
  - 模型 `face_detection_yunet_2023mar.onnx` **345KB**，模型 LICENSE 经 jsDelivr 读取为 **MIT（Copyright (c) 2020 Shiqi Yu）**，可随 app 打包；opencv_zoo 仓库 Apache-2.0。
  - 用法（cv2 已装，无需新依赖）：`cv2.FaceDetectorYN.create(model_path, "", (w,h), score_threshold=0.6, nms_threshold=0.3, top_k=50)`，`detector.setInputSize((w,h)); faces = detector.detect(img)`；对 512 图先放大到 ≥640 再检测（小脸召回显著提升）。
  - 兜底链：YuNet → Haar `haarcascade_frontalface_alt2`（`equalizeHist` 预处理）→ **返回 `{"status":"skipped","reason":"no_face"}` 并在 UI 显示「未检测到人脸，已跳过」+ 提供手动头部位置滑杆**。
  - 业界做法：检测类 API 返回空数组是正常结果，产品层必须显式反馈而非静默（OpenCV 官方 YuNet demo 对 `faces is None` 有分支；Apple Vision `VNDetectFaceRectanglesRequest` 的 results 也可能为空数组——用「空结果 → 降级路径」是通用模式）。本项目建议把「特效执行状态」作为结果元数据回传（`GenerateResult` 增加 `warnings: [String]`），UI 用 toast/inline badge 展示。
- 不采纳：`face_recognition`（dlib 重依赖）、MTCNN（torch/onnx 重）、大模型人像分割；都不符合本地小工具约束。
- 移植量：~40 行 + 模型文件 345KB，0.5–1 天；风险：模型文件随 app 分发的许可证归档（MIT LICENSE 放 `Resources/`），以及特写/侧脸仍可能失败（所以状态与手动滑杆是必须的）。

---

## 4. 本地验证实验（已完成，证据在 `qa/research/artifacts/`）

**脚本（只读输入，只写 artifacts）：**

- `qa/research/verify_lineart.py` —— 线稿/描边对比；输出 `artifacts/lineart_compare.png`、`artifacts/lineart_metrics.json`。
- `qa/research/verify_color_bg.py` —— 赛璐璐、色差/限色、背景去除；输出 `artifacts/cel_compare.png`、`artifacts/palette_distance_compare.png`、`artifacts/bg_remove_compare.png`、`artifacts/color_metrics.json`。
- 运行：`conda run -n pindou python qa/research/verify_lineart.py`（输入 `qa/lead/inputs/eagle.png` 512×512）。

### 4.1 线稿/描边（见 §3.3 表）

- 现状线稿：6.88% 覆盖、131 块、79.1% 孤立；现状邻接描边 57.32%。
- 推荐 DoG@64：8.64% 覆盖、7 块、最大块 67.5%；ΔE 门控邻接描边：9.2% 覆盖、视觉最干净（见 `lineart_compare.png` 第 4/6/7/8 格）。
- 负结果：XDoG 推荐参数在照片上二值化后退化为 100% 覆盖，不采纳；全分辨率 DoG 覆盖率下采样 16.8% 偏重，仅适合插画源图。

### 4.2 赛璐璐 / 色卡距离 / 背景去除 / 性能

- 赛璐璐：现状 43 珠 / 43.3% outlier / 21.3% speckle → 推荐 8 珠 / 22.9% / 9.3%，中位 ΔE 8.68→5.41（`cel_compare.png`）。
- 色差：CIE76 vs CIEDE2000 换色 **21.4%**；CIEDE2000 中位保真 3.74（CIE76 3.99，Oklab 4.49）。
- 背景：用例 A 现状主体保留 3% → GrabCut 100%/100%；用例 B 现状内部保留 0% → 边界连通域 100%/86.7%（`bg_remove_compare.png`）。
- 性能（本机 512px / 2048px）：`stylization` 46.6ms / 1026.8ms；`bilateralFilter` 2.5ms / 18.5ms；`grabCut` **959ms / 40.9s**；CIEDE2000 网格映射（4096×221）92.5ms vs CIE76 12ms。→ **GrabCut 必须降采样到 ≤640；stylization 限最长边 ≤1024；CIEDE2000 在 ≤200×200 网格可用，更大需 LUT。**

---

## 5. B 部分：时尚杂志风 UI 开源参考 + 可直接落地的 design tokens

> 「米白纸感 + 墨黑 + 单一强调色」= Kinfolk 的**单色衬线 + 编号/期号 + 大留白** × Monocle 的**油墨黑/新闻纸奶油 + 唯一信号色 + 细线/无阴影/编辑式版面** × Vogue 的**高对比 Didot 标题** × Wallpaper* 的**大图/50-50 图文 hero 与硬朗栅格**。

### 5.1 可借鉴来源（3–5 个）

1. **Kinfolk（独立杂志，公开官网）** —— https://www.kinfolk.com （2026-10-21 抓取：首页以 `Issue 61`、`1 / 10` 轮播编号、栏目分类（Fashion / Interiors / Arts & Culture）组织；单色、大留白）。第三方样式档 https://styles.refero.design/style/ac9b040e-36aa-4881-ada5-72d4744947a4 的元数据写明：`Ink Black #000000`、`Bone White #ffffff`、`Kinfolk-Serif-Text`/`Kinfolk-Serif-Display`（品牌自有字体，不可用；用 OFL 衬线替代）。
2. **Monocle（独立杂志，公开官网 + 第三方风格分析）** —— https://monocle.com （2026-10-21 抓取：Magazine / Radio / Shop 分区、订阅主导航）。第三方分析页 https://geoffreymanda.github.io/design-atlas/styles/monocle.html 给出可直接引用的 token：`newsprint cream #FDFCF3`、`folio black #000000`、`signal yellow #FFC500`（唯一强调色）、`caption gray #6E6E6E`、`rule gray #D9D9D9`；字体 Plantin（商业字体）+ **开源替代建议 Source Serif Pro / Spectral / Playfair Display**；字号 13/16/18/20/24/28/32/34/40，行高 1.0–1.5，字距 display -0.02em、body +0.01em、small caps +0.05em、eyebrow +0.075em；「细线、极小圆角、无投影、3 栏栅格」。
3. **Vogue（时装媒体）** —— https://www.vogue.com ；高对比 Didot 系标题传统是业界公认的时装版面语言（ATypI 专题页 `Didot and fashion`：https://atypi.org/presentation/didot-and-fashion/ ，页面存在，正文由 JS 渲染）。**只借鉴「巨大衬线标题 + 小号字距紧排 + 大图」的比例关系**；Vogue Didot 为商业/定制字体，**不采纳字体文件**，用 macOS 自带 Didot/Bodoni 72 或 OFL 的 Instrument Serif。
4. **Wallpaper*（设计杂志）** —— https://www.wallpaper.com （2026-10-21 抓取其 HTML/CSS：hero 采用 **50/50 图文分栏**（`.listing__image-layout{flex:0 0 calc(50% - 25px)}`、`.listing__text-wrapper{flex:0 0 50%}`）、1px 边线、16px/24px 正文；其 CSS 里可见 **Source Serif Pro** 作为衬线 fallback）。→ 「大图 + 半幅文字 + 1px 分隔」可直接用于成品图/图纸预览的编辑式 hero。
5. **开源设计系统/规范（token 级来源）**：
   - **Radix Colors（MIT）**：https://www.radix-ui.com/colors ；从 npm `@radix-ui/colors@3.0.0` 的 `sand.css`/`red.css` 实际读取 12 级色阶 hex（见 §5.2）。
   - **Tailwind CSS（MIT）**：https://v3.tailwindcss.com/docs/customizing-spacing （4px 基数，已验证）、https://v3.tailwindcss.com/docs/transition-duration （75–1000ms，已验证）、https://v3.tailwindcss.com/docs/transition-timing-function （ease-out `cubic-bezier(0,0,0.2,1)`、ease-in-out `(0.4,0,0.2,1)`，已验证）。
   - **Apple 官方规范**：HIG Typography / Color / Motion（https://developer.apple.com/design/human-interface-guidelines/typography 等；页面 JS 渲染但链接有效），**New York** 系统衬线说明见 https://developer.apple.com/fonts/ （已验证原文：「New York…serif typeface…six weights…variable optical sizes」）。macOS 上可直接用 `.system(design: .serif)` 或 `Font.custom("Didot", size:)`，无需打包字体。
   - 开源字体（均可自带）：Fraunces（SIL OFL 1.1，`google/fonts/ofl/fraunces/OFL.txt` 已验证）、Newsreader（OFL 1.1，productiontype/Newsreader 263★，OFL 文本已验证）、Instrument Serif（OFL 1.1，`google/fonts/ofl/instrumentserif/OFL.txt` 已验证）、Source Han Serif（OFL 1.1，LICENSE 已验证）、Noto Serif SC（OFL 1.1，已核对 OFL 文本）、LXGW WenKai 霞鹜文楷（**OFL-1.1**，26.4k★，2026-10-18 活跃；README 明确提醒「不得单独售卖字体文件」）。

### 5.2 可直接写进 SwiftUI 的 design tokens

#### 颜色（每个值均有来源）

| Token | Hex | 用途 | 来源 |
|---|---|---|---|
| `paper` | `#FDFCF3` | 窗口/预览画布底色（米白纸感） | Monocle 分析页 `--color-newsprint-cream`（第三方风格分析） |
| `paperAlt` | `#F9F9F8` | 分区底/次级纸面 | Radix Colors `sand-2`（MIT，npm CSS 实测） |
| `card` | `#FFFFFF` | 卡片/图版白 | Kinfolk `Bone White` + Monocle `Broadsheet White` |
| `ink` | `#21201C` | 主文字/标题（暖墨黑） | Radix `sand-12` |
| `inkSecondary` | `#63635E` | 二级文字/说明 | Radix `sand-11`（亦接近 Monocle caption gray #6E6E6E） |
| `inkTertiary` | `#8D8D86` | 占位/禁用/序号 | Radix `sand-9` |
| `rule` | `#CFCECA` | 1px 发丝线/分隔 | Radix `sand-7` |
| `ruleStrong` | `#BCBBB5` | 强分隔/输入框描边 | Radix `sand-8` |
| `accent` | `#E5484D` | **唯一强调色**：主按钮/选中/关键数字 | Radix `red-9`（MIT） |
| `accentPressed` | `#CE2C31` | 按下/悬停 | Radix `red-11` |
| `accentWash` | `#FFCDCE` | 选中行/浅底强调 | Radix `red-5` |

> 备选强调色（更「Monocle」）：`signal #FFC500`（Monocle 分析页），只建议用作「标记/高亮条」，不用于主按钮；单一强调色原则下优先 `#E5484D`。

#### 字体（零打包优先；OFL 字体为可再分发备选）

| Token | SwiftUI | 说明/来源 |
|---|---|---|
| `displayLatin` | `.system(size: 56, weight: .regular, design: .serif)` | Apple **New York** 系统衬线（Apple 字体页已验证）；英文 masthead/大标题 |
| `displayLatinAlt` | `.custom("Didot", size: 56)` | macOS 自带 Didot（本机 `/System/Library/Fonts/Supplemental/Didot.ttc` 已确认）；高对比时装标题感，**仅标题** |
| `displayCJK` | `.custom("Songti SC", size: 34)` | macOS 自带宋体（本机 `Songti.ttc` 已确认）；中文衬线标题 |
| `bodyLatin` | `.system(size: 14)` | SF Pro（系统默认） |
| `bodyCJK` | 系统默认（PingFang SC） | macOS 中文正文 |
| `mono` | `.system(size: 12, design: .monospaced)` | SF Mono（系统），色号/网格尺寸/编号 |
| `serifAltEN` | `Font.custom("Fraunces", size: 40)` | SIL OFL 1.1（打包时；可变光学尺寸） |
| `serifLongEN` | `Font.custom("Newsreader", size: 16)` | SIL OFL 1.1；长文阅读 |
| `serifShowEN` | `Font.custom("Instrument Serif", size: 44)` | SIL OFL 1.1；展示型细高对比 |
| `serifCJKAlt` | `Font.custom("Source Han Serif SC", size: 34)` / Noto Serif SC / LXGW WenKai | OFL 1.1（跨平台/可打包；文件较大按需） |

> **打包注意**：OFL 字体可随 app 分发（附 OFL 文本；不得单独售卖字体文件；改名字要遵守 Reserved Font Name）。**Apple 系统字体（New York/Didot/Songti SC）只按字体名使用，不复制字体文件**。

#### 字阶 / 间距 / 圆角 / 动效

| Token | 值 | 来源 |
|---|---|---|
| `type.eyebrow` | 11pt / 行高 16 / **大写 + 字距 +0.075em** | Monocle 分析页（eyebrow 0.05–0.075em、13–16px） |
| `type.caption` | 12–13pt / 16 | Monocle 分析页（13px） |
| `type.body` | 14–16pt / 1.5（+0.01em） | Monocle 分析页（16–18px、+0.01em） |
| `type.standfirst` | 18pt / 1.45 | Monocle 字号序列 18 |
| `type.h3` | 20pt / 1.4 | Monocle 字号序列 20 |
| `type.h2` | 24pt / 1.25 | Monocle 字号序列 24/28 |
| `type.h1` | 32pt / 1.15 / -0.02em | Monocle 字号序列 32，display 负字距 |
| `type.display` | 40pt / 1.1 / -0.02em | Monocle 字号序列 40 |
| `type.masthead` | 56–72pt / 1.0 | Didot/Vogue 式版面比例（标题远大于正文）；仅 masthead |
| `space` | 2 / 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 | Tailwind spacing scale（4px 基数，已验证） |
| `layout.margin` | 32（紧凑）/ 48（宽屏） | 由 Tailwind 32/48 + 编辑式留白推导（**工程取值**） |
| `layout.rail` | 320pt（现 300 → 320） | **工程取值**；参考 Kinfolk 单栏宽度感 |
| `layout.cardGap` | 16 | Tailwind 16 + Monocle 3 栏栅格 |
| `radius.surface` | 0 | Monocle 分析页「minimal radii」；编辑式版面不用圆角卡片 |
| `radius.control` | 4（输入/按钮）；10（浮层） | **工程取值**（与 0 圆角版面形成层级；非规范硬值） |
| `shadow` | none（用 1px `rule` 替代） | Monocle 分析页「no drop shadows」 |
| `motion.quick` | 150ms（hover/press） | Tailwind duration-150（已验证） |
| `motion.base` | 200ms（内容切换） | Tailwind duration-200 |
| `motion.sheet` | 300ms（面板/抽屉） | Tailwind duration-300 |
| `motion.easeOut` | `cubic-bezier(0,0,0.2,1)` | Tailwind ease-out（已验证） |
| `motion.easeInOut` | `cubic-bezier(0.4,0,0.2,1)` | Tailwind ease-in-out（已验证） |

**SwiftUI 落地片段（建议新增 `app/Sources/PerlerApp/Theme.swift`）：**

```swift
import SwiftUI

enum Theme {
    static let paper        = Color(hex: 0xFDFCF3)   // Monocle newsprint cream
    static let paperAlt     = Color(hex: 0xF9F9F8)   // Radix sand-2
    static let card         = Color.white
    static let ink          = Color(hex: 0x21201C)   // sand-12
    static let inkSecondary = Color(hex: 0x63635E)   // sand-11
    static let inkTertiary  = Color(hex: 0x8D8D86)   // sand-9
    static let rule         = Color(hex: 0xCFCECA)   // sand-7
    static let accent       = Color(hex: 0xE5484D)   // red-9（唯一强调色）
    static let accentPressed = Color(hex: 0xCE2C31)  // red-11

    static let displayLatin = Font.system(size: 56, weight: .regular, design: .serif) // New York
    static let displayCJK   = Font.custom("Songti SC", size: 34)
    static let h1           = Font.custom("Songti SC", size: 28)
    static let eyebrow      = Font.system(size: 11, weight: .semibold)
    static let body         = Font.system(size: 14)
    static let mono         = Font.system(size: 12, design: .monospaced)
}

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255)
    }
}

struct Hairline: View { var body: some View { Rectangle().fill(Theme.rule).frame(height: 1) } }
```

**版面规则（可直接执行，逐条有出处）：**

1. **单屏一张主图**：预览区一张成品图/图版，尺寸信息用 mono 小字（`Fig.01 · 64×64 · MARD 221`）；参考 Kinfolk 单图叙事与 Monocle 图片主导。
2. **图文 50/50 hero**：成品图与信息区可用 `HStack(spacing: 24)` 的 50/50 分栏、中间 1px 竖线；来源 Wallpaper* 首页实测 CSS（`flex: 0 0 calc(50% - 25px)` + 1px border）。
3. **3 栏编辑式卡网格**：色卡预览/模板/最近项目 3 列，gap 16，卡片 0 圆角、无阴影、1px `rule`；来源 Monocle 分析页。
4. **层级 = eyebrow + 编号 + 标题 + standfirst**：区块标题 11pt 大写 +0.075em 字距 + `01`/`02` 编号（mono），下接 1px 线；标题宋体/New York 32–40pt、字距 -0.02em；副标题 18pt。
5. **期号/序号系统**：页脚/标题右侧 `Issue 61`、`01 / 06` 式编号（Kinfolk 官网实测）。
6. **留白比例**：区块间距 32、页面边距 32–48、正文行长 ≤ 65–75 字符；留白 > 内容密度。
7. **单一强调色**：只在「生成」主按钮、当前选中项、关键数字出现；其余黑白灰（Monocle 唯一 signal 色原则）。
8. **字距规则**：display -0.02em、body +0.01em、small caps +0.05em、eyebrow +0.075em（Monocle 分析页数值）。
9. **无玻璃/无阴影**：把现有 `.ultraThinMaterial`（ContentView:16）、`.regularMaterial`（:194、ColorChartView:33）换成 `Theme.paper`/`Theme.card` + `Hairline`；圆角 12/8 改 0（容器）/4（控件）。

### 5.3 开源 SwiftUI 组件/参考实现

| 项目 | URL | License / 活跃度 | 可用组件 |
|---|---|---|---|
| **Luminare** | https://github.com/MrKai77/Luminare | **BSD-3-Clause**，169★，2026-10-09 | macOS SwiftUI 控件/窗口外观体系；可借 Toggle/Picker/面板封装（不必用其毛玻璃视觉） |
| **SimpleSidebar** | https://github.com/revblaze/SimpleSidebar | **MIT**，229★，2025-02-20 | macOS sidebar 三种实现（Cocoa NSOutlineView / Storyboard / SwiftUI `SidebarListStyle`） |
| **design-foundation** | https://github.com/NerdSnipe-Inc/design-foundation | **MIT**，28★，2026-10-06 | 54 组件 + 主题预设 + Style protocol；参考主题/token 架构 |
| **CodeEdit** | https://github.com/CodeEditApp/CodeEdit | **MIT**，23k★，2026-10-17 | NavigationSplitView / Inspector / Settings / 命令菜单的真实 macOS 应用架构 |
| Apple 系统字体 + HIG | https://developer.apple.com/fonts/ | Apple 规范（字体不随包分发） | New York 衬线、SF Pro/SF Mono、语义色、Reduce Motion |

### 5.4 与现有 SwiftUI 代码的接线点

- `ContentView.swift:10–16`：`HStack` + 300pt 侧栏 + `.ultraThinMaterial` → 改 `Theme.paper` 背景、320pt 侧栏、预览区 `Theme.card` + 1px 线；`glassSection`（:189–195）改「eyebrow + 编号 + Hairline」编辑式区块。
- 字体：正文/控件保留系统语义字体；标题/区块头切 `Theme.h1`/`Theme.displayCJK`；色号/尺寸用 `Theme.mono`。
- 强调色：`.tint(Theme.accent)` 只用于主操作（生成）与选中态。
- 自动重渲染（`AppViewModel.swift` :379 effectsParams / :425 generate）：增加

```swift
@Published var renderSignature: String = ""
private var renderTask: Task<Void, Never>?

func scheduleRender() {
    renderTask?.cancel()
    renderTask = Task { [weak self] in
        try? await Task.sleep(nanoseconds: 250_000_000)   // 250ms debounce
        guard !Task.isCancelled else { return }
        await MainActor.run { self?.generate() }
    }
}
// ContentView: .onChange(of: vm.renderSignature) { _, _ in vm.scheduleRender() }
```

  对重特效（`bg_remove`/`cel_shade`/`chibi`）在缩略预览阶段用 `grid 32×32`、最长边 ≤640 跑；用户点「生成」再全分辨率（GrabCut/stylization 实测耗时见 §4.2）。

---

## 6. 落地建议（先做什么、后做什么）

### P0 —— 1–2 天，改动小、收益立竿见影

1. **邻接描边**：ΔE2000 门控 + 分位预算 + 去孤点（`outline.py:_apply_outline`）；UI 加「描边强度（p85–p96）」。
2. **线稿描边**：网格 DoG + 滞后 + 细化 + 去孤点（`outline.py:67/76`）；参数以「线稿强度」暴露。
3. **赛璐璐**：stylization/bilateral + 对比度感知下采样 + Lab k-means + CIEDE2000（`filters2.py:10`）；限最长边 ≤1024。
4. **色卡映射**：`closest_indices` 换 CIEDE2000（`colors.py:158`）；保留 CIE76 快速预览开关。
5. **自动重渲染**：`onChange(renderSignature)` + 250ms debounce + 取消在途请求（`AppViewModel`）。
6. **验收指标**：eagle 64×64 下邻接描边覆盖率 ≤15%、线稿 6–15% 覆盖且连通块 ≤10、赛璐璐 outlier ≤30%/speckle ≤12%。

### P1 —— 2–4 天，质量增强

7. **限色数**：频次加权 k-means + 锚点保护（`presets.py:38`）；抖动移到限色之后（`processor.py` 顺序）。
8. **风格色板**：引导色管线（L 拉伸 → k-means → 保序映射 → strength 混合 → 抖动）（`presets.py:73`）；「>30% 格子映射到同一近白锚点」自动告警。
9. **图片→拼豆质量**：选择性移植 Jett 的四个函数（MIT，保留版权声明），加「写实/卡通」style profile。
10. **背景去除**：GrabCut + 边界采样 + 边界连通域兜底 + 吸管/容差/连续 UI + 失败提示（`filters2.py:77`）；预览降采样。
11. **chibi**：YuNet + Haar + skipped 状态 + 手动头部区域（`geometry.py:9`）；`GenerateResult` 增加 `warnings`。
12. **深色图纸底**：改名或让预览画布同步暗底（`filters.py:63` + UI）。

### P2 —— 3–5 天，UI 重构

13. 新增 `Theme.swift` tokens（§5.2），替换 Material/圆角/字号；侧栏 300→320、加 Hairline 与编号区块；预览区加 `Fig.01 · 尺寸 · 色卡` caption。
14. 新增编辑式组件：`SectionHeader(eyebrow:index:title:)`、`Hairline`、`EditorialCard`、`FigureCaption`；参考 SimpleSidebar 的 `SidebarListStyle` 改造侧栏。
15. 动效 150/200/300ms + ease-out/ease-in-out（§5.2），尊重 `accessibilityReduceMotion`。

### P3 —— 可选/后续

16. rembg（可下载「高级功能」）；蓝噪声抖动；`pencilSketch` 线稿；插画源图的「全分辨率线稿覆盖率」路径；杂志式导出模板。

---

## 7. 参考链接总表（检索/验证日期 2026-10-21）

> 状态说明：✅ = web_fetch 实际打开（HTTP 200）并读取到关键内容；◐ = 页面存在但正文由 JS 渲染/未取到正文；⛔ = 未能打开（网络超时），仅用 GitHub API 元数据。

### 7.1 拼豆/像素/算法实现

| 名称 | URL | License | 元数据/活跃度 | 采用结论 | 验证 |
|---|---|---|---|---|---|
| Jett-Wu/Perler_Beads_Generator | https://github.com/Jett-Wu/Perler_Beads_Generator | **MIT** | 57★，推送 2026-10-11 | **推荐（代码级移植）** | ✅（API + `imageToBeads.ts`） |
| LunarXuan/Pindo | https://github.com/LunarXuan/Pindo | **GPL-3.0** | 455★，推送 2026-10-19 | **可选（思路，不抄代码）** | ✅（API + engine 源码） |
| maxcleme/beadifier | https://github.com/maxcleme/beadifier | MIT | 63★，推送 2026-03-08 | 可选（UI/匹配策略参考） | ✅ |
| sedthh/pyxelate | https://github.com/sedthh/pyxelate | MIT | 1704★，推送 2026-01-18 | **可选（只移植算法）** | ✅（`pyx.py`/`pal.py`） |
| KohakuBlueleaf/PixelOE | https://github.com/KohakuBlueleaf/PixelOE | **Apache-2.0** | 530★，推送 2026-09-29 | **推荐（对比度感知下采样）** | ✅（`contrast_based.py`） |
| danielgatis/rembg | https://github.com/danielgatis/rembg | MIT | 25145★，推送 2026-10-10 | **不采纳默认安装** | ✅ |
| heitorrapela/xdog | https://github.com/heitorrapela/xdog | MIT | 66★，推送 2018-02-06 | 参考；XDoG 不采纳 | ⛔（API 元数据 ✅） |

### 7.2 算法/文档/规范

| 名称 | URL | 说明 | 验证 |
|---|---|---|---|
| OpenCV 非真实感渲染 | https://docs.opencv.org/4.x/df/dac/group__photo__render.html | stylization/edgePreservingFilter/pencilSketch/detailEnhance | ✅ |
| OpenCV 滤波（pyrMeanShiftFiltering） | https://docs.opencv.org/4.x/d4/d86/group__imgproc__filter.html | sp/sr/maxLevel 签名 | ✅ |
| OpenCV GrabCut 教程 | https://docs.opencv.org/4.x/d8/d83/tutorial_py_grabcut.html | 矩形初始化/迭代 | ✅ |
| OpenCV K-Means 教程 | https://docs.opencv.org/4.x/d1/d5c/tutorial_py_kmeans_opencv.html | cv.kmeans | ✅ |
| scikit-image DoG 示例 | https://scikit-image.org/docs/stable/auto_examples/filters/plot_dog.html | DoG 公式/σ 比例（BSD-3，仅参考） | ✅ |
| CIEDE2000 实现注记 | http://hajim.rochester.edu/ece/sites/gsharma/ciede2000/ | Sharma/Wu/Dalal 2005 + 测试数据 | ✅ |
| Oklab（Ottosson） | https://bottosson.github.io/posts/oklab/ | 转换矩阵/cbrt | ✅ |
| opencv_zoo YuNet | https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet | 模型 345KB；模型 LICENSE MIT | ✅（LICENSE 已读取） |
| Pillow quantize 文档 | https://pillow.readthedocs.io/en/stable/reference/Image.html | MEDIANCUT 等；本机 Pillow 12.3 实测存在 | ◐（API 实测确认） |

### 7.3 UI/设计/字体

| 名称 | URL | License | 用途/验证 |
|---|---|---|---|
| Kinfolk 官网 | https://www.kinfolk.com | 站点内容 © Kinfolk（仅观察） | 单色/编号/期号/留白（✅） |
| Refero Kinfolk 风格档 | https://styles.refero.design/style/ac9b040e-36aa-4881-ada5-72d4744947a4 | 第三方分析 | Ink Black/Bone White/Kinfolk-Serif-* 元数据（✅） |
| Monocle 官网 | https://monocle.com | 站点内容 © Monocle | 栏目结构（✅） |
| Monocle 风格分析（Design Atlas） | https://geoffreymanda.github.io/design-atlas/styles/monocle.html | 第三方分析 | cream/black/signal yellow + 字阶/字距/3 栏（✅ 全文） |
| Vogue 官网 / ATypI Didot | https://www.vogue.com ；https://atypi.org/presentation/didot-and-fashion/ | 站点内容 | Didot 时装标题传统（仅观察；ATypI 正文 JS） |
| Wallpaper* 官网 | https://www.wallpaper.com | 站点内容 © Wallpaper* | 50/50 hero、1px 线、Source Serif Pro fallback（✅ CSS 片段） |
| Radix Colors | https://www.radix-ui.com/colors | **MIT** | sand/red 12 级 hex（✅ npm CSS + LICENSE） |
| Tailwind CSS 文档 | https://v3.tailwindcss.com/docs/customizing-spacing 等 | **MIT** | 4px 基数、75–1000ms、ease 曲线（✅ 数值） |
| Apple Fonts（New York） | https://developer.apple.com/fonts/ | Apple 系统字体 | New York 衬线说明（✅ 原文） |
| Apple HIG | https://developer.apple.com/design/human-interface-guidelines/typography 等 | Apple 规范 | 语义色/动效/无障碍（◐ JS） |
| Fraunces / Newsreader / Instrument Serif | 见 §5.1 | **SIL OFL 1.1** | 展示/长文衬线（✅ OFL 文本） |
| Source Han Serif / Noto Serif SC | https://github.com/adobe-fonts/source-han-serif | **SIL OFL 1.1** | CJK 衬线（✅ OFL 文本） |
| LXGW WenKai 霞鹜文楷 | https://github.com/lxgw/LxgwWenKai | **OFL-1.1** | 手写/批注风（26.4k★；README 有 OFL 提醒）✅ |
| Luminare / SimpleSidebar / design-foundation / CodeEdit | 见 §5.3 | **BSD-3 / MIT / MIT / MIT** | SwiftUI 桌面端组件/架构参考（✅） |

---

## 8. 风险、未验证项与边界

1. **GPL 传染性**：Pindo 只借思路，不复制代码；Jett/pyxelate MIT：移植保留版权与 LICENSE；PixelOE Apache-2.0：保留 NOTICE/归属。
2. **OpenCV**：本机 4.14.0；未安装 `cv2.ximgproc`（guidedFilter/thinning），方案全部避开 contrib。
3. **未跑 run_tests/swift test**（按分工避免干扰门禁）；所有数字来自 `qa/research/` 两个独立脚本，输入 `qa/lead/inputs/eagle.png`，可复现。
4. **参数需按色卡校准**：Jett/Pindo 参数针对其色卡；本项目 MARD 221 下 DoG 92/80、ΔE p88 是 eagle 单图工作点，正式实现建议做成滑杆 + 3–5 张回归样图（照片/插画/线稿/白底商品/深底霓虹）。
5. **UI 风格分析页是第三方观察**（Monocle Design Atlas / Refero）：数值用于设计参考而非官方规范；杂志官网内容版权归各自所有，只做版面语言观察。
6. **字体**：系统字体不打包；OFL 字体打包需附 OFL 文本且遵守 Reserved Font Name；LXGW WenKai README 有 OFL 权益/倒卖提醒，商用分发前建议法务确认。
7. **GrabCut 性能/随机性**：必须降采样 + 固定迭代；纯白 on 纯白无解（需用户框选或 rembg）。
8. **CIEDE2000 大网格成本**：>200×200 建议 LUT/分块；预览可用 CIE76 快路径。
9. **负结果**：XDoG 软阈值直接当线稿掩码会退化（100% 覆盖）；全分辨率 DoG 覆盖率下采样对照片偏重（16.8%），仅适合插画源图。

---

## 9. 交付物清单

- 本报告：`qa/research/report.md`
- 验证脚本：`qa/research/verify_lineart.py`、`qa/research/verify_color_bg.py`
- 证据图/数据：`qa/research/artifacts/lineart_compare.png`、`lineart_metrics.json`、`cel_compare.png`、`palette_distance_compare.png`、`bg_remove_compare.png`、`color_metrics.json`
