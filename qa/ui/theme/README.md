# T9 老钱风（Old Money）主题 tokens 与验收

> 目标：把 T6 的「朱红 + 绿」编辑部风，整体换成**暖羊皮纸 + 深咖墨 + 黄铜/干邑**的老钱静奢体系；
> 用户明确反馈：红绿不和谐。本主题**从全局移除饱和红/绿**（CI grep 见 §4）。
> 实现：app/Sources/PerlerApp/DesignSystem.swift（Tok 双外观语义色 + 装帧组件），
> 页面：ContentView（报头/三栏/开始页/画廊）、ColorChartView（色样册）。

## 1. 亮色 tokens（对比度为实测 WCAG，正文 ≥ 4.5:1）

| Token | Hex | 用途 | 对比度（on paper #F4EDE1） |
|---|---|---|---|
| paper | #F4EDE1 | 暖羊皮纸底 | — |
| paperDeep | #EBE1D2 | 图版衬纸/分区底 | — |
| paperMat | #FBF6EC | 卡片/输入底 | — |
| ink | #2A2118 | 深咖墨（主文字） | 13.58 ✔ |
| inkSoft | #4D3F30 | 次级文字 | 8.72 ✔ |
| inkMuted | #72614A | 说明/图注 | 5.12 ✔（paperDeep 4.61 ✔） |
| accent | #8A5A33 | 干邑/黄铜（唯一强调色） | 5.03 ✔（paperDeep 4.52 ✔） |
| accentBright | #A9763F | 仅大字号/装饰 | 3.37（≥24pt 大字 ✔） |
| accentSoft | #EFE0CC | 选中底/提示底 | — |
| success | #6E6547 | 状态点（青铜/橄榄褐） | 4.99 ✔ |
| warning | #8C6314 | 警告（琥珀） | 4.62 ✔ |
| danger | #7E3B2C | 错误（牛血红） | 7.08 ✔ |
| hairline | #D5C4AC | 发丝线 | 非文字 |
| hairlineSoft | #E6D9C5 | 浅分隔 | 非文字 |
| hairlineStrong | #B7A488 | 外铜框/裁切角线 | 非文字 |
| 黄铜渐变 | #B0764A → #7E5228 | 开始页大标题（44pt 展示字） | 起 3.26 / 止 5.78（大字 ✔） |

## 2. 暗色 tokens

| Token | Hex | 对比度（on paper #17120D） |
|---|---|---|
| paper | #17120D | — |
| paperDeep | #1E1811 | — |
| paperMat | #261E15 | — |
| ink | #F0E7D8 | 15.17 ✔ |
| inkSoft | #C9B99F | 9.68 ✔ |
| inkMuted | #A08E74 | 5.86 ✔ |
| accent | #C99B63 | 7.40 ✔ |
| accentBright | #D9AE79 | 9.11 ✔ |
| accentSoft | #33261A | — |
| success | #A79B72 | 6.71 ✔ |
| warning | #C9973F | 7.07 ✔ |
| danger | #C07A63 | 5.50 ✔ |
| hairline | #3A2F23 | 非文字 |
| 黄铜渐变 | #D9AE79 → #C99B63 | 展示字 |

## 3. 装帧元素（新增 DesignSystem 组件）

| 组件 | 规格 | 用在哪 |
|---|---|---|
| DoubleRule | 外 1.5px hairlineStrong + 3px gap + 内 0.5px hairline | 报头下方、开始页图注下、画廊/色卡 header 下方 |
| Fleuron | 6px 菱形描边，旋转 45°，accent 色 | 报头 wordmark 旁、开始页 micro 行、状态说明 |
| BrassArrow | arrow.up.right，accent 色 | 开始页示例图版目录行、导出行 |
| 黄铜渐变 | LinearGradient(#B0764A→#7E5228 / 暗 #D9AE79→#C99B63) | 开始页标题「到 3,600 颗豆。」 |
| Hero 双框 | 外 1.5px hairlineStrong + 内 0.5px hairline（内缩 5pt）+ 四角 crop marks（内缩 11pt） | 开始页 PLATE 00 |
| 按钮 | Ink=深咖底米白字；Ghost=暖纸底黄铜发丝线；Accent=干邑底米白字（暗色反转） | 全局 |

## 4. 「不得出现饱和红/绿」验收

- 全局 UI 已无红/绿语义色：旧 #B03D25（朱红）/#3E6B4F（绿）已从 tokens 删除；
  `grep -n 'Color.red|\.red\b|Color.green|\.green\b|0xB03D25|0x3E6B4F' app/Sources/PerlerApp/*.swift` → 仅 ColorChartView 中真实色卡 RGB（内容数据，不是 UI chrome）。
- 状态点：success 青铜/橄榄褐；warning 琥珀；danger 牛血红；进度条/强调：干邑/黄铜。
- 模板缩略图罩暖纸底（降饱和 0.82 + paper 5% 罩），避免亮绿/正红破坏整体调性。
- 色卡色块/标签：色块是真实色卡内容；色号标签用固定明暗两色（不随主题），保证各色块上可读。

## 5. 验收截图

| 场景 | 亮色 | 暗色 |
|---|---|---|
| 开始页（真 app，含 PLATE 00 hero） | qa/ui/after/real_empty_light_1280x800.png | qa/ui/after/real_empty_dark_1280x800.png |
| 工作台（harness） | qa/ui/after/harness_current_1280_light_v2.png | qa/ui/after/harness_current_1280_dark_v2.png |
| 特效画廊 | qa/ui/after/harness_effects_gallery_light_v2.png | qa/ui/after/harness_effects_gallery_dark_v2.png |
| 色卡 | qa/ui/after/harness_colorschart_light_v2.png | qa/ui/after/harness_colorschart_dark_v2.png |

大窗开始页：qa/ui/after/real_empty_{light,dark}_1440x900.png（本机屏幕可用高限制，实际 1440×861）。
