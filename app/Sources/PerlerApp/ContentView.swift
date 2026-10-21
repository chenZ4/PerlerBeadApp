import SwiftUI
import AppKit
import UniformTypeIdentifiers

// ============================================================================
// ContentView.swift — 编辑部风主界面（T6，对照 qa/ui/mockups/ mockup_01 + mockup_03）
// 说明：不改 AppViewModel/Models；特效 Phase 1 用编辑式卡片（无 per-effect 缩略图），
//       自动预览 API 由 effects-qa 提供，落地后再在 onToggle 处 wire parametersDidChange()。
// ============================================================================

struct ContentView: View {
    @StateObject private var vm = AppViewModel()
    @State private var showColorChart = false
    @State private var showEffects = false
    @State private var showPDFModeDialog = false
    @State private var compareOriginal = false
    @State private var sourceImage: NSImage?
    @State private var coverTargeted = false

    var body: some View {
        Group {
            if isCover {
                coverLayout
            } else {
                workbenchLayout
            }
        }
        .background(Tok.paper)
        .foregroundStyle(Tok.ink)
        .background(shortcutHost)
        .sheet(isPresented: $showColorChart) {
            ColorChartView(paletteInternal: vm.paletteInternal,
                           paletteDisplay: vm.paletteDisplay,
                           engine: vm.engine)
        }
        .sheet(isPresented: $showEffects) {
            EffectsGalleryView(vm: vm, onApply: { vm.generate() })
                .frame(width: 1180, height: 780)
        }
        .confirmationDialog("PDF 导出模式", isPresented: $showPDFModeDialog) {
            Button("适应 A4 单页") { exportPDF(mode: "a4") }
            Button("1:1 实物大小多页") { exportPDF(mode: "1x1") }
            Button("取消", role: .cancel) {}
        }
        .onAppear(perform: vm.setup)
        .onChange(of: vm.imagePath) { _, path in
            sourceImage = path.flatMap { NSImage(contentsOfFile: $0) }
        }
    }

    private var isCover: Bool {
        vm.imagePath == nil && vm.lastResult == nil && !vm.isBusy
    }

    // MARK: - 封面（左整块背景 hero + 右文案/操作列；T12）

    private var coverLayout: some View {
        VStack(spacing: 0) {
            masthead
            DoubleRule()
            HStack(spacing: 0) {
                coverHero.frame(maxWidth: .infinity, maxHeight: .infinity)
                Hairline(vertical: true, color: Tok.hairlineStrong)
                coverColumn.frame(minWidth: 400, idealWidth: 430, maxWidth: 430)
            }
            Hairline()
            statusBar
        }
        .onDrop(of: [UTType.fileURL], isTargeted: $coverTargeted) { providers in
            handleDrop(providers)
        }
    }

    /// 左侧整块背景大图（无边距/无框住小图）：照片→拼豆对角过渡，底部 scrim + 左下奶油图注
    /// 注意：图片不参与 HStack 理想宽度计算（GeometryReader 显式尺寸 + 铺底 Rectangle），
    /// 否则 scaledToFill 的理想宽 ≈ 内容高×4/3 会把右列挤出窗口（view-verify T13 P2）。
    private var coverHero: some View {
        ZStack(alignment: .bottomLeading) {
            Rectangle().fill(Tok.paperDeep)
            if let hero = EditorialAssets.heroPhotoToBeadsCover {
                GeometryReader { geo in
                    Image(nsImage: hero)
                        .resizable()
                        .scaledToFill()
                        .frame(width: max(1, geo.size.width),
                               height: max(1, geo.size.height))
                        .clipped()
                }
            }
            LinearGradient(stops: [
                .init(color: .clear, location: 0.42),
                .init(color: Color(hex: 0x17120D, opacity: 0.74), location: 1.0),
            ], startPoint: .top, endPoint: .bottom)
            VStack(alignment: .leading, spacing: 7) {
                MicroLabel("PLATE 00  ·  FROM PHOTOGRAPH TO BEAD",
                           color: Color(hex: 0xF4EDE1), size: 9.5)
                HStack(alignment: .top, spacing: 26) {
                    coverCaption("PHOTOGRAPH", "清晰原片 · 保留明暗层次")
                    coverCaption("BEADS", "逐级像素化 · MARD 221 映射")
                    Spacer(minLength: 0)
                }
            }
            .padding(.leading, 30)
            .padding(.trailing, 24)
            .padding(.bottom, 26)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .clipped()
    }

    private func coverCaption(_ title: String, _ text: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            MicroLabel(title, color: Color(hex: 0xC9A063), size: 8.5, tracking: 1.8)
            Text(text)
                .font(TFont.pingfang(9))
                .foregroundStyle(Color(hex: 0xE8DCC8))
        }
    }

