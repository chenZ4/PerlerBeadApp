# T3 门禁复测与测试有效性审计报告

| 项 | 值 |
|---|---|
| Shared Task | task-3（独立测试验证工程师 gate-verify） |
| 执行时间 | 2026-10-21 21:39–21:52（Asia/Shanghai） |
| 仓库 | /Users/chen/Desktop/learn/PerlerBeadApp，branch dev-2.0，HEAD 3b7393d（2026-09-30 'present: TEST_REPORT.md (+8 source)'） |
| 工作区 | 运行前 git status 干净；结束仅 ?? qa/（新增审计产物），未 commit/push，未改产品源码/既有测试 |
| 被核对文档 | TEST_REPORT.md（mtime 2026-09-30 14:48，含第 3 章审计 + 第 4 章「412 项全绿」） |
| 写作用域 | 仅 qa/gates/（report/logs/probes/results.json） |

---

## 0. 结论摘要

1. **「412 项全绿」在它自己的口径内属实且可复现：230 + 92 + 12 + 78 = 412，0 失败。**
   本次严格顺序独立复跑全部命中；run_tests.py 另重跑一次仍 230/0（含 canary），无 flaky。
2. **但这 412 项中，没有任何一条断言检查「特效视觉质量」或「UI 外观/布局/可读性」。**
   412 = 代码路径 + 结构不变量 + 协议/竞态/容错回归，不代表用户感知的功能可用与美观。
3. **测试有效性缺口可用探针实锤：15 个特效中有 7 个的现有门禁断言，把特效替换成 no-op（原样返回）仍会全绿；
   mirror / crop / outline_edge / chibi 在门禁用例所用 fixture 上真实特效改变 0% 图纸像素。**
   （证据：qa/gates/probes/test_discrimination_probe.py，17 个复刻用例中 8 个 vacuous。）
4. **UI 层：「切换特效后预览不刷新」这一直接影响用户感知的行为既未实现自动刷新（无 onChange/didSet→generate），
   也没有被任何测试覆盖；XCUITest 6 个用例无一条外观断言，且不在 412 门禁内（报告遗留悬空「见下方补记」）。**
5. **测试隔离存在数据丢失级问题：run_tests.py 会 shutil.rmtree(仓库/track) 删除全部进度文件；
   gui_smoke.py 无条件删除真实仓库根 app_settings.json / queue_state.json；
   run_tests 还会把测试值写进仓库根 app_settings.json——违反项目自己写在 ARCHITECTURE 的隔离约定。**
6. 环境差异：本会话 DSH 沙箱下 cd app && swift test 原命令 exit=1（sandbox-exec: sandbox_apply: Operation not permitted），
   加 --disable-sandbox 后 78/78；ps 被沙箱禁用导致 stress S5 内存断言恒真。两者均已定位为环境问题并给出复现证据。

**对「412 全绿」声明的判定：数字成立（可复现），但作为「交付质量门禁」的表述过强。**
准确表述应为：「4 套本地回归套件 412 条代码路径/结构断言全绿；不含视觉质量、外观审美、真实 UI 交互（XCUITest）验证」。
用户「特效代码可行但效果不可行 / UI 不好看」与 412 全绿并不矛盾——门禁从来没测过这两件事。

---

## 1. 环境与执行说明

### 1.1 环境

| 项 | 值 |
|---|---|
| OS | macOS 27.0.1（build 26A434），arm64 |
| Swift | Apple Swift 6.4（swiftlang-6.4.0.34.1），Xcode 27.1（27A9275） |
| Python | conda env pindou：Python 3.11.15 / Pillow 12.3.0 / numpy 2.4.6 / OpenCV 4.14.0 / Tk 8.6 |
| 引擎入口 | core_server.py stdio JSON 行协议；core/ 引擎 |
| 沙箱 | DSH workspace-write，审批关闭。工作区外（~/Library）不可写；/bin/ps、SwiftPM 的 sandbox-exec 被拒 |

### 1.2 执行纪律

- **严格串行，绝不并发**：四套件共享 output/、track/，且 run_tests 会 prune output/（会删掉并发方的产物）。
  项目文档 docs/ARCHITECTURE.md:161-162 亦明确「套件不可并发跑」。其他 teammate 的引擎探针使用 save=False/qa 临时目录，未与本轮套件并发。
- 顺序：run_tests.py → gui_smoke.py → stress_protocol.py → (cd app && swift test)。
- 全程未修改产品源码与既有测试；未 git commit/push；output/、根目录 .json 的改动按要求保留、不清理不提交。

### 1.3 执行偏差（如实记录）

- 首次尝试用 background job 启动 run_tests.py（21:40），harness 在程序结束后回收了该后台任务（无 meta 文件、日志仅 16 行且 stdout 有缓冲）。
  为不误读数据，随后**从头严格串行重跑**；本报告所有数字均取自 21:42:32 起的权威执行。
- run_tests.py 在权威执行之外又完整重跑一次（21:49:16–21:50:25，69s，230/0），用于 flaky 验证。
- swift test 的「原命令」与「可执行命令」各跑了一次（见 2.2）。

---

## 2. 门禁实测结果

### 2.1 总表

| # | 套件 | 命令 | 起止 | 耗时 | 退出码 | 通过 | 失败 | 日志 |
|---|---|---|---|---|---|---|---|---|
| 1 | tests/run_tests.py | conda run -n pindou python tests/run_tests.py | 21:42:32 → 21:43:39 | 67s | **0** | **230** | **0** | logs/run_tests.log |
| 1r | 同上（重跑验 flaky） | 同上 | 21:49:16 → 21:50:25 | 69s | **0** | **230** | **0** | logs/run_tests_rerun.log |
| 2 | tests/gui_smoke.py | conda run -n pindou python tests/gui_smoke.py | 21:43:52 → 21:44:13 | 21s | **0** | **92** | **0** | logs/gui_smoke.log |
| 3 | tests/stress_protocol.py | conda run -n pindou python tests/stress_protocol.py | 21:44:15 → 21:45:29 | 74s | **0** | **12** | **0** | logs/stress_protocol.log |
| 4 | app/ swift test | cd app && swift test --disable-sandbox | 21:45:41 → 21:46:34 | 53s | **0** | **78** | **0** | logs/swift_test.log |
| — | **合计** | — | — | **≈215s** | — | **412** | **0** | — |

