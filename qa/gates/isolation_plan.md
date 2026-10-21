# T7 测试隔离修复设计（只读准备，尚未动代码）

| 项 | 值 |
|---|---|
| 依据 | T3 审计（qa/gates/report.md 第 7 节）+ task-7 描述 |
| 基线 | branch dev-2.0，HEAD 3b7393d；当前 tests/ 三文件尚未被他人改动（git status 仅 .gitignore + DesignSystem.swift + qa/） |
| 约束 | 只改 tests/run_tests.py、tests/gui_smoke.py、tests/stress_protocol.py（仅隔离相关）+ qa/gates/；不改产品源码/既有断言强度；不 commit/push；等 task-5（effects-qa）完成后再动 tests/run_tests.py |
| 状态 | 本文件是**实施前设计**；行号基于当前 HEAD，T5 合入后需重新定位（内容不变、行号可能漂移） |

---

## 1. 违规点清单（现状，按文件:行）

| # | 文件:行 | 行为 | 后果 | 修复方式 |
|---|---|---|---|---|
| 1 | tests/run_tests.py:697-699 | shutil.rmtree(仓库/track) | 删用户进度（stableKey(image_path).json） | 改为 rmtree(临时 TRACK_DIR) |
| 2 | tests/run_tests.py:1132-1134 | 同上 | 同上 | 同上 |
| 3 | tests/run_tests.py:635-638（经 core_server 协议 settings_set） | 写仓库根 app_settings.json | 污染/覆盖用户设置 | 引擎子进程重定向 SETTINGS_FILE 到临时目录 |
| 4 | tests/run_tests.py:219-226,300-304 | 直接读写仓库根 history.json（有备份/恢复） | 短暂改用户历史；崩溃时丢失备份 | HISTORY_FILE 重定向临时目录 |
| 5 | tests/run_tests.py:925-942,1065-1073 | my_colors save/clear 写仓库根 my_colors.json | 删/覆盖用户自定义色卡 | MY_COLORS_FILE 重定向临时目录 |
| 6 | tests/run_tests.py:99-100,1322-1352 | ImageProcessor(save=True)+canary 写/裁剪仓库 output/ | 替换用户 50 个历史中间产物 | OUTPUT_DIR 重定向临时目录 |
| 7 | tests/run_tests.py:550-552,1082-1084,1322-1324 | spawn 真实 core_server.py（默认路径） | 子进程写仓库 output/track/settings | 子进程用隔离 bootstrap 启动 |
| 8 | tests/gui_smoke.py:302-303 | os.remove(真实 queue_state.json) | 删用户队列 | QUEUE_FILE 重定向临时目录 |
| 9 | tests/gui_smoke.py:325-326 | 同上 | 同上 | 同上 |
| 10 | tests/gui_smoke.py:376-377 | os.remove(真实 app_settings.json) | 删用户设置 | SETTINGS_FILE 重定向临时目录 |
| 11 | tests/gui_smoke.py:371-374 | load_settings() 读真实设置 | 结果依赖用户数据（非确定性） | 同上（注入默认实例到临时路径） |
| 12 | tests/stress_protocol.py:48-51 | spawn 真实 core_server.py 写仓库 output/track | 残留 stress_s2.json + output 产物 | bootstrap 隔离 |
| 13 | tests/run_tests.py:1280-1283（test_output_prune） | 临时改写 core_server.OUTPUT_DIR，但被 `real_output` 引回真实 output/ | canary 进真实 output/ | 顶层 OUTPUT_DIR 已隔离后自动变为临时（保留测试语义） |

**根本机制**：路径常量分散在 4 个模块，且 `SettingsStore.__init__` 的默认参数在 def 时绑定：
- core/processor.py:14 `OUTPUT_DIR = BASE_DIR/output`；ImageProcessor.__init__ 用模块全局（core/processor.py:50）
- core/settings.py:13-15 `SETTINGS_FILE/QUEUE_FILE`；:36 def __init__(self, settings_file=SETTINGS_FILE, ...) 默认值已绑定
- core/history_manager.py:9-11 `HISTORY_FILE/LEGACY_HISTORY_FILE`；:28 `file_path or HISTORY_FILE`（调用时查模块全局→可 patch）
- core/my_colors.py:8-9 `MY_COLORS_FILE`（函数内查模块全局→可 patch）
- core_server.py:21 `from core.processor import ... OUTPUT_DIR`（导入时绑定）；:100 `TRACK_DIR = __file__/track`（模块级绑定）；:526 `def serve()`
- ui/app_controller.py:21 `from core.processor import ... OUTPUT_DIR`；:56 `SettingsStore()`；:59 `HistoryManager()`

## 2. 设计方案

### 2.1 进程内（run_tests / gui_smoke）

