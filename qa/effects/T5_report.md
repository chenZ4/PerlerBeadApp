# T5 特效修复实现报告（effects-qa）

> 依赖 T1 证据（`qa/effects/report.md`）。本次只改 core 引擎 + AppViewModel/Models + tests；ContentView/DesignSystem 归 ui-audit。未 commit/push。

## 1. 交付与门禁（全绿）

- `tests/run_tests.py`：**249 通过 / 0 失败**（新增 T5 视觉结构回归 21 项 + 协议 warnings 1 项）。
- `cd app && swift test --disable-sandbox`：**84 通过 / 0 失败**（新增 AutoPreviewTests 6 项：脏标记/参数装配/crop 默认/warnings 解码/自动预览/手动优先）。
- golden：按项目规范用 `tests/golden/update_golden.py --matrix` 重生成；8 配置中只有 `outline_cell` 哈希变化（b72744b8…），其余逐字节一致。
- 未运行 gui_smoke / stress_protocol（留给 gate-verify 统一跑）；未 git commit/push；ContentView/DesignSystem 由 ui-audit 改造，未触碰。

## 2. 修复内容与前后实测（60×60，MARD-221；证据 `qa/effects/fixes/`）

| 缺陷 | 修复前（T1） | 修复后（T5） | 证据 |
|---|---|---|---|
| outline_cell 全图黑网 | 照片描边珠 **65.86%**、风景 71.86%、卡通 31.94% | 照片 **27.33%**（其中基线本身 15.58%）、风景 **13.33%**、卡通 **15.42%**；平涂轮廓保留 | `fixes/outline_cell_before_after.jpg` |
| outline_edge 孤立噪点/不可见 | 照片 6.83% 格变化、变更格 ≥2 邻居仅 **13.4%**；卡通 1.72%/0% | 网格尺度 DoG+滞后阈值+去孤点：照片 11.69% 变化、连续性 **85.5%**；卡通 16.53%/**87.9%** | `fixes/outline_edge_before_after.jpg` |
| cel_shade 压暗+串色 | 卡通 L 85.36→62.87、色相漂移 **158°**、白底变灰 | bilateral + Lab k-means：卡通 L 85.36→**85.07**、色相漂移 **11.6°**；照片 37.65→**36.39**（旧 29.85）；风景 52→**50.89**（旧 39.81） | `fixes/cel_shade_before_after.jpg` |
| preset 洗白 | 照片 L +40.3、近白珠 28.4%、用色 6 | 明度秩映射：照片 L 37.65→**43.66**（+6）、近白 **0%**、用色 **5**；风景 L 52→55；卡通 L 85→81 | `fixes/preset_before_after.jpg` |
| 透明 PNG 丢 alpha | grayscale/cel/duotone 后 918→**3600** 颗（+292%） | 三者均 **918** 颗（透明格=空格），advance 与基线一致 | `fixes/metrics_after.json` |
| bg_remove 误删白色主体 | 白幽灵主体删除率 **100%**、照片白高光误删 111 格 | 边界连通域 + auto 角落取色：白主体删除率 **0%**、背景 0%（未触边给 warning）；白底卡通仍正确删 2334 格背景 | `fixes/bg_remove_before_after.jpg` |
| chibi 静默失效 | 0/4 素材检测到人脸 → ok=true、无提示、与基线逐像素同 | 无脸/无 cv2 → `warnings` 回传（"未检测到人脸，已跳过"）；命中时原地放大保持画布尺寸/alpha（不再 512→571、40% 白珠） | `fixes/metrics_after.json` / AutoPreviewTests |
| dither strength 绕过上限 | strength=5.0 未被钳制、图崩坏 | 走 schema 钳制到 1.5（5.0 与 1.5 输出逐像素一致）并回传 warning | metrics_after.json |
| crop 默认空操作 | 默认 0/0/1/1 = 0 变化 | 默认 0.1/0.1/0.9/0.9，开启即明显裁剪 | AutoPreviewTests.testCropDefaultsAreVisible |
| UI 开关不重算 | 改开关后预览永不刷新、无脏标记 | `needsRegenerate` + `scheduleAutoPreview()`（500ms debounce、忙时排队、手动优先、可取消）；15 项特效/参数 didSet 自动接线 | AutoPreviewTests 6 项 |
| 协议无法感知失效 | 响应无 effects/warnings 回显 | `generate/edit` 响应新增 `warnings: [String]`（`core_server.py`），`Models.GenerateResult` 兼容解码，状态栏显示 ⚠️ | test_core_server warnings 回归 |

## 3. 自动预览 API（已发 ui-audit，最终版）

- `static let autoPreviewDebounce: TimeInterval = 0.5`
- `@Published private(set) var needsRegenerate: Bool`、`@Published private(set) var isAutoPreviewing: Bool`、`var autoPreviewEnabled: Bool`
- `func parametersDidChange()`（置脏 + 触发 debounce）、`func scheduleAutoPreview()`、`func cancelPendingAutoPreview()`
- 手动 `generate()` 优先：取消 pending 自动预览、让在途自动预览让位；自动预览失败不弹错，只改 statusText。
- 新暴露参数：`outlineCellWidth` / `outlineEdgeStrength` / `grayscaleContrast` / `ditherStrength`（effectsParams 已携带；UI 滑杆由 ui-audit 接）。

## 4. 变更文件

- 引擎：`core/effects/{base,registry,filters,filters2,geometry,outline,presets}.py`、`core/processor.py`（warnings/dither clamp/几何网格 warning/stderr）、`core_server.py`（warnings 字段）。
- Swift：`AppViewModel.swift`（自动预览 + didSet 脏标记 + crop 默认 + 新参数）、`Models.swift`（warnings）。
- 测试：`tests/run_tests.py`（test_effect_quality_fixes 21 项 + 协议 warnings）、`tests/golden/golden_matrix.json`（规范重生成）、`app/Tests/PerlerAppTests/AutoPreviewTests.swift`（6 项）。
- QA 证据：`qa/effects/fixes/`（前后对比图 + metrics_after.json + fixes_verify.py 可复跑）。