- 每个通过数均由日志中 [PASS] 行 / XCTest 「Executed N tests, with 0 failures」精确计数，非脚本自报。
- run_tests.log 中 2 条 traceback 为文档已记载的预期现象（「文件不存在返回 None」的引擎容错日志，docs/ARCHITECTURE.md:167-168），非失败。
- gui_smoke.log 130 行、stress_protocol.log 23 行、swift_test.log 252 行，全文与 tail（≤200 行）均已存 qa/gates/logs/。

### 2.2 逐套明细与失败/flaky 分析

**run_tests.py（230/0）**
- 分段覆盖：色卡/处理器/PDF/历史/内存/golden·golden 矩阵/core_server 协议/特效库/阶段3/输出裁剪/WYSIWYG/鲁棒性/审计回归。
- 特有输出：通过: 230 失败: 0；[PASS]=230、[FAIL]=0；退出码 0。
- **flaky：两次完整运行均 230/0（前后 output/ 状态不同：第一次目录里有 50 个旧产物，第二次是首次运行留下的新产物）。**
  历史上第 3 章记录的 canary 隔离缺陷（TEST_REPORT.md:423-430）其修复（tests/run_tests.py:1304-1320，canary mtime=目录最旧文件−1h）在本轮两种目录状态下均稳定通过，确认已修复。
- 唯一「异常输出」是 2 条预期 traceback（见上），非 flaky。

**gui_smoke.py（92/0）**
- 全程零弹窗、零人工交互（打桩 filedialog/messagebox）；起真实 Tk 窗口。
- 通过: 92 失败: 0；退出码 0。无 flaky 迹象。
- 该套件**完全未覆盖特效**（Tk 版根本没有特效面板，docs/ARCHITECTURE.md:183），详见第 5 节。

**stress_protocol.py（12/0）**
- S1 取消风暴×24 / S2 排队无丢失 / S3 垃圾输入 / S4 在途 EOF / S5 150 次生成内存基线。
- 通过: 12 失败: 0；退出码 0。无 flaky。
- **注意（环境退化）**：S5 的内存断言在本沙箱下恒真——tests/stress_protocol.py:237-244 的 rss_kb() 调用 ps 被拒（PermissionError）后 except 返回 0，early=late=0 → growth=0MB < 120MB 恒通过。
  探针复刻见 qa/gates/probes/stress_s5_ps_probe.py：初期/后期 rss=0, growth_mb=0.0 → PASS。即 12 项中至少 1 项对内存泄漏零区分力（普通开发机上有 ps 时有效）。

**swift test（78/0，附环境差异）**
- 权威执行：cd app && swift test --disable-sandbox → Executed 78 tests, with 0 failures，退出码 0，53s。
- **报告命令原样执行 cd app && swift test 在本会话失败（exit=1，1s）**：
  error: 'app': Invalid manifest ... sandbox-exec: sandbox_apply: Operation not permitted + SwiftPM 用户缓存 ~/Library/org.swift.swiftpm 不可写。
  根因是 DSH 工作区沙箱禁止嵌套 sandbox-exec、且工作区外不可写；**属执行环境限制，不是产品/测试缺陷**。证据：logs/swift_test_rawcmd_failure.log。
- 换用 --disable-sandbox（本项目无 build plugin 脚本，安全性影响可忽略）后复现报告 78/78。
- swift test 只包含 Tests/PerlerAppTests（app/Package.swift:13-18）；Tests/PerlerAppUITests 不在 SPM target，见 3.3。

### 2.3 是否有失败/flaky

- **失败：0**（四套合计 412/0；重跑 run_tests 仍 0）。
- **flaky：0 观察到**（run_tests 两次、其余各一次）。报告 3.1 所述 canary flaky 的根因与修复已在代码中确认（3.2）。
- 环境导致的「假失败/退化」2 处，均非产品缺陷：swift test 原命令被沙箱拒绝；stress S5 的 ps 被沙箱拒绝导致内存断言恒真。

---

## 3. 与 TEST_REPORT.md 声明核对

### 3.1 第 4 章「412 项终态」逐项对照

TEST_REPORT.md:486-497 的表格 vs 本次实测：

| 套件 | 报告声明 | 本次实测 | 差异 |
|---|---|---|---|
| run_tests.py（214 基线+16 回归） | 230 / 0 | **230 / 0**（两次） | 无 |
| gui_smoke.py | 92 / 0 | **92 / 0** | 无 |
| stress_protocol.py | 12 / 0 | **12 / 0** | 无 |
| swift test | 78 / 0 | **78 / 0**（--disable-sandbox） | 仅环境执行方式差异 |
| **合计** | **412 / 0** | **412 / 0** | 无 |

- 报告 4.2 声称新增「测试11 审计缺陷回归 16 项」：tests/run_tests.py:1416-1508 实测恰为 16 个 report()，与声明一致。
- 报告 4.1 声称 canary flaky 已修（mtime 取目录最旧−1h）：tests/run_tests.py:1304-1320 代码属实，且本轮在「目录有 50 个旧产物」的脏状态下通过。
- 报告 4.3 声称 golden 矩阵哈希全部一致：本轮该断言通过；但 golden 覆盖范围有限（3.4）。
- 第 3 章（2026-09-30 审计）的 395/1 是**修复前历史**数据，与第 4 章 412/0 不冲突；本轮只对第 4 章终态负责。

### 3.2 canary flaky 核对（报告 3.4-D → 4.1）

