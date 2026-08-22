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
                        .disabled(vm.isBusy)
                    }
                }

                glassSection("网格") {
                    GridFieldRow(label: "宽 (颗)", text: $vm.gridW,
                                 onEdit: { vm.gridFieldEdited("w") },
                                 onSubmit: { vm.commitDimension("w") })
                    GridFieldRow(label: "高 (颗)", text: $vm.gridH,
                                 onEdit: { vm.gridFieldEdited("h") },
                                 onSubmit: { vm.commitDimension("h") })
                    GridFieldRow(label: "每格像素", text: $vm.cellSize)
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
                .position(x: geo.size.width / 2 + vm.offset.width,
                          y: geo.size.height / 2 + vm.offset.height)
                .onAppear { vm.previewGeo = geo.size }
                .onChange(of: geo.size) { _, newValue in vm.previewGeo = newValue }
        }
    }

    private var dragGesture: some Gesture {
        DragGesture()
            .onChanged { value in
                vm.dragChanged(value.translation)
            }
            .onEnded { _ in
                vm.dragEnded()
            }
    }

    private var editGesture: some Gesture {
        SpatialTapGesture()
            .onEnded { value in
                vm.handlePreviewTap(location: value.location)
            }
    }

    // MARK: - 文件交互
    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        // 忙时拒绝拖入：防在途请求的迟到结果污染新图状态
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
        let name = mode == "1x1" ? "perler_\(result.gridW)x\(result.gridH)_1x1.pdf"
                                  : "perler_\(result.gridW)x\(result.gridH).pdf"
        guard let dest = savePanel(defaultName: name, types: ["pdf"]) else { return }
        vm.exportPDF(to: dest, mode: mode)
    }
}

/// 网格输入行：NSTextField 桥接。
/// SwiftUI TextField 在 macOS 上有已知缺陷：窗口内有字段正在编辑时，
/// 程序化绑定更新不会重绘其他字段的显示文本（联动值变了但 UI 不动）。
/// 原生桥接在 updateNSView 对非焦点字段强制同步 stringValue，联动立即上屏；
/// 回车提交后若字段仍持焦点也回写规范化值（编辑会话已结束，光标移末尾可接受）。
struct GridFieldRow: View {
    let label: String
    @Binding var text: String
    var onEdit: (() -> Void)? = nil
    var onSubmit: (() -> Void)? = nil

    var body: some View {
        HStack {
            Text(label).frame(width: 70, alignment: .leading)
            NSTextFieldBridge(text: $text, label: label,
                              onEdit: onEdit, onSubmit: onSubmit)
                .frame(maxWidth: .infinity, minHeight: 24)
        }
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
        // 核心修复：非焦点时以 binding 为准——另一侧被联动写入时立即上屏
        if tf.currentEditor() == nil, tf.stringValue != text {
            tf.stringValue = text
        }
    }
}
