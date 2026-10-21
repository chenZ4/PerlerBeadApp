# T7 测试隔离修复 + 最终门禁复测报告

| 项 | 值 |
|---|---|
| Shared Task | task-7（owner: gate-verify） |
| 执行时间 | 2026-10-21 22:20–22:35（Asia/Shanghai） |
| 仓库 | /Users/chen/Desktop/learn/PerlerBeadApp，branch dev-2.0，HEAD 3b7393d |
| 依赖 | T5（effects-qa，22:19 completed）、T6（ui-audit completed）；本报告在两者之后执行 |
| 写作用域 | tests/run_tests.py、tests/gui_smoke.py、tests/stress_protocol.py（仅隔离改动）、qa/gates/；另经 Lead 批准扩展 core_server.py「仅路径配置」 |
| 约束遵守 | 未 git commit/push；未回滚/覆盖他人改动；未删除/弱化既有断言 |

---

# 2.5.0 二轮改造最终门禁复测（T8/T9/T10/T11，2026-10-21 23:23–23:28）

> 本节是最新门禁终态（由 T11 执行）；下方 T7/2.2.0 段落保留为历史对照。
> 注意：2.2.0（T7）的证据目录已归档到 qa/gates/logs/final_2.2.0/；qa/gates/logs/final/ 现在保存 2.5.0 证据。

## A. 背景

- T8 预览缩放/平移硬伤修复（P0）、T9 老钱风棕色主题 + 开始页 photo→beads hero 视觉统一、T10 独立验证（缩放/平移事件级复现 + 棕色主题一致性）；ui-audit 随后补 P3 锚点修复（isFlipped=true + 16pt padding 坐标换算），view-verify 复验 swift test 111/111、dragcheck PASS。
- core/version.py 工作区版本 = 2.5.0（门禁时尚未提交；门禁后 Lead 提交为 26a0b64 / 95fe228）。
- 本轮为只读门禁复测：未改源码/测试，未 git commit/push。

## B. 最终门禁终态（严格顺序、无并发）

| # | 步骤 | 命令 | 耗时 | 退出码 | 通过 | 失败 | 用户数据副作用 | 日志 |
|---|---|---|---|---|---|---|---|---|
| 1 | run_tests | conda run -n pindou python tests/run_tests.py | 69.1s | 0 | **249** | **0** | **0** | qa/gates/logs/final/run_tests.log |
| 2 | gui_smoke | conda run -n pindou python tests/gui_smoke.py | 20.3s | 0 | **92** | **0** | **0** | qa/gates/logs/final/gui_smoke.log |
| 3 | stress_protocol | conda run -n pindou python tests/stress_protocol.py | 69.5s | 0 | **12** | **0** | **0** | qa/gates/logs/final/stress_protocol.log |
| 4 | swift test（PERLER_* env 注入） | cd app && swift test --disable-sandbox | 42.3s | 0 | **111** | **0** | **0** | qa/gates/logs/final/swift_test_isolated.log |
| 5 | swift build | cd app && swift build --disable-sandbox | 1.0s | 0 | — | — | **0** | qa/gates/logs/final/swift_build.log |
| — | **合计** | — | **≈202s** | — | **464** | **0** | **0** | qa/gates/logs/final/isolation_diff.json |

- **精确数字：249 + 92 + 12 + 111 = 464**，与 Lead 预期一致（此前 463 的差异来自 P3 锚点修复新增 1 个 ZoomPan 测试）。
- swift test 的 111 项 = 既有 84 + ZoomPanTests 11（T8，含 P3 锚点 1 项）+ VerifyZoomPanTests 15（T10）+ AssetTests 1（T9）。
- 用户数据隔离：5 个步骤对 track/、根 history.json/queue_state.json/app_settings.json/my_colors.json、output/、data/ 的 sha256 全部前后一致（side_effects=0）；根 json mtime 保持 2026-10-21 22:11:03 不变。证据 qa/gates/logs/final/isolation_diff.json。
- 失败 0、flaky 0；本轮**未**再跑 bare swift 残留审计（T7 已确认 bare 只新增测试键/prune output、不删用户 track 键，机制未变）。