- 旧缺陷：canary mtime 固定 now−7200，prune_output keep=50 时可能先删更旧文件而放过 canary → 用例红。
- 现实现：tests/run_tests.py:1310-1319 扫描真实 output/ 内所有文件，取 min(mtime)-3600 作为 canary mtime；若目录空则用 now−7200。两种情形 canary 都会成为最旧文件，因此必被裁掉。
- 实测：第一次跑（output/ 有 50 个旧文件）通过；重跑（output/ 全是新文件）通过。**结论：修复有效，不再 flaky（至少在本机两种目录状态下）。**

### 3.3 XCUITest「3/3 / U4-U7」核对 —— 不在门禁内，且报告证据链断裂

**事实核对：**

1. **412 不含 XCUITest**：230+92+12+78=412 精确可加；swift test 的 SPM 包只声明 PerlerAppTests（app/Package.swift），UI 测试 target 不在其中。
2. **XCUITest 需要额外工程/命令**：app/project.yml 是 XcodeGen 规范，需 xcodegen generate + xcodebuild test；.xcodeproj 被 gitignore。CI 中 ui-tests-macos 明写 continue-on-error: true（.github/workflows/ci.yml），即**观察项，不是必过门禁**。
3. **当前 XCUITest 实际是 6 个用例**（app/Tests/PerlerAppUITests/SmokeUITests.swift：U1 启动/引擎初始化、U2 模板→生成 E2E、U3 拖拽安全、U4 网格实时联动、U5 原始比例联动、U7 回车后继续联动）。
4. **报告内部口径不一致且缺结果**：
   - TEST_REPORT.md:187-188：「已本地验证 **3/3** 全绿」（2.2.1，只有 U1-U3）；
   - TEST_REPORT.md:234：2.2.2 改成「XCUITest **4 项**（+U4）」；
   - TEST_REPORT.md:306：2.3.0 门禁表写「XCUITest（U4-U7：...）」结果栏为「**见下方补记**」——**该「补记」在全文中不存在**，U5/U6/U7 从未有任何通过记录；
   - 2.3.0 的「门禁结果」表格（TEST_REPORT.md:300-306）因此不是完整的终态证据。
5. 本轮**未执行** XCUITest（需 xcodebuild + GUI 自动化权限，且报告自述 runner 偶发 'Timed out while enabling automation mode'，TEST_REPORT.md:293）；因此报告中任何「XCUITest 全绿」的说法目前**不可独立复现**。

**结论：XCUITest 在 412 之外是事实；报告对它的描述停留在旧版本（3 项/4 项），当前 6 个用例没有结果记录，属于「不可核验声明」。**

### 3.4 Golden / 回归覆盖核对（是否覆盖特效效果）

- tests/golden/golden_matrix.json 8 个配置，含特效的只有 4 个：grayscale、max_colors_6、outline_cell、dark_chart（其余 base/exact/fitbox/basic_palette 无特效）。
- dither 只做结构断言（总量守恒/色域⊆色卡/与无抖动不同，tests/run_tests.py:1391-1411），不进字节哈希。
- 其余 11 项特效（adjust/chibi/crop/mirror/neon/duotone/bg_remove/cel_shade/preset/outline_edge + dither 的视觉质量）**没有任何 golden 锚点**。
- 后果：这些特效的「效果是否好看/是否退化」无法被 golden 发现；哈希只能证明「4 个特效的输出与 2026-09-08 重生成的基准一致」，不能证明效果符合预期。

### 3.5 「代码路径断言冒充视觉/交互质量」核对 —— 存在，且集中在特效结论

逐句核对 TEST_REPORT：

| 报告表述 | 实际可核验证据 | 判定 |
|---|---|---|
| TEST_REPORT.md:276「输出质量（**探针逐项目检 + 像素 diff 量化**）」并列出 CIELAB/描边/赛璐璐等修复 | 这些探针在第 312 行自述为「临时产物…提交前删除」；仓内无任何像素 diff/质量断言 | **过程证据已消失，质量结论无回归锚点** |
| TEST_REPORT.md:302-306 门禁表 + 412 全绿 | 412 中特效相关断言只有结构/不崩溃/参数装配（第 4 节实证） | **用代码路径绿灯代表「特效可用」，不成立** |
| TEST_REPORT.md:188「XCUITest 已本地验证 3/3 全绿（启动/模板生成 E2E/拖拽安全）」 | 3 项均为「能启动/能生成/不崩溃」，无外观断言；且已过时 | 交互路径 ≠ 交互质量/外观 |
| TEST_REPORT.md:452「门禁主体：395/396，功能面稳定」 | 第 3 章当时的判断，第 4 章修复后为 412/0 | 历史表述，不算冒充 |
| 第 3.2 节（TEST_REPORT.md:334-350）「深挖审计用例（本轮新增，**不在门禁内**）」 | 明确标注不在门禁内 | **诚实标注，加分项** |

结论：报告在「缺陷审计」章节是诚实的（明确哪些证据不在门禁内），但**最终「412 全绿」的交付表述把「门禁全绿」外推成了「功能可用/可交付」**；
而用户主诉的两件事（特效效果、UI 美观）恰好都落在门禁断言之外。这不是造假，是**门禁覆盖与用户质量问题域不匹配**。

---

## 4. 测试有效性审计：特效

### 4.1 门禁里到底断言了什么

引擎注册 **15** 个特效（实测 len(list_effects())==15；id：adjust, bg_remove, cel_shade, chibi, crop, dark_chart, dither, duotone, grayscale, max_colors, mirror, neon, outline_cell, outline_edge, preset）。

tests/run_tests.py::test_effects（L743-919）共 **23 个 report()**，按断言强度分类：