每套件在**导入 core 模块之后、创建任何 ImageProcessor/SettingsStore/HistoryManager 之前**执行一次隔离初始化：

    ISO_ROOT = tempfile.mkdtemp(prefix='perler_iso_')        # 全局持有，atexit 清理
    ISO_OUT   = ISO_ROOT/output; ISO_TRACK = ISO_ROOT/track; ...
    import core.processor as _cp, core.settings as _cs, core.history_manager as _chm,
           core.my_colors as _myc, core_server as _csm
    _cp.OUTPUT_DIR = ISO_OUT; os.makedirs(ISO_OUT, exist_ok=True)
    _csm.OUTPUT_DIR = ISO_OUT; _csm.TRACK_DIR = ISO_TRACK
    _chm.HISTORY_FILE = ISO_ROOT/history.json
    _chm.LEGACY_HISTORY_FILE = ISO_ROOT/legacy_history.json
    _myc.MY_COLORS_FILE = ISO_ROOT/my_colors.json
    _cs.SETTINGS_FILE = ISO_ROOT/app_settings.json; _cs.QUEUE_FILE = ISO_ROOT/queue_state.json
    _cs.SettingsStore.__init__.__defaults__ = (_cs.SETTINGS_FILE, _cs.QUEUE_FILE)
    HISTORY_FILE = _chm.HISTORY_FILE  # 覆盖 run_tests 顶部 from ... import HISTORY_FILE 的本地绑定

要点：
- `SettingsStore.__init__.__defaults__` 必须一起改，否则模块级 load_settings()/save_settings()/load_queue()/save_queue() 仍用 def 时绑定的真实路径。
- gui_smoke 的 patch 必须放在 `from ui.app_controller import AppController` **之前**：ui/app_controller.py:21 在 import 时绑定 OUTPUT_DIR；:56/59 在实例化时用 SettingsStore/HistoryManager。
- gui_smoke 现有 `_hm.HISTORY_FILE = TEST_DIR/history.json`（L38-40）保留并把 LEGACY 一并重定向；本地 QUEUE_FILE 在 patch 后重新赋值。
- run_tests 的 test_history 改为使用临时 HISTORY_FILE/LEGACY（保留备份-恢复逻辑与断言）。
- track 清理两处（L697-699/L1132-1134）只删临时 TRACK_DIR；测试语义（track 持久化到项目目录）保持不变，仅目录换成隔离目录。
- 结尾在 main()/脚本末尾 finally 中 shutil.rmtree(ISO_ROOT, ignore_errors=True)；atexit 兜底。

### 2.2 子进程（run_tests 3 处 + stress_protocol 全部 EngineHandle）

test 启动真实引擎时不再直接 `[python, repo/core_server.py]`，而是写一个**隔离 bootstrap** 到 ISO_ROOT 并用它启动：

    # ISO_ROOT/engine_bootstrap.py（测试运行时生成，不入库）
    import os, sys
    ROOT, TMP = <repo>, <ISO_ROOT>
    sys.path.insert(0, ROOT)
    import core.processor as p, core.settings as s, core.history_manager as h, core.my_colors as m
    p.OUTPUT_DIR = os.path.join(TMP, 'output'); os.makedirs(p.OUTPUT_DIR, exist_ok=True)
    h.HISTORY_FILE = os.path.join(TMP, 'history.json'); h.LEGACY_HISTORY_FILE = os.path.join(TMP, 'legacy_history.json')
    m.MY_COLORS_FILE = os.path.join(TMP, 'my_colors.json')
    s.SETTINGS_FILE = os.path.join(TMP, 'app_settings.json'); s.QUEUE_FILE = os.path.join(TMP, 'queue_state.json')
    s.SettingsStore.__init__.__defaults__ = (s.SETTINGS_FILE, s.QUEUE_FILE)
    import core_server as cs
    cs.OUTPUT_DIR = p.OUTPUT_DIR; cs.TRACK_DIR = os.path.join(TMP, 'track')
    cs.serve()

启动命令：`[sys.executable, os.path.join(ISO_ROOT, 'engine_bootstrap.py')]`（stderr/stdout 管道语义与现在完全一致）。
因为先 patch 再 `import core_server`，core_server.py:21 的 `from core.processor import OUTPUT_DIR` 会拿到隔离值；:100 的 TRACK_DIR 在导入后被覆盖为临时目录；CoreServer.__init__ 里的 ImageProcessor()/HistoryManager()/load_settings() 全部落到临时路径。

覆盖点：
- tests/run_tests.py:550-552（test_core_server）
- tests/run_tests.py:1082-1084（test_robustness 协议段）
- tests/run_tests.py:1322-1324（test_output_prune 协议段）
- tests/stress_protocol.py:48-51（EngineHandle.__init__，S1-S5 全部复用）

