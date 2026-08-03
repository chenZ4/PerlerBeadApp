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