| 强度 | 数量 | 例子（行号） |
|---|---|---|
| 仅「不崩溃 / r is not None」 | 10 处出现 | outline_edge L782；neon L868；mirror L878；crop L883；chibi L911/L918；组合特效 L847；无效 id L853 等 |
| 结构/数量类 | ~8 | 灰度全灰阶 L791；限色 ≤N L814/L820；暗底占比 L828；bg_remove 耗材减少 L897 |
| 变化类（无方向/度量） | 3 | dither「映射不同」L806；adjust「映射不同」L836；golden dither「与无抖动不同」L1410 |
| 注册/清单 | 2 | 只断言 **8 个**预期 id 是已注册集合的子集 L749-753；协议 effects op 只断言返回 dict L582-583 |
| 机制类（唯一较强者） | 3 | outline_cell 描边色出现 L761 / 默认纯色 1 色 L769 / 显式外轮廓 2 色 L774 |

**没有**任何断言涉及：效果方向（变亮/变暗/翻转/裁剪区域）、强度单调性、可见度阈值、色相/色彩语义、与目标 palette 的距离、边缘覆盖率、纹理/噪点指标、组合顺序语义、切换特效后预览是否更新。

### 4.2 判别力探针（把特效换成 no-op，门禁还绿吗？）

探针 qa/gates/probes/test_discrimination_probe.py 完全复刻门禁用例的 fixture 与断言谓词，结论：
**17 个复刻用例中 8 个在「no-op（原样返回）」下仍通过；7/15 特效的全部门禁断言都可被 no-op 骗过。**

| 特效 | fixture | 门禁断言 | no-op 也通过? | 该 fixture 上真实特效改图率* |
|---|---|---|---|---|
| outline_cell | 纯红 200×200 | 出现近黑描边色 | 否 | 7.65% |
| outline_cell | 纯色 60×60 | 默认参数仍 1 色（负向） | **是**（本意如此，但单独看无区分力） | 0% |
| outline_cell | 纯色 60×60 | 显式外轮廓 2 色 | 否 | 4.25% |
| **outline_edge** | **纯红 200×200** | **r is not None** | **是** | **0.0%** |
| grayscale | 纯红 200×200 | 全灰阶 | 否 | 71.0% |
| dither | 渐变 | 映射与无抖动不同 | 否 | 100% |
| max_colors | 渐变 | 颜色数 ≤6 | 否 | 100% |
| preset | 渐变 | 马卡龙 ≤6 色 | 否 | 100% |
| dark_chart | 渐变 | 深色占比>30% | 否 | 31.3% |
| adjust | 渐变 | 映射不同 | 否 | 100% |
| **cel_shade** | **纯红 30×30** | **存在彩色像素**（纯红恒真） | **是** | 71.0% |
| **neon** | **纯红 30×30** | **r is not None** | **是** | 71.0% |
| **duotone** | **纯红 30×30** | **r is not None + stats 非空** | **是** | 71.0% |
| **mirror** | **纯红 30×30** | **r is not None** | **是** | **0.0%** |
| **crop** | **纯红 30×30** | **r is not None** | **是** | **0.0%** |
| bg_remove | 白底红块 | 耗材少于不去背景 | 否 | 5.1% |
| **chibi** | **纯红 30×30** | **r is not None** | **是** | **0.0%** |

* 改图率 = 与无特效基线相比图纸像素不同的比例（含图例/标签区域，仅作可见度参考）。
完整数据与 JSON：qa/gates/logs/probe_test_discrimination.log。

**完全可被 no-op 骗过的 7 个特效**：cel_shade, chibi, crop, duotone, mirror, neon, outline_edge。

### 4.3 具体盲区证据（按文件:行）

1. **fixture 选错导致断言「物理上不可能发现效果」**
   - tests/run_tests.py:747 的 src = make_source(200, 200) → 纯红（默认色 255,0,0）；
     mirror/crop/outline_edge/cel_shade/neon/duotone/chibi 都用它。
   - 纯色图镜像/裁剪前后完全一样；纯色图没有边缘；无人脸图 chibi 原样返回——这些用例的断言即使换成 no-op 也必然通过。
2. **线稿描边只测了「不崩溃」，且参数与 UI 默认值不一致**
   - tests/run_tests.py:780-782 传 threshold=120，断言仅 r is not None；
   - UI 走默认参数（引擎默认 threshold=40，core/effects/outline.py:108），**该默认值路径没有任何断言**；
   - 报告自述「threshold 默认 100→40（原 0.9% 像素生效）」（TEST_REPORT.md:281-282）——即团队知道可见度是问题，但没把「可见度」写成测试。
3. **大头 chibi 的「有人脸」路径 0 覆盖**
   - tests/run_tests.py:903-910：face_img 只有变量赋值，**从未写入文件**；face_img if os.path.exists(face_img) else src 永远走 src（无人脸）；
   - tests/run_tests.py:913 report('opencv 已安装（大头可用）', True) 是恒真断言（与是否可用无关）。
4. **注册数量没锁死**
   - tests/run_tests.py:749-753 只断言 8 个 id ⊆ 注册表；若 15 项退化成 8 项，测试仍绿；协议 effects op 仅断言返回 dict（L582-583）。
5. **限定/预设只测了数量**
   - tests/run_tests.py:817-820 马卡龙只断言 ≤6 色，不校验颜色是否接近马卡龙色板；其余 4 个 preset 完全未测；
   - max_colors 只测 6（未测 2/50 边界与「被淘汰色→最近保留色」的 Lab 语义）。
6. **参数单调性/方向全部缺失**：adjust 只断言「变了」（L836），没有 brightness↑→平均亮度↑；neon 没有 assert 更暗/更饱和；cel_shade 没有 assert 每通道色阶数 ≤ levels；duotone 没有 assert 输出落在 color1–color2 连线附近；dither 没有 assert 平滑度/噪点改善；mirror 没有 assert 左右翻转；crop 没有 assert 区域。
7. **组合语义只测「不崩」**：tests/run_tests.py:841-848 4 个特效串联仅 r is not None；阶段顺序（几何→预处理→网格→图纸）无行为断言。
8. **参数端点/UI 默认值未测**：outline_cell width 1-3、mirror vertical、crop x0/y0 组合、bg_remove tolerance 0/120、preset 其余 4 项、max_colors 2/50 均无覆盖。