## C. 测试数变化（2.2.0 → 2.5.0：437 → 464）

| 套件 | 2.2.0 | 2.5.0 | 变化 | 说明 |
|---|---|---|---|---|
| run_tests | 249 | 249 | 0 | — |
| gui_smoke | 92 | 92 | 0 | — |
| stress_protocol | 12 | 12 | 0 | — |
| swift test | 84 | 111 | +27 | 全部为 app/Tests 新增文件：ZoomPanTests 11 + VerifyZoomPanTests 15 + AssetTests 1 |
| **合计** | **437** | **464** | **+27** | 既有 84 项 Swift 测试文件计数未变；无删除/弱化 |

## D. 状态与遗留

- 门禁运行期间 HEAD=4736fed，工作区含 T8/T9/T10 未提交改动；门禁结束后 Lead 提交为 26a0b64（feat 2.5.0 老钱风/hero/缩放平移）与 95fe228（docs 二轮验证）。app/core/tests 在门禁前后无内容变化（门禁结束后无源码/测试写入；当前仅 README/TEST_REPORT/ARCHITECTURE/version.py 为 Lead 未提交 docs/版本改动）。
- 沿用 T7 遗留风险：① bare swift test 需 CI 注入 PERLER_* env（否则 prune output，但不删用户 track 键）；② stress S5 在 ps 不可用时内存断言恒真；③ DSH 沙箱下 swift test/build 需 --disable-sandbox；④ UI 外观自动化仍以 T10 独立验证 + qa/ui/after 截图人工验收为主（VerifyZoomPanTests 覆盖缩放/平移几何，不等于视觉审美断言）。
- 证据：qa/gates/logs/final/（2.5.0 全套）；qa/gates/logs/final_2.2.0/（T7/2.2.0 历史归档）。

---

---

## 0. 结论摘要

1. **最终门禁全绿：run_tests 249/0、gui_smoke 92/0、stress_protocol 12/0、swift test 84/0、swift build 通过；合计 437/0。**
   与 412 基线相比 +25 = run_tests +19（T5 新增回归）+ swift test +6（T5 AutoPreviewTests）。无失败、无 flaky。
2. **测试数据隔离修复完成并验证：Python 3 套件 + 环境注入的 swift test 对仓库用户数据（track/、根 *.json、output/、data/）的副作用为 0。**
   修复前 T3 审计的「删 track 用户进度 / 删 queue_state+app_settings / 写入仓库根 app_settings / 替换 output 全部产物」已全部消除。
3. **Swift 测试零副作用仅在 PERLER_* env 注入下成立**：bare swift test（不注入 env）仍会新增 10 个 track 测试键并 prune 最多 50 个 output 中间产物，但**不删/不改写任何既有 track 用户进度键、不改根 json**（审计 PASS）。CI 必须注入 env，开发态可接受（见遗留风险）。
4. **计数核对：230（T3 基线）+ 19（T5 新增执行项）- 0（移除/弱化）= 249。**
   T5 自述「原 228 + 新增 21 = 249」的分解有误（228 与实测基线不符；新增实际为 19 = 18 视觉结构 + 1 协议 warnings）；但 249 终值与代码一致。**经逐行 diff 确认 T5 未删除/合并任何既有用例、未修改既有断言行，无弱化。**
5. 重要口径修正：task-7 要求的「原 230 + 新增 X - 移除 Y = 249」中 **X = 19、Y = 0**（不是 21）。
6. 遗留风险：① bare swift test 的 output prune（建议 CI/env 注入）；② stress S5 内存断言在 ps 不可用时恒真；③ DSH 沙箱下 swift test/build 需 --disable-sandbox；④ T3 指出的 UI 外观零自动化断言仍未修（不属 T7 范围）。

