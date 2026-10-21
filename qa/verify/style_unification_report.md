# T17 独立验证报告：生成图 / 成品 / PDF 的 editorial 风格统一与可读性

| 项 | 值 |
|---|---|
| Task | task-17（owner: view-verify；范围：T15 引擎输出，Tk 已取消） |
| 验证对象 | T15（effects-qa）：图纸 PNG / 成品预览 / PDF(A4+BOM、1:1、bw) 老钱风 editorial 重做 + dark_chart |
| 源码状态 | core/models.py、core/processor.py、core/effects/filters.py、tests/run_tests.py（T15 completed，未 commit）；哈希见 qa/verify/evidence/style/after_source_hashes.txt |
| 环境 | macOS 27.0.1 / Python（conda pindou：Pillow+numpy）/ swift 6.4；PDF 转图 pdftoppm 110dpi；OCR 用自建 Swift/Vision 工具（qa/verify/style/ocr） |
| 方法 | **独立渲染**：自建 core_server JSON 行协议客户端（qa/verify/style/gen_outputs.py）生成 29/60/100 + cell16 + dark + 透明素材 finished + 3 种 PDF；自建像素/OCR 分析器（analyze.py）断言；不读 T15 的 checks.json 作为结论 |
| 写作用域 | qa/verify/**（产品代码零改动；未 commit/push） |

---

## 0. 结论摘要

| 检查项 | 结论 | 关键证据 |
|---|---|---|
| ① 图纸 PNG：paper 背景 / 无旧蓝 / 图例·页脚 / 信息完整 / 无重叠 | **PASS（P2 文字缺陷已修复并复验，见 §11）** | 3 个角=paper（244,237,225，δ=0）+ 左上角块=espresso（42,33,24，δ=0）；旧蓝精确命中 **0 / 宽蓝 0**（改前 2110/3336–6407）；accent 2048–23535 px、paperDeep 6.9万–47万 px、发丝线 4.9万–49.8万 px；图例 OCR 重叠 **0**；信息项 8/8 命中；色号文字对比度中位 10.7–13.25 |
| ② dark_chart 暗色 tokens | **PASS** | 背景精确 (23,18,13)=#17120D（δ=0）；面板 (30,24,17) 46.7万 px；暗发丝线 (58,47,35) 49.9万 px；暗黄铜 (201,155,99) 2.35万 px |
| ③ 成品 finished：透明格露 paper | **PASS** | 透明素材 finished 四角 **δ=0 精确等于 paper**；满覆盖照片 finished 四角为珠色（背景不暴露，符合语义）；代码 GRID_WHITE=PAPER |
| ④ PDF A4/BOM/1:1 页：背景/版式/页数 | **PASS** | a4+bom 5 页、a4+bw 5 页、1:1 8 页（与改前 **5/5/8 完全一致**）；页面 595.2×841.68pt = A4；**所有页**四角=paper（raster δ=1）；BOM 页 4 页/份（MATERIALS·耗材清单 + SWATCH/CODE/NAME/QTY/SHARE 表头）；图纸页脚 3,600 / 01 / 01；页内 footer 无重复（PLATE/MATERIALS 每页 ≤1）；旧蓝 0 |
| ⑤ 与 DesignSystem.swift tokens 逐项比对（±2 RGB） | **PASS** | core/models.py 17 个 token 对 Swift light/dark tokens **delta 全 0，17/17 通过**（差异表见 §6） |
| ⑥ 回归：run_tests / gui_smoke 顺序跑 | **PASS** | 顺序（不并发）run_tests **277 PASS / 0 FAIL**、gui_smoke **92/0**、stress_protocol 12/0、swift test **111/0**；golden 未变且语义正确（只哈希 finished 纯珠区，满覆盖测试源不受底色影响） |

**P2（图纸 PNG CJK tofu）已由 effects-qa 修复并复验通过（见 §11）**：图例「N 颗」与页脚「约 … cm · 5mm/颗」现按 CJK 感知混排（数字 mono + 中文 body）正确显示；修复后重出全部证据并复跑：像素/OCR/PDF/token 指标无回退，run_tests 279/279、gui_smoke 92/92、stress 12/12、swift test 111/111。无未决不合格项。

---

## 1. 方法与可复跑命令

    cd qa/verify/style
    swiftc -O -o ocr ocr.swift                       # Vision OCR 工具
    conda run -n pindou python gen_outputs.py --tag after   # 真实引擎渲染证据（独立客户端）
    conda run -n pindou python analyze.py --tag after       # 像素 + OCR + token 比对
    bash run_regression.sh                                  # 4 套测试顺序跑（不并发）

- 渲染：spawn core_server.py（stdin/stdout JSON 行），环境变量隔离输出/设置/历史到临时目录（不污染仓库 output/ 与用户数据）。
- 取样：29×29 cell20、60×60 cell60、100×100 cell16、60×60 cell16、60×60 dark_chart、透明素材 29×29 finished；PDF：a4+bom、a4+bw、1:1。
- 断言：四角/角块颜色、旧蓝色像素（精确 + 宽蓝，且限定 chrome 带避免色卡内合法蓝色珠干扰）、accent/paperDeep/hairline 像素量、OCR（信息完整性/重叠）、OCR 框内近似对比度（p95/p5）、逐页 PDF 转图、token 源级比对。

---

## 2. ① 图纸 PNG（核心验收）

| case | 尺寸(px) | 角块 espresso | 其余 3 角 paper δ | 旧蓝 chrome/broad | accent px | paperDeep px | 图例重叠 | 信息(8 项) | 文字对比度中位 | 色号对比度中位 |
|---|---|---|---|---|---|---|---|---|---|---|
| 29×29 cell20 light | 1000×1368 | ✓ | 0 | 0 / 0 | 2048 | 69,350 | 0 | 8/8 | 4.74 | 13.25 |
| 60×60 cell60 light | 3670×4532 | ✓ | 0 | 0 / 0 | 4,316 | 470,339 | 0 | 8/8 | 4.80 | 12.58 |
| 100×100 cell16 light | 1670×2580 | ✓ | 0 | 0 / 0 | 7,040 | 178,896 | 0 | 8/8 | 4.60 | 13.25 |
| 60×60 cell16 light | 1030×1892 | ✓ | 0 | 0 / 0 | 4,300 | 108,476 | 0 | 8/8 | 5.06 | 13.25 |
| 60×60 cell60 dark | 3670×4532 | ✓(角块仍 espresso) | 0（=#17120D） | 0 / 0 | 23,644 | 467,875 | 0 | 8/8 | 9.68 | 10.70 |

（注：上表为 P2 修复前首轮独立渲染数值；修复后重跑各指标一致（差异 <0.1%），见 §11。）
- 信息完整性 OCR 实际读到：GRID 29×29 / BEADS 841 / COLORS 37 / MARD 221 / 14.5×14.5 cm / 5mm/… / PLATE 01 · 拼豆图纸 / MATERIALS · 耗材清单（60/100 图同样命中；OCR 对「颗」有误读但单位行存在）。
- 旧蓝对比（改前基线，同一脚本 HEAD 版本生成）：角=旧蓝 (0,120,215)，chrome 旧蓝 2110–2111 px、宽蓝 3336–6407 px；改后 **全部为 0**。
- 图例版面：4–5 列自适应（29 图 5 列、60 图 4 列），OCR 框两两重叠 0；列内 色号/名称/数量 无串行。
- 尺寸变化（样式性、可解释）：因图例从旧 10 列改为 4–5 列，图片高度增加（60 图 4270→4532）；宽度不变；BEADS/COLORS 与改前完全一致（841/37、3600/52、10000/59…）→ 配色/映射算法未变，仅样式层。

---

## 3. ② dark_chart 与成品 finished

- dark_chart：背景 (23,18,13)=#17120D 精确；面板 (30,24,17)=#1E1811；暗发丝线 (58,47,35)=#3A2F23；暗黄铜 (201,155,99)=#C99B63；无旧蓝。
- finished（透明素材路径）：finished 四角 **δ=0 精确 = paper #F4EDE1** → 透明/未覆盖格露出纸底；满覆盖照片的 finished 四角是珠色（背景不暴露，符合「成品图无背景」语义）。
- 代码审计：GRID_WHITE 由纯白改为 PAPER（core/processor.py:33），finished 画布底 = PAPER；dark_chart 只改图纸，不影响 finished。

---

## 4. ④ PDF（A4 / BOM / 1:1 / bw）

| PDF | 页数 | 页面尺寸 | 每页背景 | BOM 页 | 旧蓝 | 页脚重复 |
|---|---|---|---|---|---|---|
| a4 + bom | 5（4 BOM + 1 图纸） | 595.2×841.68pt（A4） | 四角 paper（δ=1，raster 110dpi） | 1–4（MATERIALS/耗材清单 + SWATCH/CODE/NAME/QTY/SHARE） | 0 | 无（PLATE/MATERIALS 每页 ≤1） |
| a4 bw | 5（同上） | 同上 | 同上 | 1–4，58 条 OCR 文本可读 | 0 | 无 |
| 1:1 实物 | 8（4 BOM + 4 图纸页） | 同上 | 全部 paper | 1–4；5–8 为图纸分页 | 0 | 无 |

- 页数与改前完全一致（改前 a4+bom=5、a4+bw=5、1:1=8）→ 1:1 裁切语义/分页未变。
- A4 图纸页：四角 paper，页脚「3,600」「01 / 01」可读；BOM 页 QTY/SHARE 数字右对齐、表头 hairline、色块+色号+名称完整。
- bw 模式：BOM 页 OCR 58 条文本可读；图纸页在 A4 缩放下页脚/数字可读（单元格色号在 A4 110dpi 下 OCR 不可辨，属打印尺寸物理限制；放大查看灰度对比可读）。

---

## 5. ④ 可读性（不同尺寸）

| 指标 | 29×29 cell20 | 60×60 cell60 | 100×100 cell16 | 60×60 cell16 | dark 60 |
|---|---|---|---|---|---|
| 色号文字数量(OCR) | 76 | 52 | 60 | 68 | 260 |
| 色号对比度中位 | 13.25 | 12.58 | 13.25 | 13.25 | 10.70 |
| 色号对比度 <4.5 的数量 | 3 / 76 | 1 / 52 | **0 / 60** | **0 / 68** | 7 / 260 |

- 「cell≥16 时字号/对比度」：cell16 与 cell20 图均无大面积低对比；极少数（29 图 3 个、60 图 1 个、dark 7 个）落在 2.3–4.5，均为**中间调珠色**（如 RGB(120,129,126)/(139,104,76)）上的色号，属二分阈值边缘，列为 P3 观察（不影响整体可读，中位对比度 10.7–13.25）。
- 29×29 小图图例 5 列不溢出（图例区 OCR 框均在画布内、无重叠）；100×100 大图页脚不重叠（footer 单行 + 元数据行，OCR 无重叠框）。

---

## 6. ⑤ 与 DesignSystem.swift tokens 逐项比对（±2 RGB）

| core token | core 值 | Swift token(模式) | Swift 值 | ΔRGB | 判定 |
|---|---|---|---|---|---|
| PAPER | 244,237,225 | paper(light) | 244,237,225 | 0 | PASS |
| PAPER_DEEP | 235,225,210 | paperDeep(light) | 235,225,210 | 0 | PASS |
| PAPER_MAT | 251,246,236 | paperMat(light) | 251,246,236 | 0 | PASS |
| INK | 42,33,24 | ink(light) | 42,33,24 | 0 | PASS |
| INK_SOFT | 77,63,48 | inkSoft(light) | 77,63,48 | 0 | PASS |
| INK_MUTED | 114,97,74 | inkMuted(light) | 114,97,74 | 0 | PASS |
| HAIRLINE | 213,196,172 | hairline(light) | 213,196,172 | 0 | PASS |
| HAIRLINE_SOFT | 230,217,197 | hairlineSoft(light) | 230,217,197 | 0 | PASS |
| HAIRLINE_STRONG | 183,164,136 | hairlineStrong(light) | 183,164,136 | 0 | PASS |
| ACCENT | 138,90,51 | accent(light) | 138,90,51 | 0 | PASS |
| ACCENT_SOFT | 239,224,204 | accentSoft(light) | 239,224,204 | 0 | PASS |
| DARK_BG | 23,18,13 | paper(dark) | 23,18,13 | 0 | PASS |
| DARK_PANEL | 30,24,17 | paperDeep(dark) | 30,24,17 | 0 | PASS |
| DARK_INK | 240,231,216 | ink(dark) | 240,231,216 | 0 | PASS |
| DARK_INK_SOFT | 201,185,159 | inkSoft(dark) | 201,185,159 | 0 | PASS |
| DARK_HAIRLINE | 58,47,35 | hairline(dark) | 58,47,35 | 0 | PASS |
| DARK_ACCENT | 201,155,99 | accent(dark) | 201,155,99 | 0 | PASS |

**17/17 通过（δ 全部 0，远优于 ±2 要求）**。另用渲染图逐色统计验证 token 真的被使用（60×60 light：paper 304.5万 px、paperDeep 46.6万、hairline 49.8万、accent 4183、ink 7.6万、paperMat 10.8万；dark：dark_bg 304.3万、dark_panel 46.7万、dark_hairline 49.9万、dark_accent 2.35万）。
注：ACCENT_SOFT 在引擎图表中未使用（0 px）——该 token 属 UI 用色，引擎侧未用不算偏差。

---

## 7. P2 缺陷记录（已修复，见 §11）

### P2（已修复）：图纸 PNG 两处中文渲染为 tofu（缺字形）

- 现象（29/60/100、亮/暗全部复现）：
  - 图例每项数量后缀「颗」→ 空心方框，如「235 □」；
  - 页脚元数据「约 14.5×14.5 cm · 5mm/颗」中的「约」「颗」→ 「□ 14.5×14.5 cm · 5mm/□」。
  - 其余中文正常（PLATE 01 · 拼豆图纸、MATERIALS · 耗材清单、色号名称、大数字单位「颗」均正常）。
- 根因（core/processor.py，最终工作区）：
  - L573 font_count = _get_font(11, role=mono)；L603 cnt_text = thousands(count) + 颗 → 整串含 CJK 却用 Menlo（mono 候选第一项 Menlo 加载成功即停，不会回退到 Arial Unicode）→ tofu；
  - L621 font_meta = _get_font(11, role=mono)；L651 meta = ... · 约 {w}×{h} cm · 5mm/颗 → 「约」「颗」tofu。
  - PDF BOM 页 QTY 列为纯数字，正常；PDF 图纸页继承该图（A4 缩放下同缺陷较小）。
- 修复建议（最小改动）：图例数字用 mono 单独绘制，「颗」用 body/serif 单独 draw（或图例只留纯数字，与 PDF BOM QTY 一致）；页脚元数据按 ASCII/中文分段绘制（或「约」改 ~、单位去掉/换 body 字体绘制该段）；不建议把 PingFang 塞进 mono 链。
- 证据图：qa/verify/evidence/style/after/crops/tofu_legend_29.png、tofu_footer_29.png、tofu_legend_60.png、tofu_footer_60.png；完整渲染图 qa/verify/evidence/style/after/*_chart.png。
- 状态：**已修复并复验通过（见 §11）**。

### P3（观察，不影响验收）

- 中间调珠色上极少数色号文字对比度 2.3–4.5（29 图 3/76、60 图 1/52、dark 7/260）；中位 10.7–13.25。若要求严格 4.5，可对 cell 文字阈值改按 APCA 或加 1px 奶油描边。

---

## 11. 追加复验：P2（CJK tofu）修复后（00:2x）

**effects-qa 修复方案**（core/processor.py）：新增 CJK 感知混排 _text_runs() + _draw_mixed_text()——数字/ASCII 用 mono(Menlo)、中文用 body(PingFang)，同基线 anchor=ls 绘制；图例数量改为「数字 mono + 『 颗』body」分段右对齐；页脚元数据「约」「颗」归 body 段、其余 mono 段居中混排；PDF BOM 的 QTY/SHARE 纯数字不受影响。

**我的独立复验**（重新跑 gen_outputs + analyze，未读对方证据）：
- 图例：「235 颗 / 140 颗 / 87 颗 …」字形正常（复验截图 qa/verify/evidence/style/after/crops/after_fix_legend_29.png）；
- 页脚：「GRID 29×29 · BEADS 841 · COLORS 37 · MARD 221 · 约 14.5×14.5 cm · 5mm/颗」全部字形正常（after_fix_footer_29.png / after_fix_footer_60.png）；
- 全套指标无回退：3 角 paper δ=0 + 左上 espresso、旧蓝 chrome/broad=0、accent/paperDeep/hairline 像素量保持、图例 OCR 重叠 0、信息 8/8、token 17/17 δ=0、finished 透明格 paper δ=0、PDF 5/5/8 页 A4 paper 底、无旧蓝；
- 修复后回归：run_tests **279/279**（新增 2 条守卫断言：含 CJK 的串禁用 mono 字体 / 「约 30×30 cm · 5mm/颗」须归 CJK 段）、gui_smoke 92/92、stress 12/12、swift 111/111。

**结论：P2 关闭，T17 无未决不合格项。**

---

## 8. ⑦ 回归与 golden 语义

| 套件 | 结果 | 日志 |
|---|---|---|
| tests/run_tests.py | **279 PASS / 0 FAIL**（改前 249 → T15 +28 视觉结构断言；P2 修复再 +2 条 CJK-mono 守卫断言；修复前首轮为 277） | qa/verify/evidence/style/logs/run_tests.log |
| tests/gui_smoke.py | **92 PASS / 0 FAIL**（DEFAULT_GRID_COLOR 改为暖发丝线后无回归） | logs/gui_smoke.log |
| tests/stress_protocol.py | 12 PASS / 0 FAIL | logs/stress_protocol.log |
| cd app && swift test --disable-sandbox | **Executed 111 tests, 0 failures** | logs/swift_test.log |

合计 279+92+12+111 = **494**（P2 修复前首轮 277/92/12/111=492，全部通过）；4 套严格顺序执行两轮（run_all.log 时间戳可证），无并发。

**golden 语义（未变化是正确结果）**：golden.json / golden_matrix.json 的哈希对象是 finished.tobytes()（纯珠像素，无字体/无背景边），测试源为 160×120 随机图、全格覆盖 → 主题只改「底色/文字/PDF/图表背景」，finished 纯珠区不变 → 哈希不变；`git diff tests/golden/` 为空、与 HEAD 哈希一致。底色变化由透明素材 finished 用例 + 新增 run_tests 视觉断言覆盖。

**改动性质审计（样式-only）**：git diff 统计 core/models.py +27、core/processor.py +580、core/effects/filters.py 9 行（仅 dark_chart 颜色默认值/背景）、tests +208；新增函数全部是样式辅助（_theme/_relative_luminance/_cell_text_color/_legend_columns/_palette_display/_thousands/_physical_size/_double_rule/_fleuron/字体 role 扩展/PDF BOM bw 参数）；无量化/映射/特效算法改动（色数/颗数与改前逐 case 一致）。run_tests 仅 5 行断言从旧灰 (200,200,200) 更新为 DEFAULT_GRID_RGB（暖发丝线），未削弱覆盖。

---

## 9. 证据与复跑

| 路径 | 说明 |
|---|---|
| qa/verify/evidence/style/after/*.png | 6 个 case 的独立渲染图（29/60/100/cell16/dark/透明 finished） |
| qa/verify/evidence/style/after/*.pdf | a4+bom、a4+bw、1:1 三份 PDF |
| qa/verify/evidence/style/after/pdf_pages/*.png | PDF 逐页转图（110dpi） |
| qa/verify/evidence/style/after/analysis_after.json | 全部量化结果（像素/OCR/对比度/token/PDF 页级） |
| qa/verify/evidence/style/analysis_before.json | 改型前基线（同脚本，HEAD 源码生成）—旧蓝/白底对照 |
| qa/verify/evidence/style/logs/ | 4 套回归日志 |
| qa/verify/style/{gen_outputs.py,analyze.py,ocr.swift,run_regression.sh} | 可复跑脚本 |
| qa/verify/evidence/style/after/crops/after_fix_legend_29.png / after_fix_footer_29.png / after_fix_footer_60.png | P2 修复后字形复验（tofu 消失） |

---

## 10. 时间线

| 时间 | 事件 |
|---|---|
| 00:04 | claim task-17；搭建独立渲染/分析基建，抓改型前基线（旧蓝/白底证据） |
| 00:14 | T15 completed；独立渲染 after 6 case + 3 PDF |
| 00:16–00:19 | 4 套测试顺序跑：277/92/12/111 全绿 |
| 00:19–00:22 | 像素/OCR/PDF/ token 比对完成；发现并上报 P2 tofu 缺陷（effects-qa） |
| 00:21 | effects-qa 修复 CJK 混排；我方重跑 gen+analyze 复验通过（§11） |
| 00:25 | 修复后 4 套测试顺序复跑：279/92/12/111 全绿；报告更新，complete task-17 |