### 2.3 副作用验证（新增 qa/gates/final_gate.py）

- 每个套件跑前/跑后分别快照：仓库根 track/（文件列表+sha256）、history.json、queue_state.json、app_settings.json、my_colors.json、output/（文件名+size+mtime）、数据目录 data/（只读校验）；生成 per-suite diff JSON。
- Python 3 套件期望 diff = 空；swift test 的残留单独记录（见 3）。
- 汇总写入 qa/gates/logs/final_isolation_diff.json + 最终报告 qa/gates/final_report.md。

## 3. 超出 task-7 写作用域的残留（需 Lead 决策）

**Swift 测试**（app/Tests）不受上述 Python 隔离影响：
- app/Sources/PerlerApp/Engine.swift:42-53 把 core_server.py 固定解析到仓库路径；:73-82 启动子进程时不注入路径环境变量（只认 PERLER_PYTHON 选解释器）。
- 证据（T3 实测）：swift test 会写仓库 output/（约 20 个文件/次）与 track/test.json、track/echo_test_key.json 及若干 hash 键文件；不删除用户 track 文件（键名不会与真实图片 stableKey 冲突），但 output/ 的 keep=50 prune 可能删掉旧的中间产物。
- 写作用域（task-7）不含 core_server.py / app/Tests，因此本轮**默认不修**，在 final_report「遗留风险」中写明。
- 可选方案（需 Lead 批准扩权或明确不做）：
  A. 在 core_server.py 增加 PERLER_OUTPUT_DIR/TRACK_DIR/SETTINGS_FILE/QUEUE_FILE/HISTORY_FILE 环境变量覆盖（约 10 行；但 core_server.py 属 task-5 写作用域，需 effects-qa 完成后再改并协调）；
  B. 只做 qa/gates 内的 final-gate 包装：生成「复制并 patch 路径的 core_server 副本 + PERLER_PYTHON 包装脚本」，用 `PERLER_PYTHON=wrapper swift test` 得到零副作用结果（不改产品源码，但开发者日常 bare swift test 仍有残留）；
  C. 接受残留，文档化并留 follow-up。

## 4. 实施步骤（等 task-5 completed 后）

1. re-read 最新 tests/ 三文件，重新定位行号（T5 会改 run_tests.py，新增视觉断言可能使行号漂移）。
2. 先改 gui_smoke.py、stress_protocol.py（与 T5 无冲突），再改 run_tests.py（T5 合入后）。
3. 单独跑 3 个 Python 套件 + final_gate 快照，确认零副作用且通过数与 T5 后的基线一致（不靠删用例变绿）。
4. 等 T6 完成（swift build 需 UI 重构稳定）→ 顺序跑 4 套 + swift build，写 qa/gates/final_report.md。
5. 清理 ISO_ROOT 临时目录；不 commit/push。

---

## 5. Lead 决策（2026-10-21 22:xx）：批准方案 A —— core_server.py 增加「仅路径」env 覆盖

批准范围：**只在 core_server.py 增加 6 个路径环境变量覆盖，不改任何业务逻辑**：
PERLER_OUTPUT_DIR / PERLER_TRACK_DIR / PERLER_SETTINGS_FILE / PERLER_QUEUE_FILE /
PERLER_HISTORY_FILE / PERLER_MY_COLORS_FILE。

影响：
- **Python 子进程隔离可简化为「测试进程 set os.environ → 子进程继承」**，不再需要 engine_bootstrap.py
  （bootstrap 方案已验证可用：qa/gates/probes/isolation_design_probe.py 17/17 PASS，保留作设计证据/回退方案）。
- **Swift 测试可零副作用**：final_gate.py 用 env 注入临时目录跑 swift test（Engine 子进程继承 env）。
- **bare swift test（不注入 env）仍走仓库默认路径**：按 Lead 要求做残留审计——只允许新增
  track 测试键与 output/ 产物；禁止删除/改写既有 track 用户进度键与根用户 json；
  output/ 被 prune 记为「开发态可接受，CI 必须注入 env」。

### 5.1 core_server.py 最小补丁草案（待 T5 完成后按最新文件落）