### 4.4 Swift EffectsExposureTests 审计

app/Tests/PerlerAppTests/EffectsExposureTests.swift（5 个用例）：

| 用例 | 行 | 断言 | 能证明什么 |
|---|---|---|---|
| testAllFifteenEffectsAssembled | 58-78 | 15 个 id 装配齐、首尾顺序 | UI 开关→参数字典；不能证明引擎效果 |
| testEffectParamsCarried | 81-102 | adjust/crop/bg_remove/duotone/neon 参数值 | 参数搬运；不能证明效果 |
| testGenerateSucceedsWithAllEffects | 105-120 | lastResult != nil | **即使引擎忽略所有 effect，该用例仍绿** |
| testEngineHonorsLinkedPairOriginalRatio | 123-134 | WYSIWYG 网格 | 联动，与视觉无关 |
| testEngineHonorsLinkedPairPortraitHeightEdit | 137-148 | WYSIWYG 网格 | 同上 |

- **没有任何断言：切换特效后预览会更新/重新生成**（该行为本身也未实现，见 5.3）。
- **没有任何断言：同一张图开/关特效后 chart 像素/色卡统计发生变化**。
- 因此 EffectsExposureTests 只证明「开关存在且参数能送进引擎」，报告却说它覆盖了「特效暴露」，容易被误读为「特效可用」。

---

## 5. 测试有效性审计：UI 外观与交互

### 5.1 SmokeUITests（XCUITest，门禁外）逐用例覆盖

app/Tests/PerlerAppUITests/SmokeUITests.swift 共 6 个函数：

| 用例 | 行 | 断言内容 |
|---|---|---|
| U1 testLaunchAndEngineSetup | 39-44 | 30s 内出现「引擎就绪/未找到 Python」、app 前台 |
| U2 testTemplateGenerateEndToEnd | 47-83 | 模板菜单可选、生成按钮启用、状态「完成：」出现 |
| U3 testPreviewDragDoesNotCrash | 86-102 | 连续拖拽后 app 仍前台 |
| U4 testGridLinkageRefreshesUI | 106-136 | 输入宽→高框 value 立即变；切比例重联动 |
| U5 testOriginalRatioLinksByTemplateAspect | 139-158 | 模板比例下改宽→高=29 |
| U7 testLinkageSurvivesSubmitAndRetype | 161-184 | 回车后继续输入仍联动 |

- **0 条**关于颜色/字体/间距/材质/对比度/布局重叠/可读性/截图的断言（全文 XCTAssert 只有 exists/enabled/text value/state）。
- 没有特效开关的 UI 用例（U1-U7 完全没点过特效面板）。
- 没有暗色模式/窗口缩放/最小宽度下的外观检查。
- 没有对「生成后预览图是否真的变化」的视觉检查（U2 只等状态文本）。

### 5.2 gui_smoke（Tk，门禁内）覆盖结构

- 92 项主要是：面板默认值、缩放/适应窗口、拖拽、队列持久化、批量取消、撤销、色卡窗口、历史容错、设置持久化、内存。
- **外观/布局相关仅 1 条**：tests/gui_smoke.py:356-360「色卡无右侧白屏（间隙 < 30px）」；另有若干功能性几何断言（缩放条可见、图像角坐标）。
- **特效相关 0 条**：grep -i effect/特效 tests/gui_smoke.py 无命中；Tk 版本身没有特效面板（docs/ARCHITECTURE.md:183），因此「双 UI 兜底」在特效维度不存在。
- 结论：Tk 与 Swift 两侧都没有「界面是否好看/可读」的可执行判定。

### 5.3 「切换特效后预览不刷新」—— 影响用户感知的行为，零测试

静态证据链：
1. 特效开关都是普通 @Published，**没有 didSet/onChange 触发重新生成**：app/Sources/PerlerApp/AppViewModel.swift:158-192；
2. 生成只能由显式 vm.generate() 发起：AppViewModel.swift:425-486；UI 入口只有「生成」按钮：ContentView.swift:147-157；
3. 特效 Toggle 绑定（ContentView.swift:78-145）无任何 .onChange；整个 ContentView 的 onChange 只有模板/比例/预览尺寸（ContentView.swift:43,63,279）；
4. 因此用户打开一个特效开关后，**预览/图纸不会发生任何变化，必须再点一次「生成」**。对普通用户这直接表现为「特效开了没反应 / 效果不可行」。
5. 该交互没有任何测试：EffectsExposureTests 不测预览刷新；XCUITest 不点特效；gui_smoke 无特效。
   （是否要做「开关即自动重算」是产品决策；但至少应有测试断言当前约定的 UX，例如「参数已变更，请重新生成」的显式提示，或自动刷新。）

---

## 6. 盲区分级与 Top5