---

## 1. 最终门禁结果（严格顺序，无并发）

| # | 步骤 | 命令 | 起止 | 耗时 | 退出码 | 通过 | 失败 | 仓库用户数据副作用 | 日志 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | run_tests | conda run -n pindou python tests/run_tests.py | 22:28:09→22:29:16 | 66.2s | 0 | **249** | **0** | **0** | qa/gates/logs/final/run_tests.log |
| 2 | gui_smoke | conda run -n pindou python tests/gui_smoke.py | 22:29:19→22:29:39 | 19.6s | 0 | **92** | **0** | **0** | qa/gates/logs/final/gui_smoke.log |
| 3 | stress_protocol | conda run -n pindou python tests/stress_protocol.py | 22:29:41→22:30:49 | 67.7s | 0 | **12** | **0** | **0** | qa/gates/logs/final/stress_protocol.log |
| 4 | swift test（env 注入） | cd app && swift test --disable-sandbox | 22:30:53→22:31:39 | 45.5s | 0 | **84** | **0** | **0** | qa/gates/logs/final/swift_test_isolated.log |
| 5 | swift build | cd app && swift build --disable-sandbox | 22:31:56→22:31:57 | 1.0s | 0 | — | — | **0** | qa/gates/logs/final/swift_build.log |
| A | bare swift 残留审计 | cd app && swift test --disable-sandbox（无 env） | 22:32:02→22:32:43 | 41.7s | 0 | 84 | 0 | 110（仅允许项，见 §3.2） | qa/gates/logs/final/swift_test_bare_audit.log |

- **主门禁合计 437/0**（249+92+12+84）；耗时合计约 200s（不含 bare 审计）。
- 每个通过数由日志 [PASS] 行 / XCTest Executed N tests 计数，非脚本自报。
- swift 命令在本 DSH 沙箱必须加 --disable-sandbox（与 T3 相同：嵌套 sandbox-exec 被拒 + ~/Library SwiftPM 缓存不可写）；普通终端/CI 可去掉，不影响测试语义。
- 结构化逐步骤证据：qa/gates/logs/final/isolation_diff.json（含每个步骤 side_effects 明细与 bare 审计结论）。

### 1.1 失败/flaky

- **失败：0**；**flaky：0**。
- run_tests 在 T7 期间共完整跑 4 次：① 隔离首次跑 248/1（唯一失败是 canary 用例依赖仓库 output/ 预置 50 个文件，见 §2.3，属 T7 隔离暴露的隐藏依赖而非产品/用例 flaky）；② 加入 fixture 后 249/0；③ final_gate 首轮 249/0；④ 分步 final gate 249/0。之后稳定。
- gui_smoke 21.0s / 19.6s、stress 76s / 67.7s 多次运行通过数稳定。

---

## 2. 测试隔离修复（实现）

### 2.1 改动清单（T7 scope）

| 文件 | 改动 | 说明 |
|---|---|---|
| core_server.py | +39/-1 行：新增 6 个 PERLER_* 路径 env 覆盖（_env_override_path） | 仅路径配置，无业务逻辑；未动 T5 的 warnings 字段；未设置 env 时与原行为一致（见 2.2 实测） |
| tests/run_tests.py | +~60 行隔离代码、改 4 行路径 | 进程内 monkeypatch + 子进程 env 继承；track 清理改为只删临时目录；canary 用例补 52 个 filler（见 2.3）；**断言未改** |
| tests/gui_smoke.py | 设置/队列/历史/输出重定向 TEST_DIR；删除操作只作用临时文件 | 不再触碰仓库根 app_settings.json / queue_state.json |
| tests/stress_protocol.py | 顶部设置 PERLER_* env | EngineHandle 已用 dict(os.environ,...) 继承，5 个压测段全部自动隔离 |