    /// 右侧 430pt 文案/操作列：eyebrow + 黄铜渐变标题 + standfirst + CTA + 快捷键/输出 + 本机说明
    private var coverColumn: some View {
        VStack(alignment: .leading, spacing: 0) {
            MicroLabel("BEGIN A NEW PLATE  ·  开始一张新图纸")
                .padding(.top, 26)
            Text("从一张照片，")
                .font(TFont.songtiBold(38))
                .foregroundStyle(Tok.ink)
                .padding(.top, 10)
            Text("到 3,600 颗豆。")
                .font(TFont.songtiBold(38))
                .foregroundStyle(Tok.brassGradient)
            Text("把任意图片排成一张可打印的拼豆图纸 —— 自动映射 MARD 221 色卡，生成行列标号、色号图例与耗材清单。")
                .font(TFont.pingfang(12)).foregroundStyle(Tok.inkSoft)
                .lineSpacing(5)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 10)
            Button("选择图片 …") { chooseImage() }
                .buttonStyle(InkButtonStyle(height: 40))
                .frame(width: 210)
                .padding(.top, 18)
            HStack(spacing: 6) {
                Text(coverTargeted ? "松开以开始排版" : "或拖入图片  ·  ⌘O")
                    .font(TFont.pingfang(10.5))
                    .foregroundStyle(coverTargeted ? Tok.accent : Tok.inkMuted)
                if coverTargeted { Fleuron(size: 5) }
            }
            .padding(.top, 8)
            DoubleRule().padding(.top, 18)
            MicroLabel("SHORTCUTS  ·  快捷键").padding(.top, 14)
            VStack(spacing: 0) {
                keyRow("打开图片", "⌘ O")
                keyRow("生成图纸", "⌘ G")
                keyRow("缩放 / 重置", "⌘+ / ⌘− / ⌘0")
                keyRow("对比原图", "按住按钮")
            }
            .padding(.top, 2)
            MicroLabel("OUTPUT  ·  输出").padding(.top, 14)
            VStack(spacing: 0) {
                keyRow("PNG 图纸", "3670 × 4270 px")
                keyRow("PDF", "A4 / 1:1 实物")
                keyRow("色卡", "MARD 221 · 4 套")
            }
            .padding(.top, 2)
            Spacer(minLength: 10)
            HStack(spacing: 6) {
                Fleuron(size: 5)
                Text("所有处理在本机完成 · 不上传云端")
                    .font(TFont.pingfang(9)).foregroundStyle(Tok.inkMuted)
            }
            .padding(.bottom, 18)
        }
        .padding(.horizontal, 30)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(Tok.paper)
    }

    private func keyRow(_ label: String, _ key: String) -> some View {
        VStack(spacing: 0) {
            HStack {
                Text(label).font(TFont.pingfang(10.5)).foregroundStyle(Tok.inkSoft)
                Spacer()
                Text(key).font(TFont.menlo(9.5)).foregroundStyle(Tok.inkMuted)
                    .padding(.horizontal, 6).frame(height: 17)
                    .overlay(RoundedRectangle(cornerRadius: 2)
                        .stroke(Tok.hairlineSoft, lineWidth: 1))
            }
            .frame(height: 28)
            Hairline(color: Tok.hairlineSoft)
        }
    }

    // MARK: - 工作台三栏（mockup_01）

    private var workbenchLayout: some View {
        VStack(spacing: 0) {
            masthead
            DoubleRule()
            HStack(spacing: 0) {
                sidebar.frame(width: Tok.sidebarW)
                Hairline(vertical: true)
                hero.frame(maxWidth: .infinity)
                Hairline(vertical: true)
                inspector.frame(width: Tok.inspectorW)
            }
            Hairline()
            statusBar
        }
    }

    // MARK: - 报头

    private var masthead: some View {
        HStack(alignment: .center, spacing: 0) {
            VStack(alignment: .leading, spacing: 2) {
                MicroLabel("PERLER BEAD ATELIER  ·  ISSUE 006")
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text("拼豆图纸").font(TFont.songtiBold(28)).foregroundStyle(Tok.ink)
                    MicroLabel("PLATE STUDIO", color: Tok.inkMuted, size: 8.5, tracking: 2.4)
                }
            }
            Fleuron(size: 6).padding(.horizontal, 16)
            Spacer(minLength: 8)
            HStack(spacing: 22) {
                metaBlock("本期色卡", vm.paletteDisplay)
                metaBlock("网格规格", "\(vm.gridW) × \(vm.gridH)")
                metaBlock("耗材总量", vm.lastResult.map { "\($0.totalBeads.formatted()) 颗" } ?? "—")
            }
            Spacer(minLength: 16)
            HStack(spacing: 10) {
                Button("导入图片") { chooseImage() }
                    .buttonStyle(GhostButtonStyle())
                    .disabled(vm.isBusy)
                exportMenu
            }
        }
        .padding(.horizontal, 32)
        .frame(height: Tok.mastheadH)
    }

    private func metaBlock(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            MicroLabelCN(label, size: 9.5)
            Text(value).font(TFont.menlo(11.5)).foregroundStyle(Tok.ink).lineLimit(1)
        }
    }

    private var exportMenu: some View {
        Menu {
            Button("导出 PNG…") { exportPNG() }
            Button("导出 PDF…") { showPDFModeDialog = true }
        } label: {
            HStack(spacing: 6) {
                Text("导出图纸").font(TFont.pingfangMedium(12.5)).tracking(0.8)
                Text("⌘E").font(TFont.menlo(9)).foregroundStyle(Tok.paper.opacity(0.6))
            }
            .foregroundStyle(Tok.paper)
            .padding(.horizontal, 14)
            .frame(height: 28)
            .background(Tok.ink)
            .clipShape(RoundedRectangle(cornerRadius: Tok.radiusS))
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .disabled(vm.lastResult == nil)
        .opacity(vm.lastResult == nil ? 0.35 : 1)
    }

    // MARK: - 左栏：规格表

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionHeader(index: "01", title: "图片源", trailing: "SOURCE")
                .padding(.top, 16)
            HStack(spacing: 10) {
                ImageThumb(image: sourceImage, chart: vm.chartImage, size: 44)
                VStack(alignment: .leading, spacing: 3) {
                    Text(fileName).font(TFont.menlo(10)).foregroundStyle(Tok.ink)
                        .lineLimit(1).truncationMode(.middle)
                    Text(sourceMeta).font(TFont.pingfang(9.5))
                        .foregroundStyle(Tok.inkMuted).lineLimit(1)
                }
                Spacer(minLength: 0)
            }
            .padding(.vertical, 9)
            HStack(spacing: 8) {
                Button("更换图片 …") { chooseImage() }
                    .buttonStyle(GhostButtonStyle())
                    .disabled(vm.isBusy)
                if !vm.templates.isEmpty {
                    Menu {
                        Button("自定义") { vm.selectedTemplate = nil }
                        ForEach(vm.templates, id: \.id) { t in
                            Button("\(t.name) (\(t.width)×\(t.height))") { vm.loadTemplate(t.id) }
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Text(templateName).font(TFont.pingfang(11))
                                .foregroundStyle(Tok.inkSoft).lineLimit(1)
                            Image(systemName: "chevron.down")
                                .font(.system(size: 8, weight: .semibold))
                                .foregroundStyle(Tok.inkMuted)
                        }
                        .padding(.horizontal, 9)
                        .frame(height: 26)
                        .overlay(RoundedRectangle(cornerRadius: Tok.radiusS)
                            .stroke(Tok.hairline, lineWidth: 1))
                    }
                    .menuStyle(.borderlessButton)
                    .menuIndicator(.hidden)
                    .fixedSize()
                    .disabled(vm.isBusy)
                }
            }

            SectionHeader(index: "02", title: "网格与版式", trailing: "GRID")
                .padding(.top, 18)
            GridFieldRow(label: "宽", text: $vm.gridW, labelWidth: 42,
                         onEdit: { vm.gridFieldEdited("w") },
                         onSubmit: { vm.commitDimension("w") })
            GridFieldRow(label: "高", text: $vm.gridH, labelWidth: 42,
                         onEdit: { vm.gridFieldEdited("h") },
                         onSubmit: { vm.commitDimension("h") })
            GridFieldRow(label: "每格像素", text: $vm.cellSize, labelWidth: 64)
            HStack(spacing: 0) {
                Text("比例").font(TFont.pingfang(11.5)).foregroundStyle(Tok.inkMuted)
                    .frame(width: 42, alignment: .leading)
                Menu {
                    ForEach(vm.ratioOptions, id: \.self) { option in
                        Button(option) {
                            vm.ratioMode = option
                            vm.applyRatioLink()
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Text(vm.ratioMode).font(TFont.pingfang(11)).foregroundStyle(Tok.ink)
                        Spacer(minLength: 2)
                        Image(systemName: "chevron.down")
                            .font(.system(size: 8, weight: .semibold))
                            .foregroundStyle(Tok.inkMuted)
                    }
                    .contentShape(Rectangle())
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.hidden)
                Spacer(minLength: 0)
            }
            .frame(height: Tok.specRowH)
            Hairline(color: Tok.hairlineSoft)
            HStack(spacing: 5) {
                Rectangle().fill(Tok.accent).frame(width: 3, height: 3)
                Text("成品约 \(physicalSizeText) · 5 mm / 颗")
                    .font(TFont.pingfang(9.5)).foregroundStyle(Tok.inkMuted)
            }
            .padding(.top, 7)

            SectionHeader(index: "03", title: "色卡", trailing: "PALETTE")
                .padding(.top, 16)
            HStack(spacing: 0) {
                Text("色卡").font(TFont.pingfang(11.5)).foregroundStyle(Tok.inkMuted)
                    .frame(width: 42, alignment: .leading)
                Menu {
                    ForEach(vm.palettes, id: \.display) { p in
                        Button("\(p.display) (\(p.count))") { vm.paletteDisplay = p.display }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Text(vm.paletteDisplay).font(TFont.pingfang(11))
                            .foregroundStyle(Tok.ink).lineLimit(1)
                        Spacer(minLength: 2)
                        Image(systemName: "chevron.down")
                            .font(.system(size: 8, weight: .semibold))
                            .foregroundStyle(Tok.inkMuted)
                    }
                    .contentShape(Rectangle())
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.hidden)
                Spacer(minLength: 0)
            }
            .frame(height: Tok.specRowH)
            SpecRow(label: "已用颜色",
                    value: vm.lastResult.map { "\($0.colorStats.count) / \(paletteCountText)" } ?? "—",
                    showLine: false)
            Button("查看完整色卡 →") { showColorChart = true }
                .buttonStyle(GhostButtonStyle())
                .padding(.top, 6)

            SectionHeader(index: "04", title: "特效", trailing: "EFFECTS")
                .padding(.top, 16)
            HStack(alignment: .firstTextBaseline) {
                Text("已启用").font(TFont.pingfang(11.5)).foregroundStyle(Tok.inkMuted)
                Spacer()
                Text("\(enabledEffectIDs.count) / 15").font(TFont.menlo(11.5))
                    .foregroundStyle(enabledEffectIDs.isEmpty ? Tok.inkMuted : Tok.accent)
            }
            .frame(height: 26)
            Text(enabledEffectSummary)
                .font(TFont.pingfang(9.5)).foregroundStyle(Tok.inkMuted)
                .lineLimit(1).padding(.bottom, 6)
            if vm.isAutoPreviewing {
                Text("正在自动刷新预览…")
                    .font(TFont.pingfang(9)).foregroundStyle(Tok.accent)
                    .padding(.bottom, 4)
            } else if vm.needsRegenerate && !vm.isBusy && vm.imagePath != nil {
                Text("参数已修改 · 0.5s 后自动刷新")
                    .font(TFont.pingfang(9)).foregroundStyle(Tok.warning)
                    .padding(.bottom, 4)
            }
            Button("打开特效画廊") { showEffects = true }
                .buttonStyle(GhostButtonStyle())

            Spacer(minLength: 8)
            Hairline().padding(.bottom, 10)
            generateButton
            if vm.lastResult != nil {
                HStack(spacing: 8) {
                    Button("导出 PNG") { exportPNG() }.buttonStyle(GhostButtonStyle())
                    Button("导出 PDF") { showPDFModeDialog = true }.buttonStyle(GhostButtonStyle())
                }
                .padding(.top, 8)
            } else {
                Text("生成后可导出 PNG / PDF")
                    .font(TFont.pingfang(9)).foregroundStyle(Tok.inkMuted)
                    .padding(.top, 7)
            }
        }
        .padding(.horizontal, 22)
        .padding(.bottom, 14)
        .frame(maxHeight: .infinity, alignment: .top)
    }

    private var generateButton: some View {
        Group {
            if vm.isBusy {
                Button(action: { vm.cancelActive() }) {
                    HStack {
                        Text("取消生成")
                        Spacer()
                        Text("⌘ .").font(TFont.menlo(10))
                            .foregroundStyle(Tok.paper.opacity(0.65))
                    }
                }
                .buttonStyle(InkButtonStyle(height: Tok.primaryH))
            } else {
                Button(action: { vm.generate() }) {
                    HStack {
                        Text("生成图纸").font(TFont.pingfangMedium(13)).tracking(1)
                        Spacer()
                        Text("⌘ G").font(TFont.menlo(10))
                            .foregroundStyle(Tok.paper.opacity(0.65))
                    }
                }
                .buttonStyle(InkButtonStyle(height: Tok.primaryH))
                .keyboardShortcut("g", modifiers: .command)
                .disabled(vm.imagePath == nil)
                .opacity(vm.imagePath == nil ? 0.35 : 1)
            }
        }
    }

    // MARK: - 中栏：图版 hero

    private var hero: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center, spacing: 0) {
                HStack(spacing: 8) {
                    Text("PLATE 01").font(TFont.didot(13)).foregroundStyle(Tok.accent)
                    MicroLabelCN("图版 · \(vm.effectiveShowFinished ? "成品效果" : "图纸")")
                }
                Spacer()
                EditorialSegmented(showSecond: $vm.showFinished, first: "图纸", second: "成品效果")
                Spacer()
                viewControls
            }
            .padding(.top, 14)
            .padding(.bottom, 10)

            plate.frame(maxWidth: .infinity, maxHeight: .infinity)

            Hairline().padding(.top, 12)
            heroCaption.padding(.top, 9)
            editBar.padding(.top, 8).padding(.bottom, 12)
        }
        .padding(.horizontal, 26)
    }

    /// 常驻缩放控件：− / 滑块 / ＋ / 百分比 / 适应窗口 / 重置
    private var viewControls: some View {
        ViewThatFits(in: .horizontal) {
            fullViewControls
            compactViewControls
        }
    }

    private var fullViewControls: some View {
        HStack(spacing: 6) {
            stepButton(system: "minus", action: zoomOut)
            Slider(value: zoomSliderBinding, in: 20...400, step: 5)
                .tint(Tok.ink).controlSize(.mini).frame(width: 92)
            stepButton(system: "plus", action: zoomIn)
            zoomLabel
            fitButton
            resetButton
        }
    }

    private var compactViewControls: some View {
        HStack(spacing: 6) {
            stepButton(system: "minus", action: zoomOut)
            zoomLabel
            stepButton(system: "plus", action: zoomIn)
            fitButton
        }
    }

    private func stepButton(system: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: system)
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(Tok.inkSoft)
                .frame(width: 22, height: 22)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .fixedSize()
    }

    private var zoomLabel: some View {
        Text("\(Int(effectiveZoomPercent))%")
            .font(TFont.menlo(9.5)).foregroundStyle(Tok.inkMuted)
            .frame(width: 38, alignment: .trailing)
            .fixedSize()
    }

    private var fitButton: some View {
        Button { fitPreviewToWindow() } label: {
            Text("适应窗口")
                .font(TFont.pingfang(10))
                .foregroundStyle(vm.fitToWindow ? Tok.ink : Tok.inkMuted)
                .padding(.horizontal, 7)
                .frame(height: 22)
                .overlay(RoundedRectangle(cornerRadius: Tok.radiusS)
                    .stroke(vm.fitToWindow ? Tok.hairlineStrong : Tok.hairlineSoft,
                            lineWidth: 1))
        }
        .buttonStyle(.plain)
        .fixedSize()
        .help("适应窗口（⌘0 重置视图）")
    }

    private var resetButton: some View {
        Button { resetViewport() } label: {
            Image(systemName: "arrow.counterclockwise")
                .font(.system(size: 9, weight: .semibold))
                .foregroundStyle(Tok.inkMuted)
                .frame(width: 22, height: 22)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .fixedSize()
        .help("重置视图（⌘0）")
    }

    private var plate: some View {
        Group {
            if vm.editMode {
                plateBase.gesture(editGesture)
            } else {
                plateBase.gesture(dragGesture)
            }
        }
    }

    /// 图版面本身（手势只挂一次：编辑模式=点按换色；普通模式=拖拽平移）
    private var plateBase: some View {
        ZStack {
            Rectangle().fill(Tok.paperDeep)
            Rectangle().stroke(Tok.hairline, lineWidth: 1)
            if let img = vm.effectiveShowFinished ? vm.finishedImage : vm.chartImage {
                previewImage(img).padding(16)
            } else if vm.isBusy {
                loadingPlaceholder
            } else {
                readyPlaceholder
            }
            if compareOriginal, let src = sourceImage, vm.chartImage != nil {
                compareOverlay(src)
            }
            CropMarks(color: Tok.hairlineStrong, len: 12).padding(9)

            // 真实滚轮 / 触控板事件（NSViewRepresentable 捕获 scrollWheel / magnify）
            PreviewInputCatcher(onZoom: handleWheelZoom, onPan: handleTwoFingerPan,
                                inset: 16)
        }
        .clipped()
        .contentShape(Rectangle())
        .onHover { inside in
            if inside { NSCursor.openHand.set() } else { NSCursor.arrow.set() }
        }
        .onTapGesture(count: 2) { vm.resetPreviewOffset(); clampOffsetIfNeeded() }
        .onDrop(of: [UTType.fileURL], isTargeted: nil) { providers in
            handleDrop(providers)
        }
    }

    private var loadingPlaceholder: some View {
        VStack(spacing: 10) {
            if vm.progress >= 0 {
                ProgressView(value: vm.progress).tint(Tok.accent).frame(width: 220)
            } else {
                ProgressView().tint(Tok.accent)
            }
            Text(vm.progress >= 0 ? "正在排版 \(Int(vm.progress * 100))%" : "正在处理…")
                .font(TFont.pingfang(11)).foregroundStyle(Tok.inkMuted)
        }
    }

    private var readyPlaceholder: some View {
        VStack(spacing: 12) {
            Rectangle().fill(Tok.accent).frame(width: 8, height: 8)
            Text("准备生成").font(TFont.songtiBold(22)).foregroundStyle(Tok.ink)
            Text("图片已就绪，点左下「生成图纸 ⌘G」开始排版")
                .font(TFont.pingfang(11)).foregroundStyle(Tok.inkMuted)
            Button("生成图纸") { vm.generate() }.buttonStyle(GhostButtonStyle())
        }
    }

    private func compareOverlay(_ img: NSImage) -> some View {
        GeometryReader { geo in
            let size = fitSize(img: img, in: geo.size, inset: 22)
            ZStack {
                Rectangle().fill(Tok.paperMat)
                Image(nsImage: img).resizable().interpolation(.high)
                    .frame(width: size.width, height: size.height)
                    .position(x: geo.size.width / 2, y: geo.size.height / 2)
                VStack {
                    HStack {
                        MicroLabel("ORIGINAL · 原图", color: Tok.paper, size: 9)
                            .padding(.horizontal, 8).frame(height: 20)
                            .background(Tok.ink)
                        Spacer()
                    }
                    Spacer()
                }
                .padding(12)
            }
        }
        .allowsHitTesting(false)
    }

    private var heroCaption: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 9) {
                    Text("FIG. 01").font(TFont.didot(13)).foregroundStyle(Tok.accent)
                    Text(plateTitle).font(TFont.pingfangMedium(13))
                        .foregroundStyle(Tok.ink).lineLimit(1)
                    MicroLabelCN(vm.effectiveShowFinished ? "成品效果" : "图纸")
                }
                Text(plateMeta)
                    .font(TFont.menlo(9.5)).foregroundStyle(Tok.inkMuted)
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            VStack(alignment: .trailing, spacing: 5) {
                Button {
                } label: {
                    Text("按住对比原图")
                        .font(TFont.pingfang(9.5))
                        .foregroundStyle(compareOriginal ? Tok.paper : Tok.inkSoft)
                        .padding(.horizontal, 9)
                        .frame(height: 22)
                        .background(compareOriginal ? Tok.ink : Tok.paper.opacity(0.001))
                        .overlay(RoundedRectangle(cornerRadius: Tok.radiusS)
                            .stroke(Tok.hairline, lineWidth: 1))
                }
                .buttonStyle(.plain)
                .onLongPressGesture(minimumDuration: 0.05, maximumDistance: 40,
                                     perform: {},
                                     onPressingChanged: { pressing in
                                         compareOriginal = pressing && vm.chartImage != nil
                                     })
                .disabled(vm.chartImage == nil)
                .opacity(vm.chartImage == nil ? 0.4 : 1)
                Text("滚轮 / 双指缩放 · 双击居中")
                    .font(TFont.pingfang(9)).foregroundStyle(Tok.inkMuted)
            }
        }
    }

    private var editBar: some View {
        HStack(spacing: 14) {
            Toggle("编辑模式", isOn: $vm.editMode)
                .toggleStyle(EditorialToggleStyle())
                .font(TFont.pingfang(10.5))
                .fixedSize()
            if vm.editMode {
                Toggle("进度标记", isOn: $vm.trackMode)
                    .toggleStyle(EditorialToggleStyle())
                    .font(TFont.pingfang(10.5))
                    .fixedSize()
                if vm.trackMode {
                    Text("\(vm.trackedCount) / \(vm.totalGrid)")
                        .font(TFont.menlo(10)).foregroundStyle(Tok.inkSoft)
                } else {
                    EditorialField(placeholder: "色号", text: $vm.editColorCode, width: 64)
                    Button("撤销") { vm.undoEdit() }
                        .buttonStyle(GhostButtonStyle())
                        .disabled(vm.editHistory.isEmpty)
                        .opacity(vm.editHistory.isEmpty ? 0.4 : 1)
                }
            }
            Spacer()
            Text(vm.editMode ? "点击格子换色 · 双击居中" : "拖拽平移 · 滚轮 / 双指缩放 · ⌘+ / ⌘− / ⌘0")
                .font(TFont.pingfang(9)).foregroundStyle(Tok.inkMuted)
        }
        .frame(height: 28)
    }

    // MARK: - 右栏：耗材 / 特效 / 导出

    private var inspector: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(alignment: .leading, spacing: 0) {
                SectionHeader(index: "05", title: "耗材清单", trailing: "MATERIALS")
                    .padding(.top, 16)
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(vm.lastResult.map { $0.totalBeads.formatted() } ?? "—")
                        .font(TFont.didot(44)).foregroundStyle(Tok.ink)
                    Text("颗").font(TFont.pingfang(13)).foregroundStyle(Tok.inkSoft)
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("\(vm.lastResult?.colorStats.count ?? 0) 色")
                            .font(TFont.menlo(11)).foregroundStyle(Tok.ink)
                        Text(estimateTimeText)
                            .font(TFont.pingfang(9.5)).foregroundStyle(Tok.inkMuted)
                    }
                }
                .padding(.top, 8)
                VStack(spacing: 0) {
                    ForEach(topColors) { c in colorRow(c) }
                }
                .padding(.top, 6)
                if let res = vm.lastResult, res.colorStats.count > 6 {
                    HStack(spacing: 5) {
                        Text("余下 \(res.colorStats.count - 6) 色")
                            .font(TFont.pingfang(9.5)).foregroundStyle(Tok.inkMuted)
                        Rectangle().fill(Tok.hairline).frame(height: 1)
                        Text("色号 + 名称 + 用量")
                            .font(TFont.pingfang(9)).foregroundStyle(Tok.inkMuted)
                    }
                    .padding(.top, 7)
                }

                SectionHeader(index: "06", title: "特效",
                              trailing: "APPLIED \(enabledEffectIDs.count)")
                    .padding(.top, 16)
                if enabledEffectIDs.isEmpty {
                    Text("未应用特效。打开特效画廊挑选描边、霓虹、色阶等工艺。")
                        .font(TFont.pingfang(9.5)).foregroundStyle(Tok.inkMuted)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 8)
                } else {
                    VStack(alignment: .leading, spacing: 3) {
                        ForEach(Array(enabledEffectIDs.prefix(3)), id: \.self) { id in
                            HStack(spacing: 6) {
                                Rectangle().fill(Tok.accent).frame(width: 4, height: 4)
                                Text(effectName(id)).font(TFont.pingfang(10.5))
                                    .foregroundStyle(Tok.inkSoft)
                                Spacer()
                                Text("已应用").font(TFont.pingfang(8.5))
                                    .foregroundStyle(Tok.accent)
                            }
                            .frame(height: 20)
                        }
                        if enabledEffectIDs.count > 3 {
                            Text("+ \(enabledEffectIDs.count - 3) 项")
                                .font(TFont.pingfang(9)).foregroundStyle(Tok.inkMuted)
                        }
                    }
                    .padding(.top, 8)
                }
                Button("打开特效画廊 →") { showEffects = true }
                    .buttonStyle(GhostButtonStyle())
                    .padding(.top, 8)

                SectionHeader(index: "07", title: "导出", trailing: "EXPORT")
                    .padding(.top, 16)
                exportRow("PNG",
                          meta: vm.lastResult.map {
                              "\($0.chartSize.first ?? 0) × \($0.chartSize.last ?? 0) px"
                          } ?? "生成后可用") { exportPNG() }
                exportRow("PDF", meta: "A4 单页 / 1:1 实物多页") { showPDFModeDialog = true }
                Button("导出 PDF 含耗材清单") { showPDFModeDialog = true }
                    .buttonStyle(GhostButtonStyle())
                    .padding(.top, 8)

                SectionHeader(index: "08", title: "图纸信息", trailing: "PLATE")
                    .padding(.top, 16)
                SpecRow(label: "图纸尺寸", value: chartSizeText)
                SpecRow(label: "成品尺寸", value: physicalSizeText, mono: false)
                SpecRow(label: "每格像素", value: "\(vm.cellSize) px")
                SpecRow(label: "色卡", value: vm.paletteDisplay, mono: false, showLine: false)

                Spacer(minLength: 6)
                HStack(spacing: 6) {
                    Rectangle().fill(Tok.accent).frame(width: 5, height: 5)
                    Text("本机引擎 · 不上传云端")
                        .font(TFont.pingfang(9)).foregroundStyle(Tok.inkMuted)
                }
                .padding(.top, 10)
            }
            .padding(.horizontal, 22)
            .padding(.bottom, 16)
        }
    }

    private func colorRow(_ c: TopColor) -> some View {
        VStack(spacing: 4) {
            HStack(spacing: 8) {
                Swatch(hex: c.hex, size: 13)
                Text(c.code).font(TFont.menlo(10)).foregroundStyle(Tok.ink)
                    .frame(width: 26, alignment: .leading)
                Text(c.name).font(TFont.pingfang(9.5)).foregroundStyle(Tok.inkMuted)
                    .lineLimit(1)
                Spacer(minLength: 3)
                Text(c.count.formatted()).font(TFont.menlo(9.5)).foregroundStyle(Tok.inkSoft)
                Text(c.pct).font(TFont.menlo(9)).foregroundStyle(Tok.inkMuted)
                    .frame(width: 34, alignment: .trailing)
            }
            RatioBar(fraction: c.fraction, color: Color(hexString: c.hex))
        }
        .padding(.vertical, 4)
    }

    private func exportRow(_ title: String, meta: String,
                           action: @escaping () -> Void) -> some View {
        VStack(spacing: 0) {
            Button(action: action) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(title).font(TFont.menloBold(10.5)).foregroundStyle(Tok.ink)
                    Text(meta).font(TFont.pingfang(9.5)).foregroundStyle(Tok.inkMuted)
                        .lineLimit(1)
                    Spacer(minLength: 4)
                    BrassArrow(size: 9)
                }
                .frame(height: 30)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(vm.lastResult == nil)
            .opacity(vm.lastResult == nil ? 0.45 : 1)
            Hairline(color: Tok.hairlineSoft)
        }
    }

    // MARK: - 底部状态条

    private var statusBar: some View {
        VStack(spacing: 0) {
            if vm.isBusy {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Rectangle().fill(Tok.hairlineSoft)
                        Rectangle().fill(Tok.accent)
                            .frame(width: max(2, geo.size.width * max(0, vm.progress)))
                    }
                }
                .frame(height: 2)
            }
            HStack(spacing: 9) {
                StatusDot(color: statusColor)
                Text(vm.statusText)
                    .font(TFont.pingfang(10)).foregroundStyle(Tok.inkSoft)
                    .lineLimit(1)
                if vm.isAutoPreviewing {
                    Text("正在自动刷新预览…")
                        .font(TFont.pingfang(9.5)).foregroundStyle(Tok.accent)
                } else if vm.needsRegenerate && !vm.isBusy && vm.imagePath != nil {
                    Text("参数已修改 · 即将刷新")
                        .font(TFont.pingfang(9.5)).foregroundStyle(Tok.warning)
                }
                if vm.isBusy {
                    Text(vm.progress >= 0 ? "\(Int(vm.progress * 100))%" : "…")
                        .font(TFont.menlo(9.5)).foregroundStyle(Tok.accent)
                }
                Spacer()
                Text("⌘G 生成      ⌘E 导出      ⌘O 打开图片")
                    .font(TFont.pingfang(9.5)).tracking(0.5)
                    .foregroundStyle(Tok.inkMuted)
                Spacer()
                Text(vm.fitToWindow
                     ? "适应窗口 · \(Int(effectiveZoomPercent))%"
                     : "缩放 \(Int(vm.zoom))%")
                    .font(TFont.menlo(9.5)).foregroundStyle(Tok.inkMuted)
            }
            .padding(.horizontal, 26)
            .frame(height: Tok.statusH)
        }
    }

    private var statusColor: Color {
        if vm.isBusy || vm.isAutoPreviewing { return Tok.accent }
        let t = vm.statusText
        if t.contains("失败") || t.contains("错误") || t.contains("退出") { return Tok.danger }
        if t.contains("取消") { return Tok.warning }
        return Tok.success
    }

    // MARK: - 预览交互（沿用原行为）

    private func previewImage(_ img: NSImage) -> some View {
        GeometryReader { geo in
            let size = vm.previewSize(img: img)
            Image(nsImage: img)
                .resizable()
                .interpolation(.none)
                .frame(width: size.width, height: size.height)
                .position(x: geo.size.width / 2 + vm.offset.width,
                          y: geo.size.height / 2 + vm.offset.height)
                .onAppear {
                    vm.previewGeo = geo.size
                    clampOffsetIfNeeded()
                }
                .onChange(of: geo.size) { _, newValue in
                    vm.previewGeo = newValue
                    clampOffsetIfNeeded()
                }
        }
    }

    private func fitSize(img: NSImage, in size: CGSize, inset: CGFloat) -> CGSize {
        let availW = max(10, size.width - inset * 2)
        let availH = max(10, size.height - inset * 2)
        let w = max(1, img.size.width)
        let h = max(1, img.size.height)
        let scale = min(availW / w, availH / h)
        return CGSize(width: w * scale, height: h * scale)
    }

    private var dragGesture: some Gesture {
        DragGesture()
            .onChanged { value in
                guard !vm.editMode else { return }
                enterManualZoomIfNeeded()
                vm.dragChanged(value.translation)
                clampOffsetIfNeeded()
            }
            .onEnded { _ in
                vm.dragEnded()
                clampOffsetIfNeeded()
            }
    }

    private var editGesture: some Gesture {
        SpatialTapGesture()
            .onEnded { value in vm.handlePreviewTap(location: value.location) }
    }

    // MARK: - 文件交互

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        guard !vm.isBusy else { return false }
        guard let provider = providers.first else { return false }
        _ = provider.loadObject(ofClass: URL.self) { url, _ in
            guard let url else { return }
            let ext = url.pathExtension.lowercased()
            guard ["png", "jpg", "jpeg", "webp", "gif", "bmp"].contains(ext) else { return }
            Task { @MainActor in
                self.vm.setImagePath(url.path)
            }
        }
        return true
    }

    private func chooseImage() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.png, .jpeg, .webP, .gif, .bmp]
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            vm.setImagePath(url.path)
        }
    }

    private func savePanel(defaultName: String, types: [String]) -> String? {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = defaultName
        panel.allowedContentTypes = types.compactMap { UTType(filenameExtension: $0) }
        return panel.runModal() == .OK ? panel.url?.path : nil
    }

    private func exportPNG() {
        guard let result = vm.lastResult else { return }
        guard let dest = savePanel(defaultName: "perler_\(result.gridW)x\(result.gridH).png",
                                   types: ["png"]) else { return }
        vm.exportPNG(to: dest)
    }

    private func exportPDF(mode: String) {
        guard let result = vm.lastResult else { return }
        let name = mode == "1x1"
            ? "perler_\(result.gridW)x\(result.gridH)_1x1.pdf"
            : "perler_\(result.gridW)x\(result.gridH).pdf"
        guard let dest = savePanel(defaultName: name, types: ["pdf"]) else { return }
        vm.exportPDF(to: dest, mode: mode)
    }

    // MARK: - 缩放 / 平移（T8 修复）

    private var currentPreviewImage: NSImage? {
        vm.effectiveShowFinished ? vm.finishedImage : vm.chartImage
    }

    /// 当前实际显示百分比：fit 模式按视口/图片真实比例计算，而不是写死 100%
    private var effectiveZoomPercent: Double {
        guard let img = currentPreviewImage,
              vm.previewGeo.width > 4, vm.previewGeo.height > 4 else {
            return vm.fitToWindow ? 100 : vm.zoom
        }
        return vm.fitToWindow
            ? PreviewViewport.fittedZoomPercent(imageSize: img.size, viewport: vm.previewGeo)
            : vm.zoom
    }

    private var zoomSliderBinding: Binding<Double> {
        Binding(
            get: { effectiveZoomPercent },
            set: { applyZoom($0, anchor: nil) }
        )
    }

    private var shortcutHost: some View {
        HStack(spacing: 0) {
            Button("") { zoomIn() }.keyboardShortcut("=", modifiers: .command)
            Button("") { zoomOut() }.keyboardShortcut("-", modifiers: .command)
            Button("") { resetViewport() }.keyboardShortcut("0", modifiers: .command)
        }
        .frame(width: 0, height: 0)
        .opacity(0.001)
        .accessibilityHidden(true)
    }

    private func zoomIn() { zoomStep(1) }
    private func zoomOut() { zoomStep(-1) }

    private func zoomStep(_ direction: Int) {
        let base = effectiveZoomPercent
        applyZoom(base + (direction > 0 ? 25 : -25), anchor: nil)
    }

    /// 统一缩放入口：任意缩放交互都会自动切出「适应窗口」，并以 anchor（视口内坐标）为锚点
    private func applyZoom(_ target: Double, anchor: CGPoint?) {
        guard let img = currentPreviewImage else { return }
        let viewport = vm.previewGeo
        guard viewport.width > 4, viewport.height > 4 else { return }
        let imageSize = img.size
        let oldSize = PreviewViewport.displaySize(imageSize: imageSize, viewport: viewport,
                                                  zoom: vm.zoom, fitToWindow: vm.fitToWindow)
        let newZoom = PreviewViewport.clampZoom(target)
        let newSize = PreviewViewport.displaySize(imageSize: imageSize, viewport: viewport,
                                                  zoom: newZoom, fitToWindow: false)
        let anchorPoint = anchor ?? CGPoint(x: viewport.width / 2, y: viewport.height / 2)
        var newOffset = PreviewViewport.anchoredOffset(
            currentOffset: vm.offset, oldSize: oldSize, newSize: newSize,
            anchor: anchorPoint, viewport: viewport)
        newOffset = PreviewViewport.clampOffset(newOffset, displaySize: newSize,
                                                viewport: viewport)
        vm.fitToWindow = false
        vm.zoom = newZoom
        vm.offset = newOffset
    }

    private func handleWheelZoom(factor: CGFloat, anchor: CGPoint) {
        guard currentPreviewImage != nil else { return }
        applyZoom(effectiveZoomPercent * Double(factor), anchor: anchor)
    }

    private func handleTwoFingerPan(_ delta: CGSize) {
        guard let img = currentPreviewImage else { return }
        let viewport = vm.previewGeo
        guard viewport.width > 4, viewport.height > 4 else { return }
        enterManualZoomIfNeeded()
        let size = PreviewViewport.displaySize(imageSize: img.size, viewport: viewport,
                                               zoom: vm.zoom, fitToWindow: false)
        let proposed = CGSize(width: vm.offset.width + delta.width,
                              height: vm.offset.height + delta.height)
        vm.offset = PreviewViewport.clampOffset(proposed, displaySize: size, viewport: viewport)
    }

    /// fit → 手动缩放（尺寸不变），这样之后的平移/继续缩放不会跳变
    private func enterManualZoomIfNeeded() {
        guard vm.fitToWindow else { return }
        guard let img = currentPreviewImage,
              vm.previewGeo.width > 4, vm.previewGeo.height > 4 else { return }
        vm.zoom = PreviewViewport.fittedZoomPercent(imageSize: img.size, viewport: vm.previewGeo)
        vm.fitToWindow = false
    }

    private func clampOffsetIfNeeded() {
        guard let img = currentPreviewImage else { return }
        let viewport = vm.previewGeo
        guard viewport.width > 4, viewport.height > 4 else { return }
        let size = vm.previewSize(img: img)
        let clamped = PreviewViewport.clampOffset(vm.offset, displaySize: size, viewport: viewport)
        if clamped != vm.offset { vm.offset = clamped }
    }

    private func fitPreviewToWindow() {
        vm.fitToWindow = true
        vm.zoom = 100
        vm.offset = .zero
        vm.resetPreviewOffset()
    }

    private func resetViewport() {
        fitPreviewToWindow()
    }

    // MARK: - 计算属性

    private var fileName: String {
        if let p = vm.imagePath { return (p as NSString).lastPathComponent }
        return "尚未选择图片"
    }

    private var sourceMeta: String {
        if let p = vm.imagePath, let img = NSImage(contentsOfFile: p) {
            return "\(Int(img.size.width)) × \(Int(img.size.height)) · \((p as NSString).pathExtension.uppercased())"
        }
        return "拖入图片或点上方「导入图片」"
    }

    private var templateName: String {
        if let id = vm.selectedTemplate,
           let t = vm.templates.first(where: { $0.id == id }) {
            return t.name
        }
        return "模板"
    }

    private var plateTitle: String {
        if let id = vm.selectedTemplate,
           let t = vm.templates.first(where: { $0.id == id }) {
            return t.name
        }
        if let p = vm.imagePath { return (p as NSString).lastPathComponent }
        return "未命名图纸"
    }

    private var paletteCountText: String {
        if let p = vm.palettes.first(where: { $0.display == vm.paletteDisplay }) {
            return "\(p.count)"
        }
        return "—"
    }

    private var gridWInt: Int { Int(vm.gridW) ?? 0 }
    private var gridHInt: Int { Int(vm.gridH) ?? 0 }

    private var physicalSizeText: String {
        let w = Double(gridWInt) * 0.5
        let h = Double(gridHInt) * 0.5
        func fmt(_ v: Double) -> String {
            v == v.rounded() ? String(Int(v)) : String(format: "%.1f", v)
        }
        return "\(fmt(w)) × \(fmt(h)) cm"
    }

    private var chartSizeText: String {
        guard let r = vm.lastResult, r.chartSize.count >= 2 else { return "—" }
        return "\(r.chartSize[0]) × \(r.chartSize[1]) px"
    }

    private var plateMeta: String {
        guard let r = vm.lastResult else {
            return "生成后这里会显示网格、颗数、色数与成品尺寸"
        }
        return "\(r.gridW) × \(r.gridH) 网格 · \(r.totalBeads.formatted()) 颗 · \(r.colorStats.count) 色 · \(physicalSizeText)"
    }

    private var estimateTimeText: String {
        guard let r = vm.lastResult, r.totalBeads > 0 else { return "" }
        let minutes = max(1, r.totalBeads / 20)
        if minutes % 60 == 0 { return "约 \(minutes / 60) 小时" }
        return "约 \(minutes / 60) 小时 \(minutes % 60) 分"
    }

    private var topColors: [TopColor] {
        guard let res = vm.lastResult else { return [] }
        let total = max(1, res.totalBeads)
        return res.colorStats.values
            .sorted { $0.count > $1.count }
            .prefix(6)
            .map { s in
                let hex = String(format: "#%02X%02X%02X",
                                 s.rgb.count > 0 ? s.rgb[0] : 0,
                                 s.rgb.count > 1 ? s.rgb[1] : 0,
                                 s.rgb.count > 2 ? s.rgb[2] : 0)
                return TopColor(code: s.code, name: s.name, hex: hex,
                                count: s.count,
                                fraction: Double(s.count) / Double(total))
            }
    }

    private var enabledEffectIDs: [String] {
        effectCatalog.filter { vm.uiIsEffectOn($0.id) }.map(\.id)
    }

    private var enabledEffectSummary: String {
        if enabledEffectIDs.isEmpty { return "未应用特效 · 15 项工艺可选" }
        let names = enabledEffectIDs.prefix(3).map(effectName).joined(separator: " · ")
        return names + (enabledEffectIDs.count > 3 ? " …" : "")
    }
}