| 级别 | # | 盲区 | 关键证据 |
|---|---|---|---|
| **P0** | 1 | 特效「是否真的生效」不可测：7/15 特效全断言 no-op 可过；4 个特效在门禁 fixture 上 0% 像素变化 | 4.2 探针；run_tests.py:779-783,858-884,902-919 |
| **P0** | 2 | 特效切换不刷新预览、无任何测试覆盖（用户「开了没效果」感知的直接放大器） | 5.3；AppViewModel.swift:158-192、ContentView.swift:78-157 |
| **P0** | 3 | 测试隔离的数据丢失：run_tests 删除整个 track/（用户进度）；gui_smoke 删除根 app_settings.json/queue_state.json | 第 7 节；run_tests.py:697-699,1132-1134；gui_smoke.py:302-303,325-326,376-377 |
| **P1** | 4 | UI 外观/布局/可读性零门禁：XCUITest 6 用例 0 外观断言；Tk 仅 1 条间隙检查；无截图/snapshot/设计 token 测试 | 5.1/5.2；SmokeUITests.swift；gui_smoke.py:356-360 |
| **P1** | 5 | XCUITest 事实在 412 之外且证据链断裂（3/3→4→U4-U7「见下方补记」悬空；当前 6 用例无结果；CI observe） | 3.3；TEST_REPORT.md:187-188,234,306；ci.yml |
| P2 | 6 | 11/15 特效无 golden 锚点，视觉回归不可发现 | 3.4；tests/golden/golden_matrix.json |
| P2 | 7 | 部分断言在受限环境恒真：stress S5 内存（ps 被禁→0MB）、chibi「opencv 可用」恒 True | 2.2/4.3；stress_protocol.py:237-244、run_tests.py:913 |
| P2 | 8 | 注册数量/全 id 集合未锁死（只测 8 子集；协议 effects 只测 dict） | run_tests.py:749-753,582-583 |
| P2 | 9 | 参数端点/UI 默认值/其余 4 个 preset/vertical mirror/tolerance 等未覆盖 | 4.3-8 |
| P3 | 10 | 文档 stale：ARCHITECTURE.md:47 写「Swift 测试 51 项」，实际 78 | 实测 |

**Top5（给 Lead 摘要用）**：
1. 特效效果零有效断言（7/15 no-op 可过、10 处仅「不崩溃」）。
2. 切换特效不触发预览刷新，且无测试覆盖（交互因果链断点）。
3. run_tests 删除用户 track/ 进度；gui_smoke 删除用户 settings/queue（测试会毁数据）。
4. UI 外观完全无门禁（XCUITest 无外观断言、无 snapshot 基线）——「UI 不好看」既不能验收也不能防回归。
5. 「412 全绿」口径外挂 XCUITest（observe + 无证据）+ 11/15 特效无 golden + 受限环境恒真断言，导致门禁数字高于实际保障。

---

## 7. 测试隔离 / 环境污染

### 7.1 实测副作用（详见 logs/isolation_observations.md）

| 严重度 | 发现 | 证据 |
|---|---|---|
| **高** | run_tests.py 在核心协议测试结束时 **shutil.rmtree(仓库/track)**：run_tests.py:697-699 与 :1132-1134。track/ 是**用户进度自动保存**功能目录（AppViewModel.swift:614-626 以 stableKey(image_path) 命名；TEST_REPORT.md:96 明列为功能）。运行前实测 track/ 有 13 个 json（含 10 个 hash 进度键 + 3 个历史测试键），权威 run_tests 后整个目录消失；重跑 run_tests 后再次消失。**用户在有进度时跑测试会静默丢失进度。** | pre/post 观察；代码行 |
| **高** | gui_smoke.py **无条件删除真实仓库根** queue_state.json（L302-303/L325-326）与 app_settings.json（L376-377），而这两者分别是「队列持久化/设置持久化」功能文件（TEST_REPORT.md:31,39）。 | 代码 + 结束态 app_settings 不存在 |
| 中 | run_tests.py 经协议 settings_set 把测试值写入**仓库根 app_settings.json**（L635-638 → core/settings.py:13-15 默认路径=仓库根）；结束态该文件存在且为测试值（palette=MARD 221, cell_px=60, window_w=0）。**违反 ARCHITECTURE.md:165-166 自己写的「不得污染仓库根 history.json/app_settings.json/queue_state.json」**。 | post_run_snapshot.txt |
| 中 | Swift/stress 测试把 track/test.json、track/echo_test_key.json、track/stress_s2.json 及若干 hash 键文件留在仓库 track/（gitignored）。 | EngineTests.swift:218、InteractionRaceTests.swift:109、结束态 track 列表 |
| 中 | 每套件都会改写 output/：本次 50 个旧产物全部被 prune 替换（run_tests 的裁剪 + 各套件生成）。按任务要求属预期、不清理；但意味「跑门禁会删掉此前全部中间产物」。 | pre/post 文件 diff：pre-existing removed 50 / new 51 |
| 低 | gui_smoke.py:629 写系统剪贴板（轻微系统状态副作用）。 | 代码行 |
| 环境 | 沙箱禁用 ps → stress S5 内存断言恒真；swift test 原命令因嵌套 sandbox-exec 拒绝而失败。 | probe_stress_s5_ps.log；swift_test_rawcmd_failure.log |

### 7.2 依赖执行顺序 / 系统状态的可疑点