### 2.2 core_server.py 的 env 契约（Lead 批准的方案 A）

支持 6 个环境变量，仅影响路径常量；未设置时保持仓库内默认路径：

    PERLER_OUTPUT_DIR      -> module OUTPUT_DIR（并同步 core.processor.OUTPUT_DIR）
    PERLER_TRACK_DIR       -> TRACK_DIR
    PERLER_SETTINGS_FILE   -> core.settings.SETTINGS_FILE + SettingsStore.__init__ 默认参数
    PERLER_QUEUE_FILE      -> core.settings.QUEUE_FILE
    PERLER_HISTORY_FILE    -> core.history_manager.HISTORY_FILE（同时把 LEGACY 重定向到同目录 legacy_history.json）
    PERLER_MY_COLORS_FILE  -> core.my_colors.MY_COLORS_FILE

实测（独立进程导入 core_server）：
- 不设 env：OUTPUT_DIR / TRACK_DIR / SETTINGS / QUEUE / HISTORY / MY_COLORS 全部等于仓库内默认路径（无行为变化）。
- 设 env：6 个路径全部指向指定临时目录；spawn 引擎 generate 的 chart_path、track_save 文件、settings_set 文件均落在临时目录。

### 2.3 隔离过程中发现并修复的隐藏依赖（不弱化断言）

run_tests 的协议级 canary 用例原本依赖「仓库 output/ 里已有 50 个更旧产物」：prune_output(keep=50) 只有在目录内条目 > 50 时才会删除 canary。
- 隔离后 output/ 是空临时目录 → 首次隔离运行该用例失败（248/1）。
- 修复：在隔离 output 目录内预置 52 个 mtime=now 的 filler 文件（名字以 perler_prune_ 开头，测试 finally 自动清理），使 canary 仍是最旧文件 → 断言语义与原用例完全一致且不再依赖仓库历史产物。
- 这不是弱化：断言原文未改，反而把「依赖真实 output/ 状态」的隐藏环境依赖变成显式 fixture。

---

## 3. 隔离前后副作用对照

### 3.1 修复前（T3 审计实测，2026-10-21 21:40–21:50；证据 qa/gates/logs/pre_run_snapshot.txt / post_run_snapshot.txt / isolation_observations.md）

| 用户数据 | 修复前门禁运行后的变化 | 根因代码 |
|---|---|---|
| track/（用户进度 stableKey(image_path).json） | 运行前 13 个文件 → run_tests 后整个目录被删除 | tests/run_tests.py 旧 L697-699 / L1132-1134 的 shutil.rmtree(仓库/track) |
| app_settings.json | 不存在 → 被 run_tests 协议 settings_set 创建为测试值（cell_px=60, window_w=0） | 旧 core_server 默认 SETTINGS_FILE=仓库根 |
| queue_state.json | 被 gui_smoke 无条件删除 | tests/gui_smoke.py 旧 L302-303、L325-326 |
| app_settings.json | 又被 gui_smoke 无条件删除 | tests/gui_smoke.py 旧 L376-377 |
| output/ | 50 个既有中间产物 100% 被 prune 替换（新增 51 个） | run_tests 的 save=True + 引擎 prune |
| history.json | 备份后恢复（轻微临时改写，崩溃时可能丢失备份） | 旧 run_tests 直接读写仓库根 |
| my_colors.json | 测试结束被 clear 删除 | 旧 run_tests my_colors 用例 |

### 3.2 修复后（T7 最终门禁 22:28–22:33，证据 qa/gates/logs/final/isolation_diff.json）