// MARK: - 数据小结构

struct TopColor: Identifiable {
    var id: String { code }
    let code: String
    let name: String
    let hex: String
    let count: Int
    let fraction: Double
    var pct: String { String(format: "%.1f%%", fraction * 100) }
}

// MARK: - 空状态封面（mockup_03）

// MARK: - 特效画廊（sheet，Phase 1：编辑式卡片替代 Toggle 墙）

struct EffectsGalleryView: View {
    @ObservedObject var vm: AppViewModel
    var onApply: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var selectedID: String?

    private let columns = [GridItem(.flexible(), spacing: 10),
                           GridItem(.flexible(), spacing: 10),
                           GridItem(.flexible(), spacing: 10)]

    var body: some View {
        VStack(spacing: 0) {
            header
            DoubleRule()
            HStack(spacing: 0) {
                gallery
                Hairline(vertical: true)
                paramsPanel.frame(width: 340)
            }
            Hairline()
            footer
        }
        .background(Tok.paper)
        .foregroundStyle(Tok.ink)
        .onChange(of: paramFingerprint) { _, _ in
            vm.uiNotifyParametersChanged()
        }
    }

    private var paramFingerprint: String {
        "\(vm.maxColorsValue)/\(vm.presetName)/\(vm.adjustBrightness)/\(vm.adjustContrast)/\(vm.adjustSaturation)/\(vm.mirrorDirection)/\(vm.cropX0)/\(vm.cropY0)/\(vm.cropX1)/\(vm.cropY1)/\(vm.celShadeLevels)/\(vm.neonSaturation)/\(vm.neonDarkness)/\(vm.duotoneColor1)/\(vm.duotoneColor2)/\(vm.bgRemoveColor)/\(vm.bgRemoveTolerance)"
    }

