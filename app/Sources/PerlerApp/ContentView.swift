import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct ContentView: View {
    @StateObject private var vm = AppViewModel()
    @State private var showColorChart = false

    var body: some View {
        HStack(spacing: 0) {
            settingsPanel
                .frame(width: 300)
            Divider()
            previewPanel
        }
        .background(.ultraThinMaterial)
        .sheet(isPresented: $showColorChart) {
            ColorChartView(paletteInternal: vm.paletteInternal,
                           paletteDisplay: vm.paletteDisplay, engine: vm.engine)
        }
        .onAppear(perform: vm.setup)
    }

    // MARK: - 设置面板
    private var settingsPanel: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                glassSection("图片源") {
                    Button(action: chooseImage) {
                        Label(vm.imagePath == nil ? "选择图片…"
                              : (vm.imagePath! as NSString).lastPathComponent,
                              systemImage: "photo")
                    }
                    .buttonStyle(.bordered)
                    .disabled(vm.isBusy)
                    if vm.templates.isEmpty == false {
                        Picker("模板", selection: $vm.selectedTemplate) {
                            Text("自定义").tag(String?.none)
                            ForEach(vm.templates, id: \.id) { t in
                                Text("\(t.name) (\(t.width)×\(t.height))").tag(Optional(t.id))
                            }
                        }
                        .onChange(of: vm.selectedTemplate) { _, id in
                            vm.loadTemplate(id)
                        }
                    }
                }

                glassSection("网格") {
                    gridField("宽 (颗)", text: $vm.gridW)
                    gridField("高 (颗)", text: $vm.gridH)
                    gridField("每格像素", text: $vm.cellSize)
                    Picker("比例", selection: $vm.ratioMode) {
                        ForEach(vm.ratioOptions, id: \.self) { option in
                            Text(option).tag(option)
                        }
                    }
                    .onChange(of: vm.ratioMode) { _, _ in
                        vm.applyRatioLink()
                    }
                }

                glassSection("色卡") {
                    Picker("色卡", selection: $vm.paletteDisplay) {
                        ForEach(vm.palettes, id: \.display) { p in
                            Text("\(p.display) (\(p.count))").tag(p.display)
                        }
                    }
                    Button("查看色卡") { showColorChart = true }
                        .buttonStyle(.bordered)
                }

                glassSection("特效（默认关闭）") {
                    Toggle("邻接描边", isOn: $vm.outlineCellOn)
                    Toggle("线稿描边", isOn: $vm.outlineEdgeOn)
                    Toggle("黑白/灰度", isOn: $vm.grayscaleOn)
                    Toggle("抖动过渡", isOn: $vm.ditherOn)
                    Toggle("深色底图纸", isOn: $vm.darkChartOn)
                    Toggle("限色数", isOn: $vm.maxColorsOn)
                    if vm.maxColorsOn {
                        Stepper("最多 \(vm.maxColorsValue) 色",
                                value: $vm.maxColorsValue, in: 2...50)
                    }
                    Toggle("风格色板", isOn: $vm.presetOn)
                    if vm.presetOn {
                        Picker("风格", selection: $vm.presetName) {
                            Text("马卡龙可爱").tag("pastel")
                            Text("Preppy/Y2K").tag("preppy")
                            Text("万圣节").tag("halloween")
                            Text("圣诞").tag("christmas")
                            Text("Cottagecore").tag("cottagecore")
                        }
                    }
                }

                glassSection("操作") {
                    HStack {
                        Button(action: vm.generate) {
                            Label("生成", systemImage: "sparkles")
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(vm.isBusy || (vm.imagePath == nil && vm.selectedTemplate == nil))
                        if vm.isBusy {
                            Button("取消", role: .destructive) { vm.cancelActive() }
                        }
                    }
                    if vm.lastResult != nil {
                        Button("导出 PNG…") { exportPNG() }
                        Button("导出 PDF…") { showPDFModeDialog = true }
                    }
                }
                .confirmationDialog("PDF 导出模式", isPresented: $showPDFModeDialog) {
                    Button("适应 A4 单页") { exportPDF(mode: "a4") }
                    Button("1:1 实物大小多页") { exportPDF(mode: "1x1") }
                    Button("取消", role: .cancel) {}
                }

                HStack {
                    if vm.isBusy {
                        if vm.progress >= 0 {
                            ProgressView(value: vm.progress).controlSize(.small)
                        } else {
                            ProgressView().controlSize(.small)
                        }
                    }
                    Text(vm.statusText)
                        .font(.caption)
                        .foregroundStyle(vm.isBusy ? Color.accentColor : .secondary)
                }
                .padding(.horizontal, 4)
            }
            .padding(12)
        }
    }

    private func glassSection<Content: View>(_ title: String,
                                             @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline)
            content()
        }
        .padding(12)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
    }

    private func gridField(_ label: String, text: Binding<String>) -> some View {
        HStack {
            Text(label).frame(width: 70, alignment: .leading)
            TextField(label, text: text).textFieldStyle(.roundedBorder)
        }
    }

    // MARK: - 预览面板
    @State private var showPDFModeDialog = false

    private var previewPanel: some View {
        VStack(spacing: 8) {
            ZStack {
                Rectangle().fill(Color.gray.opacity(0.12))
                if let img = vm.effectiveShowFinished ? vm.finishedImage : vm.chartImage {
                    previewImage(img)
                } else {
                    Text(vm.isBusy ? "正在处理…" : "请选择图片或模板并生成")
                        .foregroundStyle(.secondary)
                }
            }
            .clipped()
            .gesture(dragGesture, including: vm.editMode ? .none : .all)
            .gesture(editGesture, including: vm.editMode ? .all : .none)
            .onTapGesture(count: 2) { vm.resetPreviewOffset() }
            .onDrop(of: [UTType.fileURL], isTargeted: nil) { providers in
                handleDrop(providers)
            }

            HStack {
                Toggle("适应窗口", isOn: $vm.fitToWindow)
                Slider(value: $vm.zoom, in: 25...400, step: 5)
                    .frame(maxWidth: 240)
                Text("\(Int(vm.zoom))%").font(.caption).frame(width: 44)
                Toggle("成品效果", isOn: $vm.showFinished)
                Spacer()
                Toggle("编辑模式", isOn: $vm.editMode)
                if vm.editMode {
                    Toggle("进度标记", isOn: $vm.trackMode)
                    if vm.trackMode {
                        Text("\(vm.trackedCount)/\(vm.totalGrid)")
                            .font(.caption)
                    } else {
                        TextField("色号", text: $vm.editColorCode)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 70)
                        Button("撤销") { vm.undoEdit() }
                            .disabled(vm.editHistory.isEmpty)
                    }
                }
            }
            .padding(.horizontal)
        }
        .padding()
    }

    private func previewImage(_ img: NSImage) -> some View {
        GeometryReader { geo in
            let size = vm.previewSize(img: img)
            Image(nsImage: img)
                .resizable()
                .interpolation(.none)
                .frame(width: size.width, height: size.height)
                .offset(vm.offset)
                .position(x: geo.size.width / 2 + vm.offset.width,
                          y: geo.size.height / 2 + vm.offset.height)
                .onAppear { vm.previewGeo = geo.size }
                .onChange(of: geo.size) { _, newValue in vm.previewGeo = newValue }
        }
    }

    private var dragGesture: some Gesture {
        DragGesture()
            .onChanged { value in
                vm.offset = value.translation
            }
            .onEnded { _ in }
    }

    private var editGesture: some Gesture {
        SpatialTapGesture()
            .onEnded { value in
                vm.handlePreviewTap(location: value.location)
            }
    }

    // MARK: - 文件交互
    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
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
        panel.allowedContentTypes = [.png, .jpeg, .webP]
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
        let name = mode == "1x1" ? "perler_\(result.gridW)x\(result.gridH)_1x1.pdf"
                                  : "perler_\(result.gridW)x\(result.gridH).pdf"
        guard let dest = savePanel(defaultName: name, types: ["pdf"]) else { return }
        vm.exportPDF(to: dest, mode: mode)
    }
}