| 步骤 | 副作用条数 | 明细 |
|---|---|---|
| run_tests（249/0） | **0** | track/、根 *.json、output/、data/ 前后 sha256 全一致 |
| gui_smoke（92/0） | **0** | 同上 |
| stress_protocol（12/0） | **0** | 同上 |
| swift test（PERLER_* env 注入，84/0） | **0** | 引擎 output/track/settings 全部写临时目录 |
| swift build | **0** | 仅 app/.build 构建缓存（gitignored，非用户数据） |
| bare swift（残留审计，84/0） | 110（允许） | track 新增 10 个测试键，0 删除/0 改写；output 新增 50 + prune 50；根 *.json 0 变化；audit verdict = PASS |

- 门禁期间仓库根 history.json / queue_state.json / app_settings.json 的 mtime 始终保持 2026-10-21 22:11:03、sha256 不变（history/queue = 97d170e1…，settings = 20dd4bda…）。
- bare swift 审计结论：**bare swift test 不会删除/改写既有 track 用户进度键**（user_data_removed_or_changed = []）；但会 prune 旧 output 中间产物（本次 50 个）→ 记为「开发态可接受、CI 必须注入 env」。

---

## 4. 测试计数核对（230 → 249 分解 + 412 → 437）

### 4.1 净增分解

| 口径 | 数值 | 证据 |
|---|---|---|
| T3 基线（2026-10-21 21:43，两次运行一致） | **230 / 0** | qa/gates/logs/run_tests.log、run_tests_rerun.log |
| T5 + T7 后最终 | **249 / 0** | qa/gates/logs/final/run_tests.log |
| 新增 PASS 名称（baseline multiset diff） | **+19** | 18 个 T5 视觉结构 + 1 个协议 warnings |
| 移除 PASS 名称（baseline multiset diff） | **0** | 无任何既有用例消失/改名 |
| **核对式** | **230 + 19 - 0 = 249** | 与实测 249 一致 |

### 4.2 新增 19 项明细

- 协议 warnings（1）：generate 响应含 warnings 字段（协议向后兼容）。
- T5 特效质量回归（18）：邻接描边去黑网、平涂保留轮廓、线稿覆盖率可读、线稿连续、赛璐璐不压暗、赛璐璐不崩坏、风格色板用色≤预设、风格色板不洗白、风格色板近白不激增、grayscale/cel_shade/duotone 各自保持透明背景（3 项）、背景去除保留内部白色主体、背景去除未触边给 warning、chibi 无脸 warnings、dither 钳制、dither 钳制 warning、crop 默认明显裁剪。
- 说明：新增函数 test_effect_quality_fixes 有 16 个静态 report() 调用；其中「透明背景」检查在 for eid in (grayscale, cel_shade, duotone) 循环内 → 动态 3 项；因此 16 静态调用执行出 18 个 PASS。

### 4.3 T5 自述「原 228 + 新增 21 = 249」为什么不成立

- 「原 228」与事实不符：T3 权威基线为 230/0（两次独立运行，日志留档），T5 改动后既有 230 项名称 multiset 完全保留（移除 0）。
- 「新增 21」与实际代码/执行不符：新增 16 个静态 report()（执行 18 项）+ 协议 warnings 1 项 = **19**。
- 终值 249 正确；但分解应为 **230 + 19 - 0 = 249**。

### 4.4 是否存在既有用例被删/合并/弱化 —— 逐行核对结论：**无**

- git diff -U0 tests/run_tests.py 的删除行在 T5 完成时 = **0 行**（T5 对 run_tests.py 为纯新增）。
- 当前工作区组合 diff 中 tests/ 四个文件的删除行共 8 行，**全部是 T7 隔离改动**（TRACK_DIR 定义、GUI 历史重定向、legacy/track/escape 三处路径、注释替换），不涉及任何断言。
- 静态 report() 计数按函数逐个对比：18 个既有函数的 report() 数量除 test_core_server 25→26（T5 新增 warnings 1 项）外**全部不变**；test_effects 仍 23 个、test_audit_regressions 仍 16 个、test_robustness 仍 32 个。
- PASS 名称 multiset：删除集合为空；不存在同名断言被弱化的迹象（断言行未被修改）。