放在 imports 之后（约 L23 之后），并在原 TRACK_DIR 定义处改用 env 覆盖：

    # --- 测试/CI 路径隔离：环境变量优先（仅路径配置，无业务逻辑） ---
    def _env_path(name, default):
        value = os.environ.get(name)
        return os.path.abspath(value) if value else default

    OUTPUT_DIR = _env_path("PERLER_OUTPUT_DIR", OUTPUT_DIR)

    import core.processor as _processor_module
    _processor_module.OUTPUT_DIR = OUTPUT_DIR

    import core.settings as _settings_module
    _settings_module.SETTINGS_FILE = _env_path("PERLER_SETTINGS_FILE", _settings_module.SETTINGS_FILE)
    _settings_module.QUEUE_FILE = _env_path("PERLER_QUEUE_FILE", _settings_module.QUEUE_FILE)
    _settings_module.SettingsStore.__init__.__defaults__ = (
        _settings_module.SETTINGS_FILE, _settings_module.QUEUE_FILE)

    import core.history_manager as _history_module
    _history_module.HISTORY_FILE = _env_path("PERLER_HISTORY_FILE", _history_module.HISTORY_FILE)
    if os.environ.get("PERLER_HISTORY_FILE"):
        _history_module.LEGACY_HISTORY_FILE = os.path.join(
            os.path.dirname(_history_module.HISTORY_FILE), "legacy_history.json")

    import core.my_colors as _my_colors_module
    _my_colors_module.MY_COLORS_FILE = _env_path(
        "PERLER_MY_COLORS_FILE", _my_colors_module.MY_COLORS_FILE)

原 `:100` 改为：

    TRACK_DIR = _env_path("PERLER_TRACK_DIR",
                          os.path.join(os.path.dirname(os.path.abspath(__file__)), "track"))

注意：core_server.py 在 task-5 写作用域内，**必须等 task-5 completed 后**先读当前文件再落补丁，
若 T5 已改过相关路径逻辑则基于现状最小合并，严禁覆盖他人改动。

### 5.2 测试文件最终改法（等 T5 completed 后）

- **run_tests.py**：
  1) 顶部（imports 之后、任何 ImageProcessor 实例化之前）创建 ISO_ROOT 与子路径，
     设置 6 个 PERLER_* 环境变量（供 spawn 的 core_server 子进程继承），
     并对当前进程 monkeypatch core.processor.OUTPUT_DIR / core.settings.SETTINGS_FILE+QUEUE_FILE +
     SettingsStore.__init__.__defaults__ / core.history_manager.HISTORY_FILE+LEGACY / core.my_colors.MY_COLORS_FILE。
  2) L14 的本地 HISTORY_FILE 绑定改为 patch 后的值；test_history 的 legacy 改用隔离 LEGACY 路径。
  3) 两处 track rmtree（L697-699/L1132-1134）目标改为隔离 TRACK_DIR（或只删测试键），保留断言。
  4) 3 处 spawn（L550-552/L1082-1084/L1322-1324）无需改命令（env 继承即可），
     但 test_output_prune 的 canary 自动落隔离 OUTPUT_DIR。
  5) main() 末尾 + atexit 清理 ISO_ROOT（保留 TEST_DIR 语义/一并清理）。
- **gui_smoke.py**：
  1) 在 `from ui.app_controller import AppController`（L42）之前完成 monkeypatch：
     processor.OUTPUT_DIR、history.HISTORY_FILE+LEGACY、settings.SETTINGS_FILE+QUEUE_FILE、
     SettingsStore.__init__.__defaults__、my_colors.MY_COLORS_FILE；
     并把本地 QUEUE_FILE 重赋为隔离路径（L302-303/L325-326/L371-377 的删除/读取随之作用在 temp）。
  2) 结束 root.destroy 后清理 ISO_ROOT。
- **stress_protocol.py**：
  1) 顶部创建 ISO_ROOT，设置 6 个 PERLER_* env（EngineHandle 的 env=dict(os.environ,...) 已继承）。
  2) 结束清理 ISO_ROOT；S5 的 ps 恒真问题不在本任务范围，final_report 记录遗留。

### 5.3 final_gate.py（已按决策更新）

- 步骤：run_tests → gui_smoke → stress_protocol → swift test（注入 PERLER_* 到 tempfile）→
  swift build → bare swift test 残留审计（可 --skip-bare-swift）。
- 判定：主步骤退出码非 0 或任何主步骤出现仓库用户数据 diff → exit 2；
  bare swift 审计若删除/改写 track 用户键或根 json → exit 2；output/ prune 仅记录。
- 输出 qa/gates/logs/final/isolation_diff.json（含每步骤 side_effects 明细和 bare 审计结论）。

### 5.4 完成标准（task-7）

1. 3 个 Python 套件全绿且 per-suite 用户数据 diff 为空；
2. swift test（env 注入）全绿且 diff 为空；swift build 通过；
3. bare swift 审计 PASS（不删/不改用户 track 键与根 json；output/ prune 记录）；
4. qa/gates/final_report.md 写清：与 412 基线差异（T5 新增用例后的新数字）、隔离前后对照、
   Swift 零副作用仅在 env 注入下成立、遗留风险（S5 ps、bare swift output prune）；
5. 不 commit/push。