- **跨套件共享 output/**：run_tests 会 prune 真实 output/（keep=50）。并发跑 swift test/stress 会被删中间产物 → 假失败（报告 3.1 与 ARCHITECTURE.md:161-162 均已记载；本报告按串行执行规避）。
- **跨套件共享 track/**：run_tests 清空 track、swift/stress 写 track，互不影响结果但造成残留。
- **canary 用例**依赖 output/ 内文件 mtime 分布；修复后不再依赖具体状态（两种状态实测均通过）。
- gui_smoke 依赖真实 Tk 窗口/可用的 GUI session；无头环境会失败（未纳入 macOS CI）。
- stress_protocol S5 依赖系统 ps（受限环境退化为恒真）。
- run_tests 的「文件不存在返回 None」会打印 traceback（预期，不影响计数），容易被误判为失败。
- 未发现依赖剪贴板内容、系统语言、时区、网络、历史残留数据来决定通过/失败的用例（除上述 output/track 文件副作用外）。

### 7.3 版本库污染检查

- 结束 git status --porcelain：仅 ?? qa/（本报告与探针；qa/gates/logs/ 等被 .gitignore 忽略）。
- output/、track/、history.json、queue_state.json、app_settings.json、app/.build、app/.derivedData 均被 .gitignore 覆盖（.gitignore:365-373），**没有未忽略的仓库根 .json 污染**。
- 但「git 看不到」不等于「用户数据安全」：track/progress 与 settings 属于用户数据，见 7.1。

---

## 8. 建议新增的回归用例（可直接实施）

> 原则：把「用户体验」翻译成可计算的代理指标（方向/强度/可见度/像素/布局），并提交可复跑的 golden 基线。
> 建议新增文件而不是继续堆 test_effects；新套件需串行执行并隔离 output/track（见 8.4）。

### 8.1 引擎层（tests/run_tests.py 新增 test_effects_visual_quality()，或新文件 tests/effect_quality_tests.py）

1. **特效必须改变输出（no-op 守卫）**：对 15 个 id 各选一张「非退化 fixture」（渐变+多色块图；chibi 用合成人脸图）：
   assert changed_cell_ratio > 0.01 or changed_chart_pixels > 0.01，否则失败。可立刻抓住当前 7 个 vacuous 用例。
2. **方向性断言**：
   - adjust：brightness 0.7/1.3 → 平均亮度严格递增；saturation 0/2 → 平均彩度递增；contrast 0.7/1.4 → 亮度标准差递增；
   - neon：输出平均亮度 < 输入、平均饱和度 > 输入；
   - grayscale：max(rgb)-min(rgb) <= 20（已有，保留）；
   - mirror：grid[y][x] == base[y][W-1-x]（cell 级精确翻转，horizontal/vertical 各一）；
   - crop：只保留指定区域；用「四象限不同颜色」图断言输出仅含左上象限颜色；
   - duotone：输出颜色到 color1-color2 连线的投影残差（ΔE）≤ 阈值，且自定义颜色生效；
   - cel_shade：每通道不同取值数 ≤ levels，且与原图色相偏差 ≤ 阈值；
   - max_colors/preset：输出色 ⊆ 保留集合；preset 的 5 个选项逐一断言与目标色板最近色 ΔE ≤ 10（不是只数个数）；
   - dither：渐变图上相邻格颜色差的平均绝对值下降（平滑度）；strength=0 时与基线一致（参数端点）；
   - outline_edge：高对比图边缘覆盖率在 [2%, 40%]；纯色图变化 0%；**默认 threshold=40 的路径单独测**；
   - outline_cell：多色图描边像素比例在 [1%, 30%]；width=1/2/3 单调；默认不描外轮廓、显式开启有外轮廓（现有）；
   - bg_remove：tolerance 0→120 空格数单调不减；--color 自定义色生效。
3. **注册与 schema**：assert set(list_effects()) == 15 id 全集；assert get_spec('outline_edge').params['threshold'].default == 40 等 UI 默认值。
4. **组合顺序语义**：对固定输入，断言「几何→预处理→网格→图纸」顺序下特定组合的输出（如 mirror 后再 outline 的翻转等价性：outline(mirror(img)) == mirror(outline(img)) 可作为不变量）。
5. **视觉 golden**：为上述 15 个特效各生成一张固定 fixture + 固定参数的 finished PNG，提交到 tests/golden/effects/；比较用感知容差（CIELAB ΔE 直方图/平均绝对差 ≤ 阈值），避免跨平台字节差异；提供 tests/golden/update_effect_golden.py 重生成脚本。这样修复/回归时「效果变了」能被发现。

### 8.2 Swift VM 层（app/Tests/PerlerAppTests/EffectsExposureTests.swift 扩展）

6. testToggleEffectRefreshesPreview：生成一次并记录 chartImage 的像素哈希；toggle ditherOn；等待自动（若产品实现自动重算）或断言状态提示「参数已变更，请重新生成」（若保持手动），防止「开了没反应」再次成为感知缺陷。
7. testEffectToggleChangesRenderedPixels：生成 baseline → 开 mirror（水平）→ 再生成 → 读回 chartPath PNG，断言像素分布与 baseline 不同（镜像方向可抽样断言），验证 UI→引擎→预览全链路真实变化。
8. testAllEffectsPerceptibleWithDefaults：对 15 个默认参数逐个开启生成，断言输出与 baseline 差异率 > 1%（chibi 用合成人脸 fixture；bg_remove 用白底图）；就是「默认即可感知」的产品承诺测试。
9. testGenerateWithAllEffectsActuallyAppliesThem：把当前只断言 lastResult != nil 的用例升级为同时断言结果图与无特效基线不同。

### 8.3 UI 外观层

10. **SwiftUI 快照单测（推荐，无需 UI 自动化权限）**：用 ImageRenderer 渲染 ContentView（注入固定 VM 状态）为 NSImage，按 1100/1280/暗色 3 个配置存 golden（app/Tests/PerlerAppTests/AppearanceSnapshotTests.swift），用感知哈希/ΔE 容差比较。可检测「UI 变丑/错位/配色回归」。
11. **XCUITest 外观断言（SmokeUITests.swift 扩展）**：
    - testEffectsToggleUpdatesPreview：点开特效开关→生成→XCUIScreen.main.screenshot() 前后哈希不同；
    - testLayoutAtMinWidth：窗口缩到最小宽度，断言关键控件 frame 不重叠/不被裁剪（element.frame 几何断言）；
    - testAppearanceBaselineLightDark：亮/暗各截图与基准做感知 diff（附件存档，先 observe 后转必过）；
    - 特效面板 15 个 Toggle 全部可见可点（当前无任何特效 UI 测试）。
12. **Tk 版外观**：至少对「主窗口 1100×800 截图 + 色卡窗口」存基准图并在 gui_smoke 中做尺寸/边界断言；若要「好看」验收，需先有设计 token/规范（由 UI 任务给出），测试断言颜色/字体/间距常量。

### 8.4 测试基础设施（先修隔离，否则新测试也会踩坑）

13. 在四套件入口统一把 OUTPUT_DIR / TRACK_DIR / SETTINGS_FILE / QUEUE_FILE / HISTORY_FILE 重定向到 tempfile.mkdtemp()（或在 runner 中注入环境变量），并新增：
    test_no_repo_persisted_files_touched：运行前后对仓库根 *.json 与 track/ 做哈希/存在性对比，必须不变。
14. stress S5：ps 不可用时用 resource.getrusage(RUSAGE_CHILDREN)/psutil 或显式 report(..., 'SKIP: ps unavailable')，禁止静默恒真；chibi 的「opencv 可用」改为真实断言（检测器能返回人脸）或标注 SKIP。
15. CI 与门禁口径对齐：把 stress_protocol、macOS gui_smoke 纳入必过 job；XCUITest 稳定后移除 continue-on-error；在门禁脚本输出中注明「不含视觉/外观」。

---

## 9. 未决问题与边界

1. **swift test 原命令在本会话无法执行**（DSH 沙箱拒绝嵌套 sandbox-exec + ~/Library 不可写）。已用 --disable-sandbox 复现 78/78；普通终端/CI 下原命令历史为绿（报告与 ci.yml 可佐证），但本次审计**无法在「原命令」下独立确认**。
2. **XCUITest 未运行**：需要 xcodebuild + GUI 自动化权限，且报告自述 runner 偶发超时。当前 6 个用例无本次结果；报告 3/4/U4-U7 的数字与当前文件不一致，无法核验。
3. **首个 run_tests 后台尝试被 harness 回收**：权威数据来自随后严格串行重跑；两次 run_tests 均 230/0，故不影响数字，但「从完全 pristine 的 output/ 开始」未单独测（output/ 为运行期产物，任务要求不清理）。
4. **track/ 前值只做了文件名级留档**（13 个 json 名字，见 logs/isolation_observations.md），其内容已被删除、无法恢复；因此「丢失的是否恰为真实用户进度」只能由命名机制（stableKey(image_path)）推断，不能逐字节证明。
5. 本轮只审计有效性/隔离，不评价特效算法本身优劣（task-1 负责）与 UI 设计方案（task-2 负责）；本报告为它们提供「为什么门禁发现不了」的机制解释。
6. 报告口径提醒：TEST_REPORT.md 的 412 是历史快照（2026-09-30），本次复跑环境（macOS 27.0.1 / Swift 6.4 / Xcode 27.1 / 新 PyPI 版本）与报告环境不完全相同（报告写 Python 3.11.15 / Pillow 12.3 / numpy 2.4.6，本次一致；OS/Xcode 版本报告未详述）。

---

## 10. 复现命令（严格顺序、勿并发）

    cd /Users/chen/Desktop/learn/PerlerBeadApp

    # 1) 引擎自动化（230 项）
    conda run --no-capture-output -n pindou python tests/run_tests.py

    # 2) Tk GUI 冒烟（92 项，需要可用的 macOS 图形会话）
    conda run --no-capture-output -n pindou python tests/gui_smoke.py

    # 3) 协议压力（12 项）
    conda run --no-capture-output -n pindou python tests/stress_protocol.py

    # 4) Swift 测试（78 项）
    cd app && swift test --disable-sandbox   # 普通终端可去掉 --disable-sandbox，见 2.2

审计探针（只读、save=False、临时目录，可与门禁分开跑）：

    conda run --no-capture-output -n pindou python qa/gates/probes/test_discrimination_probe.py
    conda run --no-capture-output -n pindou python qa/gates/probes/stress_s5_ps_probe.py

---

## 11. 证据文件清单

| 文件 | 内容 |
|---|---|
| qa/gates/results.json | 机器可读的套件数字/环境/审计结论 |
| qa/gates/report.md | 本报告 |
| qa/gates/logs/run_tests.log / run_tests_rerun.log | run_tests 两次完整输出（[PASS] 230/0） |
| qa/gates/logs/run_tests_tail200.log | tail（≤200 行） |
| qa/gates/logs/gui_smoke.log / gui_smoke_tail200.log | gui_smoke 92/0 |
| qa/gates/logs/stress_protocol.log / stress_protocol_tail200.log | stress 12/0 |
| qa/gates/logs/swift_test.log / swift_test_workaround.log / swift_test_tail200.log | swift 78/0（--disable-sandbox） |
| qa/gates/logs/swift_test_rawcmd_failure.log | 原命令 swift test 在沙箱下 exit=1 的原始报错 |
| qa/gates/logs/probe_test_discrimination.log | 特效断言判别力探针（17 用例/8 vacuous/7 特效全 vacuous） |
| qa/gates/logs/probe_stress_s5_ps.log | ps 被禁导致 S5 内存断言恒真的复现 |
| qa/gates/logs/pre_run_snapshot.txt / post_run_snapshot.txt | 运行前后 output/根 .json/track 状态 |
| qa/gates/logs/isolation_observations.md | 隔离/污染时间线（含 track/ 运行前的 13 个文件名） |
| qa/gates/logs/*.meta | 每套件起止时间/退出码/耗时 |
| qa/gates/probes/test_discrimination_probe.py | 可重跑判别力探针 |
| qa/gates/probes/stress_s5_ps_probe.py | 可重跑 ps/内存断言探针 |

---

## 附录 A：TEST_REPORT 关键行号索引（用于争议核对）

- 412 终态表：TEST_REPORT.md:486-497（230/92/12/78=412）
- 第 3 章旧门禁 395/1 与 canary flaky：TEST_REPORT.md:321-332、:423-430
- XCUITest 3/3 声明：TEST_REPORT.md:187-188；4 项：:234；U4-U7 悬空补记：:306
- 特效「输出质量探针+像素 diff」声明：TEST_REPORT.md:276-287；探针已删除：:312
- 已知限制（描边网状）：TEST_REPORT.md:294-296；docs/ARCHITECTURE.md:186-187
- 项目隔离约定：docs/ARCHITECTURE.md:165-166；并发陷阱：:161-162
- 测试目录/数量 stale：docs/ARCHITECTURE.md:47（51 项 vs 实测 78）