### 4.5 412 → 437

| 套件 | 基线 | 最终 | 变化 |
|---|---|---|---|
| run_tests | 230 | 249 | +19（T5 新增） |
| gui_smoke | 92 | 92 | 0 |
| stress_protocol | 12 | 12 | 0 |
| swift test | 78 | 84 | +6（T5 AutoPreviewTests 6 项） |
| **合计** | **412** | **437** | **+25** |

- 新增用例均为行为/结构断言，不是凑数。golden 按项目规范重生成：8 配置中仅 outline_cell 一个哈希更新（b72744b8…），其余逐字节一致（T5 报告 + git diff tests/golden/golden_matrix.json 仅 1 行变更）。

---

## 5. 与 T3 审计遗留问题的关系

| T3 遗留 | T7 后状态 |
|---|---|
| P0 测试删用户 track 进度 / 删 settings/queue | **已修复并实测验证（0 副作用）** |
| P0 特效效果断言无效（7/15 no-op 可通过） | T5 已新增 18 项视觉结构断言（覆盖 T3 指出的重点盲区）；完整验证以 T5 报告 qa/effects/T5_report.md 为准（本任务只核对计数与门禁） |
| P0 切换特效不刷新预览 | T5 已实现 scheduleAutoPreview + 6 项 Swift 单测（AutoPreviewTests），本门禁 84/0 通过 |
| P1 UI 外观零自动化断言 | **仍未解决**（不属 T7/T5 范围）；T6 产出真实启动截图（qa/ui/after/）供人工验收；建议后续加 SwiftUI snapshot + XCUITest 外观断言（T3 report §8.3） |
| P1 XCUITest 不在 412 且证据链断裂 | 仍不在 412；本轮未运行 XCUITest（需 xcodebuild + GUI 自动化，超 task-7 范围） |
| P2 stress S5 内存断言在受限环境恒真 | 未改（不属隔离范围）；记为遗留风险 |

---

## 6. 遗留风险与建议

1. **bare swift test 仍会写仓库 output/ 与 track 测试键（不删用户数据）**。建议：把 PERLER_* env 注入写进 .github/workflows/ci.yml 的 swift-tests job（一行 env 块），或在 app/Tests 增加隔离初始化；本轮因写作用域限制未改 CI/App。
2. **stress_protocol S5 内存断言**：ps 不可用（本沙箱）时 rss_kb 返回 0，断言恒真；建议改为 psutil/resource 或显式 SKIP。
3. **DSH 沙箱**：swift test/build 原命令会因嵌套 sandbox-exec 失败，本报告统一用 --disable-sandbox；这是环境限制不是产品问题。
4. **PERLER_* 6 个环境变量是新的部署/CI 契约**，建议在 docs/ARCHITECTURE.md 的测试策略/环境章节补 3-5 行说明（本轮未改文档，避免与 Lead 正在编辑的 README/ARCHITECTURE 冲突）。
5. **UI 外观自动化仍为零**：T6 重构后「好看」只能人工/截图验收；建议按 T3 报告 §8.3 增加 SwiftUI ImageRenderer 快照基线。
6. app 启动冒烟：本轮未重复执行；T6 已用真实启动 + 截图验证最终 UI（qa/ui/after/harness_current_1280_light_v2.png 等），且 swift build 通过。若需独立启动冒烟可另行安排。

---

## 7. 复现命令

分步最终门禁（本会话单次执行上限 120s 的 workaround；无上限环境可直接跑 final_gate.py）：

    cd /Users/chen/Desktop/learn/PerlerBeadApp
    conda run --no-capture-output -n pindou python qa/gates/final_gate_step.py run_tests
    conda run --no-capture-output -n pindou python qa/gates/final_gate_step.py gui_smoke
    conda run --no-capture-output -n pindou python qa/gates/final_gate_step.py stress_protocol
    conda run --no-capture-output -n pindou python qa/gates/final_gate_step.py swift_test_isolated
    conda run --no-capture-output -n pindou python qa/gates/final_gate_step.py swift_build
    conda run --no-capture-output -n pindou python qa/gates/final_gate_step.py swift_test_bare_audit
    conda run --no-capture-output -n pindou python qa/gates/final_gate_step.py merge

