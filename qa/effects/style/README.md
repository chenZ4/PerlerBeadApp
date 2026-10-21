# T15 Editorial 输出风格证据（引擎图纸 / 成品 / PDF）

与 App 2.5.x「老钱风」UI 同源：暖羊皮纸 + 深咖墨 + 干邑黄铜 + 宋体/Didot 展示字 + 发丝线 + PLATE 装帧。
tokens 定义在 `core/models.py`（与 `qa/ui/theme/README.md`、`app/Sources/PerlerApp/DesignSystem.swift` 同源），渲染在 `core/processor.py`。

## 1. 设计 tokens（亮色 / 暗色）

| Token | Hex | 引擎用途 |
|---|---|---|
| paper | #F4EDE1 | 图纸画布底 / finished 背景 / PDF 页面 |
| paperDeep | #EBE1D2 | 行列标号区衬纸 |
| paperMat | #FBF6EC | 深色珠色号文字 / 奶油装饰 |
| ink | #2A2118 | 主文字 / 浅色珠色号 |
| inkSoft | #4D3F30 | 图例名称 |
| inkMuted | #72614A | 数量/元数据/页码 |
| hairline | #D5C4AC | 默认网格线 / 发丝线 |
| hairlineStrong | #B7A488 | 双线/外框/色块边 |
| accent | #8A5A33 | 「每 5」行列号 / PLATE 标题 / fleuron |
| dark bg / panel | #17120D / #1E1811 | dark_chart espresso 底 |
| dark ink / accent | #F0E7D8 / #C99B63 | dark_chart 奶油字 / 黄铜线 |

## 2. 版式要点（对应任务验收）

1. **图纸/成品**：画布与 finished 背景 = paper；默认网格线 = hairline；透明格露出纸底。
2. **行列标号**：paperDeep 底 + hairline 边 + ink 数字，每 5 个 accent 粗体；左上角 espresso 块 + 奶油双框/菱形装饰。
3. **图例**：5 列编辑式（自适应 4~5 列），「MATERIALS · 耗材清单」serif 标题 + 双发丝线 + 菱形 fleuron；方形色块 hairline 边；色号 mono ink、名称 PingFang inkSoft、数量右对齐 muted、行发丝线；高度按行数自适应。
4. **页脚**：双线 + 「PLATE 01 · 拼豆图纸」serif（accent+ink）+ Didot/Georgia 大数字（千分位）+ 小号「颗」+ 元数据行 `GRID 60×60 · BEADS 3,600 · COLORS 52 · MARD 221 · 约 30×30 cm · 5mm/颗`；旧蓝色 (0,120,215) 全量移除（见 checks.json）。5. **成品预览**：paper 背景；图纸内色号文字按 WCAG 对比度在 ink/paperMat 中取高者（全 MARD 色珠最坏 ≥3:1，run_tests 有断言）。
6. **dark_chart**：espresso 底 + 奶油墨 + 黄铜 accent/hairline（bg `[23,18,13]`，dark_ink/dark_accent 像素见 checks.json）。
7. **PDF**：A4 图表页 = paper + 双框/裁切角线 + 右下角小页码（**不重复图表内 PLATE 页脚**）；BOM 页 = MATERIALS serif 标题 + 双线 + SWATCH/CODE/NAME/QTY/SHARE 表头 + 方形色块 + 右对齐数量/占比 + 合计；bw 黑白模式保持纸底可读。页面尺寸 / 页数 / 1:1 裁切语义不变（run_tests PDF 断言）。
8. **字体回退**：mac Songti（衬线）/Didot（数字）/PingFang（正文）/Menlo（等宽）；Windows simsun/georgia/msyh/consola；Linux Noto/DejaVu。无新依赖。

## 3. 证据文件

| 文件 | 说明 |
|---|---|
| `chart_29x29_cell60.png` | 29×29 小图（cell 60）完整图纸 |
| `chart_60x60_cell20.png` | 60×60 照片图纸 |
| `chart_100x100_cell16.png` | 100×100 高精度图纸 |
| `chart_cell16_small.png` | cell 16 小字号图纸（色号对比度回归样本） |
| `chart_dark_chart_29x29.png` | dark_chart espresso/cream/brass |
| `finished_60x60_cell20.png` | finished 成品预览（照片全覆盖） |
| `finished_transparent_paper_bg.png` | finished 透明格露出 **paper** 背景（验证 #F4EDE1） |
| `pdf_a4_chart.pdf` / `pdf_a4_page_render.jpg` | A4 图表页（纸底+细框+页码，无重复页脚） |
| `pdf_bom.pdf` / `pdf_bom_page1_render.jpg` / `pdf_bom_last_page_render.jpg` | BOM 编辑式材料页（多页/末页合计） |
| `pdf_1x1.pdf` / `pdf_1x1_page1.jpg` | 1:1 实物多页（纸底+裁切角线） |
| `checks.json` | 自动校验数据（背景/旧蓝=0/5 列/暗色 token 像素数等） |

说明：finished 在不透明满覆盖素材上整幅都是珠色（不存在「背景」），纸底只在**透明格/边界**外露；`finished_transparent_paper_bg.png` 即纸底证据（右上/镂空处 = [244,237,225]）。

## 4. 可复跑命令

`bash`
cd /Users/chen/Desktop/learn/PerlerBeadApp
# 生成全部证据（PNG/PDF/页面渲染/checks.json；约 20s）
PYTHONPATH=. /opt/homebrew/Caskroom/miniconda/base/envs/pindou/bin/python \
    qa/effects/style/make_style_evidence.py
# 视觉回归（277 项，含 T15 editorial 断言）
PYTHONPATH=. /opt/homebrew/Caskroom/miniconda/base/envs/pindou/bin/python tests/run_tests.py
# golden 重生成（规范流程）
PYTHONPATH=. /opt/homebrew/Caskroom/miniconda/base/envs/pindou/bin/python \
    tests/golden/update_golden.py --matrix
`

依赖：系统自带 `pdftoppm`（poppler）用于 PDF→PNG 渲染；引擎本身无新依赖。