    private var header: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 3) {
                MicroLabel("ISSUE 006  ·  EFFECTS  ·  MARD 221")
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    Text("特效画廊").font(TFont.songtiBold(30)).foregroundStyle(Tok.ink)
                    Text("先看说明与参数，点「应用并生成」重新出图")
                        .font(TFont.pingfang(11.5)).foregroundStyle(Tok.inkMuted)
                }
            }
            Spacer()
            Button("关闭  ESC") { dismiss() }
                .buttonStyle(GhostButtonStyle())
        }
        .padding(.horizontal, 28)
        .frame(height: 84)
    }

    private var gallery: some View {
        ScrollView(.vertical, showsIndicators: true) {
            VStack(alignment: .leading, spacing: 16) {
                ForEach(Array(EffectGroup.allCases.enumerated()), id: \.offset) { idx, group in
                    let items = effectCatalog.filter { $0.group == group }
                    VStack(alignment: .leading, spacing: 9) {
                        SectionHeader(index: String(format: "0%ld", idx + 1),
                                      title: group.rawValue,
                                      trailing: "\(items.count) 项")
                        LazyVGrid(columns: columns, spacing: 10) {
                            ForEach(items) { info in
                                effectCard(info)
                            }
                        }
                    }
                }
            }
            .padding(22)
        }
    }

    private func effectCard(_ info: EffectInfo) -> some View {
        let on = vm.uiIsEffectOn(info.id)
        let selected = selectedID == info.id
        return VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 7) {
                IndexBadge(text: cardIndex(info.id), filled: selected)
                Text(info.name).font(TFont.pingfangMedium(11.5))
                    .foregroundStyle(Tok.ink).lineLimit(1)
                Spacer(minLength: 2)
                Toggle("", isOn: vm.uiBinding(for: info.id))
                    .labelsHidden()
                    .toggleStyle(EditorialToggleStyle())
            }
            Text(info.desc).font(TFont.pingfang(9))
                .foregroundStyle(Tok.inkMuted)
                .lineLimit(2).fixedSize(horizontal: false, vertical: true)
            if on {
                HStack(spacing: 4) {
                    Rectangle().fill(Tok.accent).frame(width: 4, height: 4)
                    Text("已应用").font(TFont.pingfang(8.5)).foregroundStyle(Tok.accent)
                }
            }
        }
        .padding(9)
        .frame(maxWidth: .infinity, minHeight: 74, alignment: .topLeading)
        .background(Tok.paperMat)
        .overlay(Rectangle().stroke(selected ? Tok.accent : Tok.hairline,
                                    lineWidth: selected ? 1.5 : 1))
        .contentShape(Rectangle())
        .onTapGesture { selectedID = info.id }
    }

    private func cardIndex(_ id: String) -> String {
        if let idx = effectCatalog.firstIndex(where: { $0.id == id }) {
            return String(format: "%02ld", idx + 1)
        }
        return "—"
    }

    private var paramsPanel: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let id = selectedID,
               let info = effectCatalog.first(where: { $0.id == id }) {
                MicroLabel("SELECTED  ·  已选")
                    .padding(.top, 16)
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(info.name).font(TFont.songtiBold(24)).foregroundStyle(Tok.ink)
                    Spacer()
                    Toggle("", isOn: vm.uiBinding(for: info.id))
                        .labelsHidden()
                        .toggleStyle(EditorialToggleStyle())
                }
                .padding(.top, 6)
                Text(info.desc).font(TFont.pingfang(11))
                    .foregroundStyle(Tok.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 5)
                Hairline().padding(.vertical, 12)
                if vm.uiIsEffectOn(id) {
                    MicroLabel("PARAMETERS  ·  参数")
                    VStack(spacing: 12) {
                        paramsView(id)
                    }
                    .padding(.top, 10)
                } else {
                    Text("这项特效当前关闭。打开开关后可在这里调参数；完成后点右下「应用并生成」。")
                        .font(TFont.pingfang(10.5)).foregroundStyle(Tok.inkMuted)
                        .lineSpacing(4)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 10)
                }
                Hairline().padding(.vertical, 12)
                MicroLabel("PREVIEW  ·  当前图纸")
                HStack(spacing: 8) {
                    previewPlate("图纸", image: vm.chartImage)
                    previewPlate("成品", image: vm.finishedImage)
                }
                .padding(.top, 8)
                Text("提示：生成后可在主界面「按住对比原图」，对比处理前后。")
                    .font(TFont.pingfang(9)).foregroundStyle(Tok.inkMuted)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)
            } else {
                MicroLabel("SELECTED  ·  未选择")
                    .padding(.top, 16)
                VStack(alignment: .leading, spacing: 6) {
                    Rectangle().fill(Tok.accent).frame(width: 8, height: 8)
                        .padding(.top, 14)
                    Text("选一张特效卡").font(TFont.songtiBold(20))
                        .foregroundStyle(Tok.ink)
                    Text("左侧 15 项工艺按影响面分成 5 组。点卡片查看说明与参数；开关只改状态，点右下「应用并生成」后才会重新出图。")
                        .font(TFont.pingfang(10.5)).foregroundStyle(Tok.inkMuted)
                        .lineSpacing(4)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 4)
        }
        .padding(.horizontal, 22)
        .padding(.bottom, 14)
        .frame(maxHeight: .infinity, alignment: .top)
    }

    private func previewPlate(_ label: String, image: NSImage?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ZStack {
                Rectangle().fill(Tok.paperDeep)
                if let image {
                    Image(nsImage: image).resizable().interpolation(.medium)
                        .aspectRatio(contentMode: .fit).padding(4)
                }
            }
            .frame(height: 82)
            .clipped()
            .overlay(Rectangle().stroke(Tok.hairline, lineWidth: 1))
            Text(label).font(TFont.pingfang(9)).foregroundStyle(Tok.inkMuted)
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private func paramsView(_ id: String) -> some View {
        switch id {
        case "outline_cell":
            stepperRow("描边宽度", value: $vm.outlineCellWidth, range: 1...3, suffix: " px")
        case "outline_edge":
            EditorialSlider(label: "强度", value: $vm.outlineEdgeStrength,
                            range: 0...1, step: 0.05)
        case "grayscale":
            EditorialSlider(label: "对比度", value: $vm.grayscaleContrast,
                            range: 0.5...2, step: 0.05)
        case "dither":
            EditorialSlider(label: "强度", value: $vm.ditherStrength,
                            range: 0.2...1.5, step: 0.05)
        case "max_colors":
            stepperRow("最多颜色", value: $vm.maxColorsValue, range: 2...50, suffix: " 色")
        case "preset":
            pickerRow("预设", selection: $vm.presetName, options: [
                ("pastel", "马卡龙可爱"), ("preppy", "Preppy / Y2K"),
                ("halloween", "万圣节"), ("christmas", "圣诞"),
                ("cottagecore", "Cottagecore"),
            ])
        case "adjust":
            EditorialSlider(label: "亮度", value: $vm.adjustBrightness,
                            range: 0.5...1.5, step: 0.05)
            EditorialSlider(label: "对比度", value: $vm.adjustContrast,
                            range: 0.5...1.5, step: 0.05)
            EditorialSlider(label: "饱和度", value: $vm.adjustSaturation,
                            range: 0...2, step: 0.05)
        case "mirror":
            pickerRow("方向", selection: $vm.mirrorDirection,
                      options: [("horizontal", "水平"), ("vertical", "垂直")])
        case "crop":
            EditorialSlider(label: "左", value: $vm.cropX0, range: 0...0.9, step: 0.05)
            EditorialSlider(label: "上", value: $vm.cropY0, range: 0...0.9, step: 0.05)
            EditorialSlider(label: "右", value: $vm.cropX1, range: 0.1...1, step: 0.05)
            EditorialSlider(label: "下", value: $vm.cropY1, range: 0.1...1, step: 0.05)
        case "cel_shade":
            stepperRow("色阶", value: $vm.celShadeLevels, range: 2...16, suffix: " 级")
        case "neon":
            EditorialSlider(label: "饱和", value: $vm.neonSaturation,
                            range: 1...2.5, step: 0.05)
            EditorialSlider(label: "压暗", value: $vm.neonDarkness,
                            range: 0.4...1, step: 0.05)
        case "duotone":
            HexField(label: "暗部色", text: $vm.duotoneColor1)
            HexField(label: "亮部色", text: $vm.duotoneColor2)
        case "bg_remove":
            HexField(label: "背景色", text: $vm.bgRemoveColor)
            stepperRow("容差", value: $vm.bgRemoveTolerance, range: 0...120)
        case "chibi":
            Text("Q 版大头需要 OpenCV 支持；若环境缺少 OpenCV，会在生成时给出警告并跳过。")
                .font(TFont.pingfang(9.5)).foregroundStyle(Tok.inkMuted)
                .fixedSize(horizontal: false, vertical: true)
        default:
            Text("这项特效没有可调参数，开关即可生效。")
                .font(TFont.pingfang(9.5)).foregroundStyle(Tok.inkMuted)
        }
    }

    private func stepperRow(_ label: String, value: Binding<Int>,
                            range: ClosedRange<Int>, suffix: String = "") -> some View {
        HStack {
            Text(label).font(TFont.pingfang(11)).foregroundStyle(Tok.inkSoft)
            Spacer()
            Button { value.wrappedValue = max(range.lowerBound, value.wrappedValue - 1) } label: {
                Text("−").font(TFont.pingfang(13)).frame(width: 22, height: 22)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            Text("\(value.wrappedValue)\(suffix)")
                .font(TFont.menlo(11)).foregroundStyle(Tok.ink)
                .frame(minWidth: 44)
            Button { value.wrappedValue = min(range.upperBound, value.wrappedValue + 1) } label: {
                Text("+").font(TFont.pingfang(13)).frame(width: 22, height: 22)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        }
        .frame(height: 26)
        .overlay(alignment: .bottom) { Hairline(color: Tok.hairlineSoft) }
    }

    private func pickerRow(_ label: String, selection: Binding<String>,
                           options: [(String, String)]) -> some View {
        HStack {
            Text(label).font(TFont.pingfang(11)).foregroundStyle(Tok.inkSoft)
            Spacer()
            Menu {
                ForEach(options, id: \.0) { opt in
                    Button(opt.1) { selection.wrappedValue = opt.0 }
                }
            } label: {
                HStack(spacing: 4) {
                    Text(options.first(where: { $0.0 == selection.wrappedValue })?.1 ?? "—")
                        .font(TFont.pingfang(11)).foregroundStyle(Tok.ink)
                    Image(systemName: "chevron.down")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundStyle(Tok.inkMuted)
                }
                .padding(.horizontal, 8).frame(height: 24)
                .overlay(RoundedRectangle(cornerRadius: Tok.radiusS)
                    .stroke(Tok.hairline, lineWidth: 1))
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
        }
        .frame(height: 28)
        .overlay(alignment: .bottom) { Hairline(color: Tok.hairlineSoft) }
    }

    private var footer: some View {
        HStack(spacing: 10) {
            StatusDot(color: vm.isAutoPreviewing ? Tok.accent : Tok.success)
            Text("已启用 \(effectCatalog.filter { vm.uiIsEffectOn($0.id) }.count) / 15 项特效")
                .font(TFont.pingfang(10)).foregroundStyle(Tok.inkSoft)
            if vm.isAutoPreviewing {
                Text("· 正在自动刷新预览…")
                    .font(TFont.pingfang(9.5)).foregroundStyle(Tok.accent)
            } else if vm.needsRegenerate && vm.imagePath != nil {
                Text("· 预览待刷新")
                    .font(TFont.pingfang(9.5)).foregroundStyle(Tok.warning)
            }
            Spacer()
            Text("修改后点「应用并生成」重新出图；关闭不会丢失已生成图纸")
                .font(TFont.pingfang(9.5)).foregroundStyle(Tok.inkMuted)
            Spacer()
            Button("关闭") { dismiss() }
                .buttonStyle(GhostButtonStyle())
            Button("应用并生成") {
                onApply()
                dismiss()
            }
            .buttonStyle(AccentButtonStyle(height: 30))
            .keyboardShortcut(.return, modifiers: .command)
        }
        .padding(.horizontal, 28)
        .frame(height: 46)
    }
}

// MARK: - 网格输入行：NSTextField 桥接（沿用原实现，仅增加标签宽度参数）

struct GridFieldRow: View {
    let label: String
    @Binding var text: String
    var labelWidth: CGFloat = 70
    var onEdit: (() -> Void)? = nil
    var onSubmit: (() -> Void)? = nil

    var body: some View {
        HStack(spacing: 8) {
            Text(label)
                .font(TFont.pingfang(11.5))
                .foregroundStyle(Tok.inkMuted)
                .frame(width: labelWidth, alignment: .leading)
            NSTextFieldBridge(text: $text, label: label,
                              onEdit: onEdit, onSubmit: onSubmit)
                .frame(maxWidth: .infinity, minHeight: 26)
        }
        .frame(height: Tok.specRowH)
        .overlay(alignment: .bottom) { Hairline(color: Tok.hairlineSoft) }
    }
}

private struct NSTextFieldBridge: NSViewRepresentable {
    @Binding var text: String
    let label: String
    var onEdit: (() -> Void)?
    var onSubmit: (() -> Void)?

    final class Coordinator: NSObject, NSTextFieldDelegate {
        var text: Binding<String>
        var onEdit: (() -> Void)?
        var onSubmit: (() -> Void)?
        weak var view: NSTextField?

        init(text: Binding<String>, onEdit: (() -> Void)?, onSubmit: (() -> Void)?) {
            self.text = text
            self.onEdit = onEdit
            self.onSubmit = onSubmit
        }

        func controlTextDidChange(_ obj: Notification) {
            guard let tf = obj.object as? NSTextField else { return }
            text.wrappedValue = tf.stringValue
            onEdit?()
        }

        @objc func submit() {
            onSubmit?()
            guard let tf = view else { return }
            DispatchQueue.main.async {
                if tf.currentEditor() != nil,
                   tf.stringValue != self.text.wrappedValue {
                    tf.stringValue = self.text.wrappedValue
                }
            }
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(text: $text, onEdit: onEdit, onSubmit: onSubmit)
    }

    func makeNSView(context: Context) -> NSTextField {
        let tf = NSTextField(string: text)
        tf.placeholderString = label
        tf.delegate = context.coordinator
        tf.target = context.coordinator
        tf.action = #selector(Coordinator.submit)
        tf.bezelStyle = .roundedBezel
        tf.font = NSFont.systemFont(ofSize: NSFont.systemFontSize)
        tf.usesSingleLineMode = true
        tf.cell?.wraps = false
        tf.cell?.isScrollable = true
        tf.translatesAutoresizingMaskIntoConstraints = false
        context.coordinator.view = tf
        return tf
    }

    func updateNSView(_ tf: NSTextField, context: Context) {
        context.coordinator.text = $text
        context.coordinator.onEdit = onEdit
        context.coordinator.onSubmit = onSubmit
        if tf.placeholderString != label { tf.placeholderString = label }
        if tf.currentEditor() == nil, tf.stringValue != text {
            tf.stringValue = text
        }
    }
}

// MARK: - 图片缩略图

struct ImageThumb: View {
    let image: NSImage?
    let chart: NSImage?
    var size: CGFloat = 44
    var body: some View {
        ZStack {
            Rectangle().fill(Tok.paperMat)
            if let img = image ?? chart {
                Image(nsImage: img).resizable().interpolation(.medium)
                    .aspectRatio(contentMode: .fill)
            }
        }
        .frame(width: size, height: size)
        .clipped()
        .overlay(Rectangle().stroke(Tok.hairline, lineWidth: 1))
    }
}

// MARK: - 特效目录（15 项，分组用于替代 Toggle 墙）

enum EffectGroup: String, CaseIterable, Identifiable {
    case outline = "描边与线稿"
    case tone = "色调与光影"
    case style = "风格与色板"
    case texture = "质地与过渡"
    case composition = "构图与主体"
    var id: String { rawValue }
}

struct EffectInfo: Identifiable {
    let id: String
    let name: String
    let desc: String
    let group: EffectGroup
}

let effectCatalog: [EffectInfo] = [
    EffectInfo(id: "outline_cell", name: "邻接描边", desc: "描出每格边界，行列更易数", group: .outline),
    EffectInfo(id: "outline_edge", name: "线稿描边", desc: "提取轮廓线，接近线稿", group: .outline),
    EffectInfo(id: "grayscale", name: "黑白 / 灰度", desc: "去色，只留明暗层次", group: .tone),
    EffectInfo(id: "dither", name: "抖动过渡", desc: "点阵过渡，渐变更细腻", group: .texture),
    EffectInfo(id: "dark_chart", name: "深色底图纸", desc: "深色纸面，省墨也更好看", group: .texture),
    EffectInfo(id: "max_colors", name: "限色数", desc: "压到更少颜色，贴近预算", group: .style),
    EffectInfo(id: "preset", name: "风格色板", desc: "马卡龙 / Y2K / 节日预设", group: .style),
    EffectInfo(id: "adjust", name: "画面调整", desc: "亮度、对比度、饱和度", group: .tone),
    EffectInfo(id: "mirror", name: "镜像", desc: "水平或垂直翻转画面", group: .composition),
    EffectInfo(id: "crop", name: "裁剪", desc: "裁掉边缘，聚焦主体", group: .composition),
    EffectInfo(id: "cel_shade", name: "赛璐璐色阶", desc: "分层色阶，动画赛璐璐感", group: .tone),
    EffectInfo(id: "neon", name: "霓虹", desc: "高饱和 + 压暗，夜光感", group: .tone),
    EffectInfo(id: "duotone", name: "双色调", desc: "两种颜色重塑明暗", group: .tone),
    EffectInfo(id: "bg_remove", name: "背景去除", desc: "按颜色容差去背景", group: .composition),
    EffectInfo(id: "chibi", name: "大头（Q 版）", desc: "放大头部，Q 版比例（需 OpenCV）", group: .composition),
]

extension AppViewModel {
    func uiIsEffectOn(_ id: String) -> Bool {
        switch id {
        case "outline_cell": return outlineCellOn
        case "outline_edge": return outlineEdgeOn
        case "grayscale": return grayscaleOn
        case "dither": return ditherOn
        case "dark_chart": return darkChartOn
        case "max_colors": return maxColorsOn
        case "preset": return presetOn
        case "adjust": return adjustOn
        case "mirror": return mirrorOn
        case "crop": return cropOn
        case "cel_shade": return celShadeOn
        case "neon": return neonOn
        case "duotone": return duotoneOn
        case "bg_remove": return bgRemoveOn
        case "chibi": return chibiOn
        default: return false
        }
    }

    /// effects-qa T5 自动预览接线：特效/参数变更 → 脏标记 + 500ms debounce 自动刷新
    func uiNotifyParametersChanged() {
        guard imagePath != nil else { return }
        parametersDidChange()
    }

    func uiBinding(for id: String) -> Binding<Bool> {
        return Binding(
            get: { [weak self] in
                guard let self else { return false }
                return self.uiIsEffectOn(id)
            },
            set: { [weak self] value in
                guard let self else { return }
                switch id {
                case "outline_cell": self.outlineCellOn = value
                case "outline_edge": self.outlineEdgeOn = value
                case "grayscale": self.grayscaleOn = value
                case "dither": self.ditherOn = value
                case "dark_chart": self.darkChartOn = value
                case "max_colors": self.maxColorsOn = value
                case "preset": self.presetOn = value
                case "adjust": self.adjustOn = value
                case "mirror": self.mirrorOn = value
                case "crop": self.cropOn = value
                case "cel_shade": self.celShadeOn = value
                case "neon": self.neonOn = value
                case "duotone": self.duotoneOn = value
                case "bg_remove": self.bgRemoveOn = value
                case "chibi": self.chibiOn = value
                default: break
                }
                self.uiNotifyParametersChanged()
            }
        )
    }
}

func effectName(_ id: String) -> String {
    effectCatalog.first(where: { $0.id == id })?.name ?? id
}



// MARK: - 预览视口数学（纯函数，供缩放/平移/钳制与单元测试复用）

enum PreviewViewport {
    static let minZoom: Double = 25
    static let maxZoom: Double = 400
    static let minVisibleFraction: CGFloat = 0.15

    static func clampZoom(_ zoom: Double) -> Double {
        min(maxZoom, max(minZoom, zoom))
    }

    static func displaySize(imageSize: CGSize, viewport: CGSize,
                            zoom: Double, fitToWindow: Bool) -> CGSize {
        guard imageSize.width > 0, imageSize.height > 0,
              viewport.width > 0, viewport.height > 0 else { return .zero }
        let scale: CGFloat = fitToWindow
            ? min(viewport.width / imageSize.width, viewport.height / imageSize.height)
            : CGFloat(zoom) / 100.0
        return CGSize(width: imageSize.width * scale, height: imageSize.height * scale)
    }

    static func fittedZoomPercent(imageSize: CGSize, viewport: CGSize) -> Double {
        guard imageSize.width > 0, imageSize.height > 0,
              viewport.width > 0, viewport.height > 0 else { return 100 }
        let scale = min(viewport.width / imageSize.width, viewport.height / imageSize.height)
        // fit 模式下展示真实比例（可能 < 25%），不套用手动缩放的下限
        return max(1, Double(scale * 100))
    }

    /// offset 钳制：大图至少保留 minVisibleFraction 可见；小图（≤ 视口）保持居中
    static func clampOffset(_ offset: CGSize, displaySize: CGSize, viewport: CGSize,
                            minVisibleFraction: CGFloat = PreviewViewport.minVisibleFraction) -> CGSize {
        guard viewport.width > 0, viewport.height > 0 else { return .zero }
        func axis(_ value: CGFloat, image: CGFloat, viewport v: CGFloat) -> CGFloat {
            guard image > 0 else { return 0 }
            if image <= v + 0.5 { return 0 }
            let visible = min(1, max(0, minVisibleFraction)) * image
            let lower = visible - image - (v - image) / 2
            let upper = v - visible - (v - image) / 2
            return min(max(value, lower), upper)
        }
        return CGSize(width: axis(offset.width, image: displaySize.width, viewport: viewport.width),
                      height: axis(offset.height, image: displaySize.height, viewport: viewport.height))
    }

    /// 图版坐标（左上原点，含 16pt 内边距）→ 视口坐标（左上原点）
    static func viewportPoint(fromPlatePoint p: CGPoint, inset: CGFloat) -> CGPoint {
        CGPoint(x: p.x - inset, y: p.y - inset)
    }

    /// 锚点缩放：保持 anchor（视口坐标）下的图像点不动
    static func anchoredOffset(currentOffset: CGSize, oldSize: CGSize, newSize: CGSize,
                               anchor: CGPoint, viewport: CGSize) -> CGSize {
        guard oldSize.width > 1, oldSize.height > 1,
              viewport.width > 1, viewport.height > 1 else { return currentOffset }
        let center = CGPoint(x: viewport.width / 2, y: viewport.height / 2)
        let f = newSize.width / oldSize.width
        let dx = (anchor.x - center.x) - ((anchor.x - center.x) - currentOffset.width) * f
        let dy = (anchor.y - center.y) - ((anchor.y - center.y) - currentOffset.height) * f
        return CGSize(width: dx, height: dy)
    }
}

// MARK: - 真实滚轮 / 触控板事件（scrollWheel / magnify / 双指滚动平移）

struct PreviewInputCatcher: NSViewRepresentable {
    var onZoom: (CGFloat, CGPoint) -> Void   // factor, 视口内坐标（左上原点）
    var onPan: (CGSize) -> Void
    var inset: CGFloat = 16

    func makeNSView(context: Context) -> NSView {
        let view = EventCatcherView()
        view.onZoom = onZoom
        view.onPan = onPan
        view.inset = inset
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        guard let view = nsView as? EventCatcherView else { return }
        view.onZoom = onZoom
        view.onPan = onPan
        view.inset = inset
    }

    final class EventCatcherView: NSView {
        var onZoom: ((CGFloat, CGPoint) -> Void)?
        var onPan: ((CGSize) -> Void)?
        var inset: CGFloat = 16
        private var monitor: Any?

        override func hitTest(_ point: NSPoint) -> NSView? { nil }

        /// 使用左上原点，与 SwiftUI 预览视口坐标系一致（修 P3 R1：锚点上下镜像）
        override var isFlipped: Bool { true }

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            removeMonitor()
            guard window != nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: [.scrollWheel, .magnify]) { [weak self] event in
                guard let self, event.window === self.window else { return event }
                let point = self.convert(event.locationInWindow, from: nil)
                guard self.bounds.contains(point) else { return event }
                // 图版（含 16pt padding）→ 预览视口坐标（左上原点）
                let viewportPoint = PreviewViewport.viewportPoint(fromPlatePoint: point,
                                                                  inset: self.inset)
                switch event.type {
                case .magnify:
                    self.onZoom?(1 + event.magnification, viewportPoint)
                    return nil
                case .scrollWheel:
                    let precise = event.hasPreciseScrollingDeltas
                    let wantsZoom = event.modifierFlags.contains(.command)
                        || event.modifierFlags.contains(.option)
                        || !precise
                    if wantsZoom {
                        let delta = event.scrollingDeltaY
                        guard abs(delta) > 0.01 else { return event }
                        let factor = 1 + delta * (precise ? 0.01 : 0.06)
                        self.onZoom?(factor, viewportPoint)
                    } else {
                        let dx = event.scrollingDeltaX
                        let dy = event.scrollingDeltaY
                        guard abs(dx) + abs(dy) > 0.1 else { return event }
                        self.onPan?(CGSize(width: dx, height: dy))
                    }
                    return nil
                default:
                    return event
                }
            }
        }

        private func removeMonitor() {
            if let monitor {
                NSEvent.removeMonitor(monitor)
                self.monitor = nil
            }
        }

        deinit { removeMonitor() }
    }
}