一体版（无 120s 限制时）：

    conda run --no-capture-output -n pindou python qa/gates/final_gate.py

单独跑门禁（隔离已内置）：

    conda run --no-capture-output -n pindou python tests/run_tests.py
    conda run --no-capture-output -n pindou python tests/gui_smoke.py
    conda run --no-capture-output -n pindou python tests/stress_protocol.py
    cd app && swift test --disable-sandbox
    cd app && swift build --disable-sandbox

---

## 8. 证据文件清单

| 文件 | 内容 |
|---|---|
| qa/gates/logs/final/isolation_diff.json | 最终门禁逐步骤结果 + 副作用明细 + bare swift 审计结论 |
| qa/gates/logs/final/run_tests.log / gui_smoke.log / stress_protocol.log | 3 个 Python 套件完整输出（249/92/12） |
| qa/gates/logs/final/swift_test_isolated.log / swift_build.log / swift_test_bare_audit.log | Swift 步骤输出（84/0、build 成功、bare 84/0） |
| qa/gates/logs/final/partial_*.json | 分步运行的中间结果（含每步快照 diff） |
| qa/gates/logs/final/precheck_run_tests2.log（249/0）、precheck_gui.log（92/0）、precheck_stress.log（12/0） | T7 隔离预检记录 |
| qa/gates/logs/final/precheck_before2.txt / precheck_after2.txt 等 | 隔离预检前后快照（diff 为空） |
| qa/gates/logs/pre_run_snapshot.txt / post_run_snapshot.txt / isolation_observations.md | T3 修复前副作用基线 |
| qa/gates/logs/run_tests.log / run_tests_rerun.log（T3 230/0）、gui_smoke.log、stress_protocol.log、swift_test.log（T3 78/0） | 计数核对基线证据 |
| qa/gates/isolation_plan.md | 隔离修复设计与行号清单（实施前） |
| qa/gates/probes/isolation_design_probe.py + qa/gates/logs/probe_isolation_design.log | 隔离设计原型验证（17/17 PASS） |
| qa/effects/T5_report.md、qa/effects/fixes/metrics_after.json | T5 新增用例/修复的交付证据 |
| qa/ui/after/harness_current_*.png | T6 最终 UI 启动截图（人工验收证据） |

---

## 9. T7 变更文件（仅列本任务改动）

| 文件 | 改动用途 |
|---|---|
| core_server.py | 6 个 PERLER_* 路径 env 覆盖（仅路径配置；未改 warnings 等业务逻辑） |
| tests/run_tests.py | 隔离初始化、track 清理路径、history legacy 路径、escape 断言目标、canary fixture（52 fillers） |
| tests/gui_smoke.py | 设置/队列/历史/输出重定向 TEST_DIR；清理逻辑只作用临时目录 |
| tests/stress_protocol.py | 顶部 PERLER_* env（子进程继承） |
| qa/gates/final_gate.py / final_gate_step.py | 最终门禁 + 隔离验证脚本（含 120s 分步 workaround） |
| qa/gates/isolation_plan.md / final_report.md / probes / logs | 设计、证据与报告 |

说明：工作区其它 20+ 个文件改动来自 T5（core/effects、core/processor.py、AppViewModel、Models、tests/run_tests.py、golden、AutoPreviewTests）与 T6（ContentView、DesignSystem、ColorChartView、PerlerApp、qa/ui）以及 Lead 的 README/ARCHITECTURE/version/.gitignore 更新；T7 未回滚、未覆盖这些改动。