# 拼豆图纸 · 测试报告（冻结版 v1.0.0）

日期：2026-08-03
测试环境：macOS（Apple Silicon），conda 环境 `pindou`（Python 3.11，Tk 8.6，Pillow 12.3，numpy 2.4，tkinterdnd2）

> 运行方式：`conda run -n pindou python main.py`（Tk < 8.6 会明确提示）

## 一、测试结果总览

| 测试套件 | 通过 | 失败 | 结果 |
|---|---|---|---|
| `tests/run_tests.py`（无界面自动化，含 Golden/耗时/输入防御） | 54 | 0 | ✅ |
| `tests/gui_smoke.py`（GUI 冒烟，全程零弹窗零交互） | 67 | 0 | ✅ |
| `main.py` 真实启动 | — | — | ✅ |
| **合计** | **121** | **0** | **✅ 交付** |

## 二、冻结版功能清单（本次迭代全部完成）

### 核心（阶段 0）
- **预览缩放重构**：`tk.Label` → `tk.Canvas`，任何缩放级别（400%）下缩放条始终可见；滚轮/快捷键 ±/适应窗口/百分比滑块
- **输出清晰度解耦**：每格像素（默认 60，可自定义 16~160）+ 总边长 12000px 保护；150×150 网格输出 9000px+ 清晰图
- **历史反推迁移**：旧"总画布像素"自动反推为每格像素（1500/50 → 30）
- **性能**：numpy 向量化颜色匹配（零误差，10000 像素 0.05s）；`hex_codes` 缓存；色卡搜索 250ms 防抖；预览渲染 8192px 上限；删死代码
- **健壮性**：Tk<8.6 启动守卫 + 异常弹窗 + 非法宽高/hex 输入容错

### 数据安全（阶段 1）
- **批量文件名防覆盖**：文件名含源图名，冲突自动追加序号（实测 2 张同尺寸不同源图导出 2 个文件）
- **"在文件夹中显示"**：保存/导出成功后弹窗一键定位（mac `open -R` / win `explorer /select`）

### 顺手（阶段 2）
- **设置持久化**：`app_settings.json`（色卡/每格像素/开关/网格颜色/窗口尺寸），重启恢复
- **快捷键**：Cmd/Ctrl+O 选图、S 保存、P 导出 PDF、E 导出 PNG、+/- 缩放
- **成品尺寸 cm 提示**：实时显示"成品约 30×30 cm（每颗 5mm）"
- **比例语义修正**："按原图比例（宽为基准）"+"等比完整（适应框内）"（min 逻辑，实测 30×30 框竖图 → 7×30）

### 体验（阶段 3）
- **拖拽选图**：任意位置拖入图片（tkinterdnd2）
- **批量可取消**：⏹ 取消按钮 + 逐行取消回调，完成后汇总（成功/失败/剩余）
- **队列持久化**：`queue_state.json` 重启恢复
- **队列缩略图**：Treeview 48px 缩略图 + 文件名/格式/尺寸
- **1:1 PDF 拼接增强**：8mm 出血重叠区 + 裁剪参考线 + 页码（第 x/y 页）

### 增值（阶段 4）
- **成品效果预览**：一键切换无网格/无文字的纯色成品图（实测生成并切换正常）
- **预览拖动平移**：放大后按住左键拖动查看细节（边界钳制不越界，双击恢复居中，适应窗口模式自动锁定居中）

## 三、内存数据（tracemalloc）
- 连续 20 次生成：峰值 < 150MB，驻留 < 60MB
- GUI 10 次生成+渲染：峰值 < 200MB，驻留 < 80MB
- PhotoImage 替换前 blank、PIL 图替换前 close、grab 释放、渲染节流均已覆盖

## 四、已知限制
1. **手动格子编辑**（点击换色）→ v2 立项，本次不做
2. 1:1 PDF 的出血/页码为栅格绘制，拼贴效果需打印后人工确认（页数/尺寸已自动验证）
3. Windows 端主题（clam）与 Ctrl 快捷键逻辑已实现，需在 Windows 机器跑一次 gui_smoke 最终确认

## 五、运行与测试
```bash
conda run -n pindou python main.py                # 运行
conda run -n pindou python tests/run_tests.py     # 自动化测试（54 项）
conda run -n pindou python tests/gui_smoke.py     # GUI 冒烟（67 项，零弹窗）
```

## 结论
121 项测试全部通过（GUI 测试全程零弹窗、零人工交互），冻结版 v1.0.0 满足交付条件。

---

# 2.0 交付记录（2026-08-03，dev-2.0 分支）

## 测试终态（全自动，零人工交互）

| 套件 | 通过 | 说明 |
|---|---|---|
| `tests/run_tests.py` | 107 | 引擎：协议层/特效库/色卡文件化/MyColors/模板/BOM/编辑 |
| `tests/gui_smoke.py` | 67 | Tk 版回归保底（零弹窗） |
| `swift test` | 5 | SwiftUI 壳协议层 + 编辑/追踪 |
| Tk / Swift app 启动 | ✅ | 均验证 |
| **合计** | **179 项** | 全绿 |

## 2.0 新增功能

### 引擎层（core_server 服务化，JSON 协议）
- stdio 行协议：请求/响应/进度事件/即时取消（读线程处理）
- **特效库 14 个**（全部默认关闭+参数 schema）：邻接描边、线稿描边、黑白、抖动(Floyd-Steinberg)、深色底、亮度/对比度/饱和度、限色数、风格预设×5（马卡龙/Preppy/万圣节/圣诞/Cottagecore）、大头(chibi/OpenCV)、赛璐璐、霓虹、双色调、背景去除(透明空格)、镜像、裁剪
- 加权 RGB 匹配（感知权重）
- **色卡 JSON 文件化**（data/palettes/*.json 动态加载+校验+兜底）
- **My Colors 自定义调色板**（粘贴色号/重命名/只用我的颜色生成）
- 板数网格（29/58/87）、BOM 材料清单（CSV+PDF 材料页）、PDF 黑白打印模式、内置模板库×6、透明 PNG

### SwiftUI 壳（Mac 原生 + 玻璃设计）
- 毛玻璃材质面板（.ultraThinMaterial/.regularMaterial）+ 圆角卡片，深浅色自动适配
- 预览：适应窗口/缩放滑块/拖动平移/成品效果切换
- 色卡窗口：分组网格 + 搜索 + 点击复制（毛玻璃）
- 手动格子编辑：点击换色/撤销（引擎 overrides 增量更新）
- 进度追踪：自动保存续做（track_save/load）
- 导出 PNG/PDF（含 BOM 页）

## 数据与依赖
- `data/palettes/`（4 套色卡 JSON）、`data/templates/`（6 模板）、`my_colors.json`（用户色卡，gitignore）
- `requirements.txt`：Pillow==12.3.0 / numpy==2.4.6 / tkinterdnd2==0.6.2 / opencv-python==4.14.0
- 运行：`cd app && swift run`（SwiftUI）或 `conda run -n pindou python main.py`（Tk 保底）

## 回滚
- master + tag v1.0.0 保持 1.0 冻结版；2.0 在 dev-2.0 分支，失败 `git checkout v1.0.0` 即回滚

---

# 2.2.0 修复记录（2026-08-15，全面代码审查修复）

## 测试终态

| 套件 | 通过 | 说明 |
|---|---|---|
| `tests/run_tests.py` | 191 | 新增鲁棒性 + 全流程 E2E（异常输入/空格特效/协议安全/取消/退出） |
| `tests/gui_smoke.py` | 87 | 新增幽灵弹窗/假死注入/撤销去重/损坏历史/定时器残留回归 |
| `swift test` | 60 | 新增取消/UTF-8 分块/stderr 排空/编辑取消/进度持久化回归 |
| **合计** | **338 项** | 全绿 |

## 修复清单

### 崩溃级（core）
- 特效 × 空格：`max_colors` 对透明格 `np.bincount` 崩溃、`preset` 负索引填色 → 空格保持空格；grid 特效后 `total_beads` 重算（此前与图例统计矛盾）
- 损坏历史记录（字符串 width/output_size、缺字段）不再让引擎启动失败；队列坏项跳过；网格上限 500 三层钳制（防 OOM）；cell_size 字符串容错
- core_server 协议：错误/取消响应不再被 `ok:True` 包裹（客户端把错误当成功解码）；取消排队期间请求生效；reader 对非对象 JSON 免疫；stdin EOF 哨兵 → 进程优雅退出（不再僵尸）

### 安全（core_server 协议）
- `track_load/save` key、`template_id` 路径穿越校验；`my_colors_save` 非法数据拒绝写入；`export_png` 异常路径 close
- 每请求图像对象 `close()`（常驻进程内存不再随生成膨胀）；`_last_progress` 清理

### Tk UI
- 批处理异常后 `is_processing` 永久假死（finally 引用未绑定变量）→ 预初始化 + 异常提示
- 历史面板移除"选中即加载"（幽灵警告框/意外重载）；历史记录补存实际网格与 show_legend
- 色卡窗口关闭后 after 定时器残留 TclError；撤销栈去重（FocusOut/KeyRelease 不再污染）
- 换图时预览面板清引用（已关闭 PIL 图不再被渲染）；滚轮 bind_all 收束 + 关闭解绑；导出路径统一异常捕获；缩略图缓存上限

### Swift
- stderr 独立队列读取（串行队列饿死 → 管道写满引擎假死）；闭包弱捕获（引用循环 → 僵尸 Python 进程）
- `cancel(rid:)` 不再覆盖 pending 条目；编辑请求支持取消；忙时点击忽略；undoEdit 持久化进度
- 预览 offset 双重应用修复（拖动后点击错位）；UTF-8 按字节切行（中文响应跨块丢字节）；长任务超时 120s；applyResult 移除与 saveTrack 竞态的 loadTrack

### 其他
- 常量单一来源（DEFAULT_PALETTE/CELL_PX/GRID/ACCENT/cm_hint）；特效公共函数提取；死代码清理；版本 2.2.0

---

# 2.2.1 修复与扩测记录（2026-08-21，dev-2.0）

## 测试终态（全自动，零人工交互）

| 套件 | 通过 | 说明 |
|---|---|---|
| `tests/run_tests.py` | 207 | +output 裁剪（沙箱单元+协议 canary）+golden 多配置矩阵（8 配置哈希+dither 结构断言） |
| `tests/gui_smoke.py` | 89 | +批量取消标志防御初始化回归 |
| `tests/stress_protocol.py` | 12 | 新增压力套件：取消风暴×24 双时序/长任务排队无丢失/垃圾输入轰炸/在途 EOF/RSS 内存基线 |
| `swift test` | 66 | +InteractionRaceTests 6 项（拖拽累加/迟到结果代币/track 回显/取消即时生效） |
| **合计** | **374 项** | 全绿 |

CI：GitHub Actions 四 job——Python 双平台矩阵 / Swift 真实引擎 / Windows Tk 冒烟（观察）/ XCUITest（观察）。

## 修复清单

### Swift 交互竞态五连修
- 拖拽偏移以手势起点为基准累加（多次拖拽不再跳回）；双击复位清基准
- `imageEpoch` 结果归属代币：换图/换模板递增，generate/edit 完成回调校验一致才应用，
  迟到结果只复位状态；忙时封堵预览区拖入与模板切换入口
- `track_load` 响应回显 key，VM 校验后才应用进度（快速换图晚到响应不覆盖）
- `Engine.onStart` 改同步调用（pending 注册后）：generate() 返回即可取消，
  消除 cancelActive 早于 onStart 的竞态窗口
- exportPNG 超时对齐 PDF 调至 120s

### core_server
- output/ 自动裁剪：generate/edit 落盘后按 mtime 只保留最新 50 个中间产物（防无限增长）
- 协议管道加固：stdin errors=replace（二进制垃圾字节在严格解码 locale 下打死 reader
  线程致引擎永久假死，已复现+验证）；stdout 强制 UTF-8（协议输出不随 Windows gbk 等 locale 漂移）

### Tk
- `_queue_cancel` 防御初始化（原依赖 process_queue 先执行才存在）

### 画质/性能（输出哈希已随 golden 重生成留档）
- 下采样 NEAREST→BOX（面积平均），照片类源图噪声显著降低
- 抖动距离改内积展开式（1.5x）+ 误差 clamp 到 [0,255]；展开式与旧式逐像素计算 100% 等价

## 扩测说明
- golden 矩阵只字节哈希逐元素运算路径（跨平台位稳定）；dither 走 BLAS matvec 有位差异，
  以结构断言覆盖（总量守恒/色域⊆色卡/映射改变）
- XCUITest：SPM 无法承载 UI 测试，新增 XcodeGen 工程规范（app/project.yml）+3 用例；
  **已本地验证 3/3 全绿**（启动+引擎初始化 / 模板→生成 E2E / 拖拽安全）。
  首跑排障记录：①Xcode 26 显式模块构建致多 target .swiftmodule 输出撞路径 →
  逐 target 显式 PRODUCT_MODULE_NAME + SWIFT_ENABLE_EXPLICIT_MODULES=NO；
  ②PRODUCT_NAME 需显式 $(TARGET_NAME)（否则产物名为空、CodeSign 失败）；
  ③完全禁签会让 macOS kill 未签名 xctrunner → 改 ad-hoc 签名（"-"）；
  ④SwiftUI Text 文本在 accessibility value 而非 label，模板 Picker 按 value='自定义' 定位。
  本机 brew 安装超时，改用 GitHub Releases artifactbundle 直装（~/.local/bin/xcodegen）

---

# 2.2.2 网格实时联动修复（2026-08-22，dev-2.0）

## 主诉
网格设置里底层联动正常，但另一侧输入框 UI 不刷新；且期望「原始比例」也参与联动。

## 根因与修复
### D1 · UI 不刷新（渲染层）
macOS SwiftUI TextField 已知缺陷：窗口内有字段正在编辑时，程序化绑定更新不会重绘
其他字段的显示文本。修复：GridFieldRow 改为 NSViewRepresentable 桥接 NSTextField，
`updateNSView` 对非焦点字段强制同步 stringValue → 联动值逐键即时上屏；
回车提交后若字段仍持焦点也回写规范化值。

### D2 · 原始比例/等比完整不联动（逻辑层）
新增 `imageAspect`（CGImageSource 读像素尺寸元数据，不解码整图），
`linkedDimensions` 对原始比例/等比完整按源图比联动：
改宽 w → 高=round(w×ih/iw)；改高 h → 宽=round(h×iw/ih)；无图不联动。
换图自动更新 aspect；模板加载仍显式设 gridW/H。

### 附带真 bug · 联动回声指纹未随换图失效
lastProgrammaticW/H 只在 writeLinked 时写入：图 A 联动后切到图 B，
若首次输入恰与旧结果相同会被误判为回声而跳过联动。已在 resetForNewImage 重置。

## 工况真值表（全部有测试锚定）
| # | 模式 | 图片 | 行为 |
|---|---|---|---|
| 1 | 固定比例(5种) | 任意 | 固定比联动（保持） |
| 2/3 | 原始比例 | 有图 | 双向按像素比联动（新增） |
| 4 | 原始比例/等比完整 | 无图 | 不联动 |
| 5 | 等比完整 | 有图 | 同原始比例规则（新增） |
| 6/7 | 非法输入 / 越界 | - | 不联动 / 先 clamp 再联动 |
| 8 | 程序回写 | - | 指纹抑制不重触发 |
| 9 | 换图/模板 | - | 指纹失效 + 显式设值不被覆盖 |
| 10 | UI 显示 | - | 逐键刷新无需回车（U4 实测） |

## 测试终态
- swift test 73 项（+7 工况单测）
- XCUITest 4 项（+U4 testGridLinkageRefreshesUI：typeText "6" 无回车断言高框即时变 "6"）

---

# 2.3.0 深度测试与修复记录（2026-09-08）

## 背景与输入

用户主诉：① 网格输入联动没解决（改宽/高，另一侧输入框不动）；② 特效几乎不可以用（效果不好）。
本轮以资深测试视角执行：定向探针 → 根因 → 修复 → 回归 → 全量门禁。

## 发现与修复

### F1 网格联动「没解决」——三层根因，全部修复

1. **引擎不 WYSIWYG（主根因，探针实锤）**：UI 联动用四舍五入，引擎 `int()` 截断且固定按
   较宽侧重算 → 全比例×编辑侧×尺寸 160 组合实测 **68 组不一致**（如 4:3 图改宽 40：
   UI 40×30 / 引擎 40×29；竖图 0.75 改宽 40：UI 40×53 / 引擎 39×53；fit_box 1.4 框 30：
   UI 30×21 / 引擎 29×21）。
   修复：引擎 WYSIWYG 候选路由（`processor.process_image`：请求=宽/高基准联动配对时原样
   生效；模糊请求保持旧语义=宽基准 / min-scale）；舍入统一**半上** `floor(x+0.5)`
   （对齐 Swift `.rounded()`；Python `round()` 是银行家舍入，x.5 向下，联动公式禁用，
   `core.models.link_dimensions` 已同步）。
   回归：run_tests `test_wysiwyg_link`（96 组真实引擎矩阵）+ 半上舍入用例 + aspect 联动
   用例；Swift `EffectsExposureTests` 2 项 VM 级（联动配对=引擎结果）。
2. **Swift 无图时不联动**：原始比例/等比完整在 `aspect=nil` 时完全不联动——默认态
   （打开 app 未选图）改宽/高另一侧永远不动，即用户感知的「没解决」。
   修复：无图按 1:1 兜底联动（选图后真实 aspect 接管）。
   回归：`GridModeTests.testOriginalRatioNoImageLinksSquare`。
3. **Tk 版无实时联动**：此前仅失焦/回车联动。修复：`<KeyRelease>` 实时联动（两侧均为
   合法整数才联动、不回写正在编辑的框）+ 按源图比例联动（`SettingsPanel.set_aspect`，
   选图/加载历史时由控制器更新）。
   回归：gui_smoke 3 项（1:1 实时联动 / 源图比联动 / 半输入不联动）。
   注：Tk 合成 `event_generate("<KeyRelease>")` 在本机 Tk 上不触发 widget 绑定
   （最小复现确认，`when="now"` 亦然），冒烟直调 `_on_key_release`。

### F2 特效「几乎不可以用」——两条线修复

1. **暴露面**：引擎注册 15 项特效但 Swift UI 仅 7 个开关。补齐 8 项入口（画面调整/
   裁剪/镜像/赛璐璐色阶/霓虹/双色调/背景去除/大头），带参数控件（滑杆/步进器/HEX 输入）；
   `effectsParams()` 按引擎四阶段（几何→预处理→网格→图纸）排序。
   回归：`EffectsExposureTests`（15 项装配/参数携带/全开真实引擎生成）。
2. **输出质量（探针逐项目检 + 像素 diff 量化）**：
   - **色卡匹配升级 CIELAB 感知色距**（`core/colors.py`，原加权 RGB）：
     渐变区噪点消失（测试图 35→33 色）、抖动的饱和色错色相噪点（红球绿斑）修复；
     `closest_indices`/`closest_indices_dithered`/`find_closest_color` 全部迁 Lab，
     误差扩散在 Lab 空间并 clamp。
   - 邻接描边 `outline_outer` 默认 True→False（细节图实测 58% 像素被描黑成网）；
   - 线稿描边 threshold 默认 100→40（原 0.9% 像素生效，几乎不可见）；
   - 赛璐璐只对亮度分桶 → 输出灰度图（语义错误），改 RGB 逐通道色阶保留色相；
   - 限色/风格色板的色间映射同步 Lab。
   - 输出变化属有意行为修正，golden 基准已按项目流程重生成
     （`update_golden.py --matrix`，8 配置）。

### 观察项（非产品缺陷）

- **套件并发陷阱**：run_tests 与 swift test 并发执行时互相失败（swift 引擎子进程写共享
  `output/` 并触发裁剪，会删掉对方刚生成的中间产物）——本轮实测 2 项假失败，单独跑全绿。
  已写入 ARCHITECTURE.md：套件必须顺序执行。
- XCUITest runner 偶发 "Timed out while enabling automation mode"（系统级抖动，
  重跑恢复）。
- 邻接描边在多色细节图上仍是网状（「所有相邻异色对画线」的语义本质），建议配合限色数
  使用，已记入已知限制。

## 门禁结果（全部由本轮独立执行，顺序运行）

| 套件 | 结果 |
|---|---|
| `tests/run_tests.py`（含 WYSIWYG 矩阵等新增回归 7 项） | 214/214 ✅ |
| `tests/gui_smoke.py`（含 Tk 实时联动 3 项） | 92/92 ✅ |
| `tests/stress_protocol.py` | 12/12 ✅ |
| `swift test`（含特效暴露/ WYSIWYG 新增 5 项） | 78/78 ✅ |
| XCUITest（U4-U7：逐键联动/切比例重联动/源图比联动/回车后续编辑） | 见下方补记 |

## 环境与边界

- 引擎测试环境：conda `pindou`（Python 3.11.15 / Pillow 12.3 / numpy 2.4.6 / opencv 4.14）。
- 全程读写限于项目文件夹内；xcodebuild DerivedData 钉在 `app/.derivedData`。
- 探针脚本 `tests/probe_*.py` 为临时产物（结论已并入正式回归），提交前删除。

---

# 3. 完整复测 + 逐行代码审计（2026-09-30）

执行人：测试工程师（独立复测）
环境：macOS arm64 / conda `pindou`（Python 3.11.15 / Pillow 12.3.0 / numpy 2.4.6 / OpenCV 4.14 / Tk 8.6）+ Swift 6.4

## 3.1 门禁套件复测（顺序执行，不可并发）

| 套件 | 通过 | 失败 | 结果 |
|---|---|---|---|
| `tests/run_tests.py` | 213 | 1 | ⚠️ 1 项 flaky（见 3.3-D） |
| `tests/gui_smoke.py` | 92 | 0 | ✅ |
| `tests/stress_protocol.py` | 12 | 0 | ✅ |
| `swift test`（`app/`） | 78 | 0 | ✅ |
| **合计** | **395** | **1** | 主体功能稳定 |

说明：`run_tests` 中「文件不存在返回 None」会打印预期 traceback，属文档已记载的无害现象。
唯一失败项为 `generate 自动触发裁剪（canary 已清理）`，根因见 3.3-D（测试隔离缺陷，非产品裁剪逻辑错误）。

## 3.2 深挖审计用例（本轮新增，不在门禁内）

针对逐行审计发现的疑似缺陷，写了独立验证脚本，实证结果如下：

| 用例 | 结果 | 证据 |
|---|---|---|
| 透明 PNG 左半不透明/右半透明 20×10 | **BUG 确认** | 期望 total≈100，实际=200 |
| 同尺寸全不透明对照 | 正常 | total=200 |
| `bg_remove` 特效路径（可产生 RGBA） | 正常 | 纯色背景 total=0 |
| board=14 源图 4:3 舍入 | **BUG 确认** | `round`=10，`half_up`=11 |
| fit_box 模糊请求 30×30 + 源图 40×20 | **BUG 确认** | 引擎 30×15，历史记 30×30 |
| 协议 `grid_color="#C8C8C8"` | **BUG 确认** | `tuple(str)` → `('#','C','8',…)` |
| 协议 `settings_set` 传入非法类型 | **BUG 确认** | `cell_px=['a']`/`show_grid={}` 被落盘 |
| 协议 `settings_set` 传入 `"boom"` | 轻微 | handle 抛 ValueError，worker 捕获不崩 |
| 历史迁移 width=50.7 | **BUG 确认** | 保留 float 未转 int |
| 批量文件名 600×600 vs 引擎 500×250 | **BUG 确认** | 文件名未用 clamp 后尺寸 |
| 协议 generate 透明 PNG | **BUG 确认** | total=200（与处理器同根因） |

## 3.3 代码审计发现（按严重级别）

### A. 【高】透明 PNG 输入 alpha 被提前丢弃 — 功能缺陷

**位置**：`core/processor.py:110-111` vs `163-166`

```python
with Image.open(image_path) as opened:
    img = opened.convert("RGB")   # ← alpha 在此丢失
...
if small_img.mode == "RGBA":     # ← 源图路径下永远为 False（死代码）
    alpha_mask = ...
```

- 注释写明「支持 RGBA：透明像素为空格，无珠」，但源图在进入管线时已被转 RGB。
- 透明区 `convert("RGB")` 后变成实色（通常为原 RGB 或黑），被计为色豆。
- 仅当 `bg_remove` 等 preprocess 特效**之后**产生 RGBA 时，空格逻辑才生效（特效路径正常）。
- 影响面：Tk 版 / Swift 版 / 协议 generate 全部入口；透明底素材、带 alpha 的贴纸图。
- **修复建议**：`Image.open` 后保留 `opened.mode`；若含 alpha 则走 `RGBA → resize → alpha_mask`，仅在无 alpha 时 `convert("RGB")`。

### B. 【中】board 模式舍入与 UI 联动公式不一致

**位置**：`core_server.py:237`（`round`） vs `core/models.py:90-93`（`_round_half_up`）

- 文档与 Swift 对齐约定是半上舍入（`floor(x+0.5)`），Python 内建 `round` 是银行家舍入。
- 实测分歧：board=14、源图 4:3 → `round` 得 10，半上舍入得 11。
- 与 ARCHITECTURE.md「联动公式禁用 round()」的约定相悖。
- **修复建议**：`core_server.py` board 计算改用 `core.models._round_half_up`。

### C. 【中】批量历史记录写入「请求尺寸」而非「最终网格」

**位置**：`core/services/batch_service.py:70-75`

```python
self.history_mgr.add_record(..., params.grid_w, params.grid_h, ...)
# 应改为 result.grid_w, result.grid_h
```

- fit_box / 原始比例下模糊请求会被引擎重算网格（实测 30×30 请求 → 30×15）。
- 历史回放/续做时会按错误尺寸重建参数。
- 同文件 `_build_output`（L37）文件名也用未 clamp 的请求值（实测文件名 600x600，引擎实际 500x500→再按比例 500x250）。

### D. 【中】协议层参数校验缺口

| 点 | 位置 | 问题 |
|---|---|---|
| `grid_color` | `core_server.py:253` | `tuple("#C8C8C8")` 变成字符元组；应 `hex_to_rgb_safe` 或接受 list[int] |
| `settings_set` | `core_server.py:162` | 任意类型可 `update` 落盘（`cell_px=['a']`）；应按 DEFAULTS 做类型清洗 |
| `settings_set` 非 dict | 同上 | `handle` 抛 ValueError（worker 兜底不崩，但应显式校验） |
| `queue_save` | `core_server.py:170` | 裸 dict 直写磁盘，依赖加载侧兜底 |

### E. 【低】历史迁移类型不完整

**位置**：`core/history_manager.py:89-92`

- `width`/`height` 为 float 时原样保留（50.7），未转 int。
- 建议统一 `_as_int` 后写入。

### F. 【低】持久化非原子写

- `settings.py` / `history_manager.py` / `my_colors.py` 均为直接 `open(w)` + `dump`。
- 进程被杀可能留下半截 JSON；建议 temp + `os.replace`。

### G. 【低】杂项

- `core_server.py` `_cancelled` 集合：对不存在的 rid 发 cancel 会永久残留（可加 TTL 或上限）。
- `models.py` `as_bool`/`parse_int` 对 float 字符串（"50.7"）会回退 default，与历史 float 问题叠加。
- `colors.py` `ColorPalette` 对未知名静默回落 `_FALLBACK`，可能掩盖调色板加载失败。

## 3.4 测试资产问题

### D. 【中】`run_tests.py` 裁剪 canary 用例 flaky

**位置**：`tests/run_tests.py:1304-1330`

- canary mtime 固定为 `now-7200`，断言「generate 后 canary 必被删」。
- 但 `prune_output` 按 mtime 保留最新 50 个；当 `output/` 已有比 2 小时更旧的文件时，先删那些，canary 存活 → 用例红。
- 复测证实：output 状态干净时绿；存在更旧文件时红。产品裁剪逻辑本身正确（单元用例 keep=50 / 删最旧 / 留最新 均绿）。
- **修复建议**：canary mtime 设为目录内最小 mtime − 1 小时，或先清空 sandbox 化隔离。

## 3.5 审计覆盖范围

| 模块 | 覆盖 | 备注 |
|---|---|---|
| `core/models.py` | 逐行 | 比例联动/钳制/序列化 |
| `core/settings.py` | 逐行 | 类型清洗不足 |
| `core/processor.py` | 逐行 | 高优先级缺陷在 L111 |
| `core/colors.py` | 逐行 | Lab 匹配/校验/缓存 |
| `core/effects/*` | 逐行 | registry 钳制 OK；bg_remove 正常 |
| `core/services/*` | 逐行 | 历史尺寸/文件名问题 |
| `core_server.py` | 逐行 | 协议校验缺口 |
| `core/history_manager.py` | 逐行 | float/原子写 |
| `core/my_colors.py` | 逐行 | 校验 OK，写非原子 |
| `core/templates.py` | 逐行 | 路径穿越防护 OK |
| `ui/state.py` | 逐行 | 撤销/资源关闭 OK |
| `ui/app_controller.py` | 关键路径 | 批量/撤销/入队 |
| Swift `app/` | 门禁 78 项 | 未逐行（依赖协议契约） |

## 3.6 结论与优先级

**门禁主体**：395/396，功能面稳定，WYSIWYG/内存/协议压力/GUI 冒烟均绿。

**交付前建议修复（按优先级）**：

1. **P0** 透明 PNG alpha 丢失（A）— 明确功能缺陷，有复现步骤
2. **P1** board 半上舍入对齐（B）；历史/文件名写最终网格（C）
3. **P1** 协议 `grid_color`/`settings_set` 类型校验（D）
4. **P2** 历史 float 钳制（E）；原子写（F）；canary 测试隔离（3.4-D）

**不阻塞项**：settings_set 非 dict 有 worker 兜底；路径穿越/取消风暴/内存基线已有防护与测试。

---

# 4. 缺陷修复验证（2026-09-30，紧接第 3 章审计）

## 4.1 修复清单

| 级别 | 缺陷 | 修复位置 | 做法 |
|---|---|---|---|
| P0 | 透明 PNG alpha 丢失 | `core/processor.py:110-117` | 打开时识别 RGBA/LA/PA/transparency，保留 alpha；仅无 alpha 才转 RGB |
| P1 | board 银行家舍入 | `core_server.py` | 改用 `core.models._round_half_up` |
| P1 | 历史/文件名写请求尺寸 | `core/services/batch_service.py` | 生成后再按 `result.grid_w/h` 命名与写历史 |
| P1 | `grid_color` 字符串被 `tuple()` | `core_server.py` `_coerce_grid_color` | 兼容 hex / [r,g,b]，非法回退默认灰 |
| P1 | `settings_set` 非法类型落盘 | `core_server.py` `_sanitize_settings` | 按 DEFAULTS 类型清洗，拒绝 list/dict |
| P2 | 历史宽高 float 不转 int | `core/history_manager.py` | 非 int / bool 一律 `_as_int` |
| P2 | 持久化非原子写 | `core/models.py` `atomic_write_json` | tmp + `os.replace`，settings/queue/history/my_colors 共用 |
| 测试 | canary 用例 flaky | `tests/run_tests.py` | canary mtime = 目录最旧文件 − 1h |

## 4.2 回归用例

`tests/run_tests.py` 新增 **测试11: 审计缺陷回归**（16 项），覆盖：
透明空格 / 对照全不透明 / board 半上舍入 / 历史最终网格 30×15 / 文件名 30x15 /
float→int / grid_color 五种输入 / settings 类型清洗。

## 4.3 修复后门禁终态（顺序执行）

| 套件 | 通过 | 失败 |
|---|---|---|
| `tests/run_tests.py`（214 基线 + 16 回归） | **230** | 0 |
| `tests/gui_smoke.py` | **92** | 0 |
| `tests/stress_protocol.py` | **12** | 0 |
| `swift test` | **78** | 0 |
| **合计** | **412** | **0** |

原 flaky 项 `generate 自动触发裁剪（canary 已清理）` 已稳定通过。
Golden 矩阵哈希全部一致（透明修复不影响无 alpha 基准图）。

---

# 5. 独立 QA 与 2.4.0 特效/UI 重做（2026-10-21）

执行方式：4 个并行子智能体独立取证（特效视觉复现 / UI 审计 / 门禁验证 / 开源参考）+ Lead 终审。
详细证据：[qa/](qa/)（报告、mockup、截图、可复跑脚本）。

## 5.1 门禁复测（严格顺序执行，不可并发）

| 套件 | 基线（第 4 章） | 2.4.0 终态 | 说明 |
|---|---|---|---|
| `tests/run_tests.py` | 230 | **249** | +19 = 18 视觉结构回归 + 1 协议 warnings；无既有用例删除/弱化 |
| `tests/gui_smoke.py` | 92 | **92** | 测试数据改为 tempdir 隔离，断言不变 |
| `tests/stress_protocol.py` | 12 | **12** | 同上 |
| `swift test` | 78 | **84** | +6 自动预览（AutoPreviewTests） |
| **合计** | **412** | **437** | 0 失败 / 0 flaky |

附加验证：`cd app && swift build` 通过；4 套件 + swift build 的用户数据副作用 sha256 快照 = **0**
（修复前 run_tests 会删除整个仓库 `track/`、gui_smoke 会删根 `app_settings.json` / `queue_state.json`）。

## 5.2 「特效代码可行但效果不可行」——根因与修复

T1 实测：协议 15/15 特效与直接引擎逐像素一致、全部 ok；但真实使用中仅 6 项 A 级，6 项 D 级。
门禁全绿的原因：特效用例只断言不崩溃/尺寸/装配，无视觉断言（7 项把实现换成 no-op 仍全绿）。

| 缺陷 | 修复前 | 修复后 |
|---|---|---|
| 改特效开关后预览不重算（P0） | 15 个 Toggle 无 onChange，仅手动「生成」 | 参数变更 500ms 防抖自动重渲染；脏标记/「正在刷新预览」/手动优先 |
| 邻接描边全图黑网 | 照片描边珠 65.9%（风景 71.9%） | 27.3%（风景 13.3%）；照片不再黑网、平涂仍保留轮廓 |
| 线稿描边是孤立噪点 | 变更格连续性 13.4% | 85.5%（卡通 87.9%），网格尺度 DoG + 滞后阈值 + 去孤点 |
| 赛璐璐压暗/串色 | 卡通 L 85.4→62.9、色相漂移 158° | L 85.4→85.1、色相漂移 11.6°（边缘保留 + Lab k-means 平涂） |
| 风格色板洗白 | 照片 L +40.3、近白珠 28.4% | L +6.0、近白 0%、用色 5（保结构量化后映射预设色） |
| 透明 PNG 特效丢 alpha | grayscale/cel/duotone 耗材 918→3600 | 918 全保持 |
| 背景去除误删白色主体 | 主体删除率 100% | 0%（边界连通域 + auto 取色 + warning） |
| chibi 无脸静默失效 | 无任何反馈 | 返回 warning，状态栏可见（大头默认跳过） |
| crop 默认空操作 / dither 绕过钳制 | 开关无变化 / strength=5 生效 | 默认内缩 0.1 / 钳制 1.5 + warning |
| 组合顺序冲突、15 项全开=单色 | 描边被后续 preset 打掉 | 仍存在顺序敏感（记录为已知限制）；UI 画廊改为分组选择而非盲目全开 |

协议扩展（向后兼容）：`generate` / `edit` 响应新增 `warnings:[String]`；Swift `GenerateResult` 缺失时默认 `[]`。
golden 矩阵按项目规范重生成（8 配置仅 outline_cell 哈希变化）。
未完成：neon 仍为 Color+Brightness 近似；chibi 真实人脸路径仅 monkeypatch 验证。

## 5.3 UI：从「默认控件墙」到「克制的高级杂志感」

UI 审计结论：现状不是单纯「不好看」，而是信息架构坏了——默认 1100×728 窗口下侧栏要滚动才能
看到「生成」，15 个特效 Toggle 是墙，图纸 hero 被塞进灰框且无色号/尺寸/颗数图注。

落地内容（SwiftUI 主推版，`app/Sources/PerlerApp/`）：
- 编辑杂志风主界面：报头/期号、编号章节 spec sheet、hero 图版 + 图注（FIG.01）、耗材 inspector、
  编辑式特效画廊 sheet、色卡色样册、亮暗双主题；三栏固定、参数 4pt 密度、生成键常驻。
- 保留全部原功能：网格实时联动（NSTextFieldBridge）、预览缩放/平移、成品切换、编辑/进度/撤销、
  PNG/PDF 导出、拖放、快捷键；主操作与快捷键可键盘到达。
- Tk 版本轮未重做（仍为旧 UI），Swift 版为设计主推。

设计观点（详见 [qa/ui/audit.md](qa/ui/audit.md)）：**做 6/10「克制的高级杂志感」**，editorial 只放在
报头/图注/空状态/特效画廊/色卡/导出封面等展示面，工作台保持工具效率；不做全套编辑部
（大留白/衬线小字参数/非对称工作页会伤效率，双端双外观维护成本高）。

## 5.4 测试有效性盲区（新发现）

1. 特效 7 项的断言可被 no-op 实现通过（详情与探针：`qa/gates/report.md`）。
2. 无任何断言检查「切特效是否自动重绘」、UI 外观/布局/可读性；XCUITest 不在 412/437 门禁内，
   且 TEST_REPORT 历史记录中的 U5–U7「见下方补记」在全文不存在。
3. 测试会删除用户数据：run_tests `shutil.rmtree(仓库/track)`、gui_smoke 删根 settings/queue
   —— 已在 2.4.0 修复为 tempdir 隔离 + `PERLER_*` 路径 env 覆盖（CI 建议注入）。
4. `stress_protocol` S5 在 `ps` 不可用的沙箱里内存断言恒真（环境限制，已记录）。

## 5.5 风险与后续

- 跨平台：新 UI 使用 macOS 系统字体（Songti/PingFang/Didot/New York）；打包 Windows/跨平台需引入
  OFL 字体（Noto Serif SC 等）并附许可。
- 特效画廊暂无逐项缩略图（Phase 2，需新增 effectPreviews 协议）。
- 视觉验收目前依赖人工看截图；建议补 UI 截图/感知 diff 回归与特效视觉快照（golden 已覆盖 4/15）。
- 开源参考与 license 清单：`qa/research/report.md`。

---

# 6. 2.5.0 用户二轮反馈修复（缩放/平移 + 老钱风棕色调 + 开始页 hero）

用户反馈：喜欢 2.4.0 效果，但要更「老钱」、更多细节、棕色系；开始页更华丽且与工作台统一；
原有朱红强调色与绿色状态色不和谐；另有两个操作硬伤：放大比例调节失效、放大后不能移动。

## 6.1 缩放/平移硬伤（P0）

**根因**（独立复现）：
1. 缩放滑杆只在 `!fitToWindow` 时渲染，默认适应窗口下界面上没有任何比例调节；
2. 「滚轮缩放」文案与实际不符：Swift 版从未实现 scrollWheel / magnify 事件；
3. **P0**：plate 上双层 `.gesture` 叠加，非编辑模式外层 `including: .none` 吞掉内层 dragGesture（事件到达 app 但产品手势 0 次 onChanged）；另有 offset 无钳制、fit 与手动缩放状态不联动。

**修复**：常驻缩放控件（−/滑块/＋/百分比/适应窗口/重置，任何交互自动切出手动缩放）；
真实滚轮（锚定光标）与触控板双指 pinch 缩放、双指滚动/拖拽平移；`⌘+`/`⌘−`/`⌘0`；
新增 `PreviewViewport` 纯函数（尺寸/锚点缩放/15% 可见钳制/小图居中）；fit 百分比显示真实比例；
plate 改为单一条件手势（编辑模式 tap / 否则 drag），修复双 `.gesture` 吞事件；滚轮锚点用
`isFlipped=true` + 16pt padding 换算修正 NSView 左下原点造成的 y 轴镜像。

**验证过程值得记录**：首版修复只验证了数学与闭包链，未验证事件到达；独立验证方用真实 ContentView +
合成 NSEvent 复现「拖拽 8 次 offset 仍为 0」，定位到双 `.gesture` 根因并要求补修，补修后实测拖拽
(60,40) 生效、极端拖拽钳制在 (726,560)（与独立推导零误差）。这也是后续 UI 改动必须补「事件到达级」
验证的原因。新增 Swift 单测 10 项（ZoomPanTests）+ 独立验证用例 15 项。

## 6.2 老钱风棕色 UI + 开始页 hero

- tokens 全量替换：暖羊皮纸 `#F4EDE1` + 深咖墨 `#2A2118` + 干邑强调色 `#8A5A33` + 黄铜渐变；
  success=青铜/橄榄褐、warning=琥珀、danger=牛血红；暗色为暖黑卡纸 `#17120D` + 黄铜 `#C99B63`。
  旧朱红 `#B03D25` / 绿 `#3E6B4F` 已从 UI 体系中移除（正文对比度实测 ≥4.5:1）。
- 开始页：新增「照片 → 拼豆」hero 首图（左清晰照片向右逐级像素化/拼豆格线过渡，2400×1333），
  外铜内浅双框 + 四角 crop marks + PLATE 00 图注 + PHOTOGRAPH/BEADS 双列微说明；
  黄铜渐变宋体大标题、右侧示例图版改为编号图录式，主操作「选择图片」保持首位。
- 装帧细节：报头双发丝线、菱形 fleuron、黄铜箭头；工作台/画廊/色卡/状态条统一暖棕 tokens。
- hero 素材说明：由本地示例照片 + 引擎生成（未引入第三方素材）；公开发布前建议替换为明确授权的照片。

## 6.3 回归与门禁（最终以 qa/gates/final_report 为准）

| 套件 | 2.4.0 | 2.5.0 |
|---|---|---|
| `tests/run_tests.py` | 249 | **249** |
| `tests/gui_smoke.py` | 92 | **92** |
| `tests/stress_protocol.py` | 12 | **12** |
| `swift test` | 84 | **111** |
| **合计** | **437** | **464** |

独立验证：[qa/verify/zoom_pan_and_theme_report.md](qa/verify/zoom_pan_and_theme_report.md)（缩放/平移功能与数学、事件到达级复现、主题取色/对比度、hero 显示、真实交互自动化限制）。
swift test 增量为：AutoPreviewTests 6（2.4.0）+ ZoomPanTests 10 + AssetTests 1 + VerifyZoomPanTests 15（独立验证用例）。

---

# 7. 2.5.1 封面改版（2026-10-21 用户四轮反馈）

用户反馈：①示例面板不要了，颜色特别不和谐；②老鹰图做成一张背景大图在整个左侧。

## 7.1 改动

- **移除示例面板**：封面右侧 coverRail 整块（示例图版 + 彩色模板缩略图）删除，`TemplateThumb` 一并清理；
  模板入口仅保留在工作台侧栏「模板」下拉。封面页不再出现任何彩色缩略图。
- **左侧整幅背景大图**：新增封面资产 `app/Sources/PerlerApp/Resources/hero_photo_to_beads_cover.jpg`
  （2400×1800，4:3，左上清晰照片 → 右下拼豆对角过渡 + 渐进像素化 + 拼豆格线，约 606KB）；
  以 `scaledToFill + clipped` 铺满内容区整个左侧（无边距/无框），底部渐隐 scrim + 奶油图注
  （PLATE 00 / FROM PHOTOGRAPH TO BEAD / PHOTOGRAPH·BEADS）；鹰眼主体不被遮挡。
- **右侧 430pt 操作列**：eyebrow、黄铜渐变宋体标题、standfirst、主 CTA + 拖入提示、快捷键 4 行、输出 3 行、本机处理说明；
  1280×800 不滚动、CTA 首屏可见；亮暗双主题。
- **P2 修复**：hero 用 `GeometryReader` 显式尺寸 + 铺底 Rectangle，切断图片理想宽传播；右列回到 430pt、
  右内边距恢复 30pt（修复前被裁到 0–18.5pt）。
- 旧横向 hero 资产（2400×1333）与 API 已删除，避免死重。

## 7.2 独立验证（T13，全部 PASS）

| 检查项 | 结果 |
|---|---|
| 示例面板/彩色缩略图移除 | PASS：四场景 hero 外饱和彩色像素 = 0（旧封面右栏 486px），OCR 无示例关键词 |
| 左侧 hero 铺满 | PASS：1280×800 实测 879×682.5pt（占窗口宽 68.7% × 内容区高 100%），左/上/下贴边；hero 内纸底残留 0.07% |
| scaledToFill 无变形 | PASS：结构性等比裁切；素材比例 4:3 由 AssetTests 断言 |
| 图注/scrim 可读性 | PASS：图注带对比度 7.16:1（1280）/6.93:1（1440），scrim 区背景亮度为中部 6.7% |
| 主 CTA 首屏 | PASS：OCR「选择图片⋯」完整在 1280×800 内 |
| 快捷键/输出表 | PASS：7 行完整无截断 |
| 工作台/画廊回归 | PASS：与 T10 截图逐像素 diff 0.008% / 0% |
| P2 右内边距 | 已修复：1280 分隔线 849pt/右列 431/内边距 30pt，1440 分隔线 1009pt |

报告：[qa/verify/cover_redesign_report.md](qa/verify/cover_redesign_report.md)；截图：[qa/ui/after/](qa/ui/after/README.md)。

## 7.3 门禁

封面改版后 `swift test 111`（旧横向 hero 测试删除后），最终门禁 249 + 92 + 12 + 111 = **464/0**（详见 qa/gates/final_report.md）。


---

# 8. 2.6.0 生成图/PDF 风格统一（2026-10-22 用户五轮反馈）

用户反馈：『生成的图片的风格也要统一，所有界面统一』。本轮把引擎输出的图纸 PNG、成品预览、PDF（含 BOM 页）
从旧「白底 + 蓝色标题/浅蓝标号区」统一到与 2.5.x App 界面同一套老钱风 editorial tokens；Tk 界面按用户明确指示暂不处理。

## 8.1 改动（core/models.py + core/processor.py + core/effects/filters.py）

- tokens 单一来源：paper #F4EDE1 / paperDeep #EBE1D2 / paperMat #FBF6EC / ink #2A2118 / inkSoft #4D3F30 /
  inkMuted / hairline #D5C4AC / hairlineStrong #B7A488 / accent #8A5A33；暗色 #17120D / #1E1811 / #F0E7D8 / #C99B63。
- 图纸：paper 底、默认网格线改暖 hairline、行列标号 paperDeep+ink（每 5 个 accent）、图例 4–5 列编辑式
  （MATERIALS · 耗材清单 + 双发丝线 + 方形色块 + 右对齐数量）、页脚 PLATE 01 + Didot/Georgia 大数字 + 元数据行；
  旧蓝色 (0,120,215) 全量移除；列宽/字号/对比度为可读性做过 WP 断言。
- 成品预览：paper 背景（透明格露出纸底）；色号文字按 WCAG 在 ink/paperMat 中取对比度更高者。
- dark_chart：espresso 底 + 奶油墨 + 黄铜 accent。
- PDF：A4 图表页 paper + 细框 + 右下页码（不重复图表内 PLATE 页脚）；BOM 页编辑式材料表（MATERIALS 标题、
  SWATCH/CODE/NAME/QTY/SHARE、右对齐数量/占比、合计）；1:1 页纸底 + 裁切角线；页面尺寸/页数/裁切语义不变。
- CJK 混排：PIL 无字体回退，新增 `_text_runs/_draw_mixed_text`（中文用 body：PingFang/msyh；数字/ASCII 用 mono），
  修复「颗」「约」在 Menlo 下渲染为 tofu 的问题；run_tests 新增 2 条「含 CJK 串不得用 mono」守卫。
- 默认网格线常量 #C8C8C8 → #D5C4AC（新默认；显式旧值/旧设置仍兼容）。

## 8.2 独立验证（T17，全部 PASS）

| 项 | 结果 |
|---|---|
| 图纸 PNG（29/60/100 + cell16 + dark） | PASS：三角=paper δ=0、左上角块=espresso δ=0；旧蓝像素 0（改前 2110/3336–6407）；图例 OCR 重叠 0；信息 8/8；色号对比度中位 10.7–13.25 |
| dark_chart / finished | PASS：暗色 tokens 精确命中；透明格露 paper δ=0 |
| PDF（A4/BOM/1:1/bw） | PASS：页数 5/5/8 与改前一致、A4 尺寸、paper 底、旧蓝 0、页脚无重复 |
| tokens 对齐 | PASS：core 17 个 token 对 Swift DesignSystem 亮/暗 delta 全 0（17/17） |
| 回归 | PASS：run_tests 279/0、gui_smoke 92/0、stress 12/0、swift test 111/0（合计 494）；golden 未变（仅哈希 finished 纯珠区，语义正确） |
| 可读性/尺寸 | PASS（P3 观察）：中间调珠个别色号对比度 2.3–4.5，中位 10.7–13.25 |

报告：[qa/effects/style/README.md](qa/effects/style/README.md) / [qa/verify/style_unification_report.md](qa/verify/style_unification_report.md)；
代表性截图：`qa/effects/style/chart_29x29_cell60.png`、`chart_60x60_cell20.png`、`chart_dark_chart_29x29.png`、
`pdf_a4_page_render.jpg`、`pdf_bom_page1_render.jpg`。

## 8.3 门禁

最终 279 + 92 + 12 + 111 = **494/0**（详见 qa/gates/final_report.md）。golden 未重生成的理由见 8.1/8.2。

