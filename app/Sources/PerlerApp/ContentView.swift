import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct ContentView: View {
    @State private var engine: Engine?
    @State private var engineError: String?
    @State private var palettes: [PaletteInfo] = []
    @State private var templates: [TemplateInfo] = []

    // 参数
    @State private var imagePath: String?
    @State private var gridW = "29"
    @State private var gridH = "29"
    @State private var cellSize = "60"
    @State private var paletteName = "MARD 221 色"
    @State private var selectedTemplate: String?

    // 特效开关
    @State private var outlineCellOn = false
    @State private var outlineEdgeOn = false
    @State private var grayscaleOn = false
    @State private var ditherOn = false
    @State private var darkChartOn = false
    @State private var maxColorsOn = false
    @State private var maxColorsValue = 12
    @State private var presetOn = false
    @State private var presetName = "pastel"

    // 状态
    @State private var chartImage: NSImage?
    @State private var finishedImage: NSImage?
    @State private var lastResult: GenerateResult?
    @State private var isBusy = false
    @State private var statusText = "就绪"
    @State private var showColorChart = false

    // 编辑
    @State private var editMode = false
    @State private var editColorCode = "H7"
    @State private var editHistory: [[String: Any]] = []
    @State private var doneCells: Set<String> = []
    @State private var trackKey: String?

    // 预览
    @State private var zoom: Double = 100
    @State private var fitToWindow = true
    @State private var showFinished = false
    @State private var offset = CGSize.zero
    @State private var previewGeo = CGSize(width: 800, height: 600)

    var body: some View {
        HStack(spacing: 0) {
            settingsPanel
                .frame(width: 300)
            Divider()
            previewPanel
        }
        .background(.ultraThinMaterial)
        .sheet(isPresented: $showColorChart) {
            ColorChartView(paletteName: paletteName, engine: engine)
        }
        .onAppear(perform: setup)
    }

    // MARK: - 设置面板（毛玻璃卡片）
    private var settingsPanel: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                glassSection("图片源") {
                    Button(action: chooseImage) {
                        Label(imagePath == nil ? "选择图片…"
                              : (imagePath! as NSString).lastPathComponent,
                              systemImage: "photo")
                    }
                    .buttonStyle(.bordered)
                    .disabled(isBusy)
                    if templates.isEmpty == false {
                        Picker("模板", selection: $selectedTemplate) {
                            Text("自定义").tag(String?.none)
                            ForEach(templates, id: \.id) { t in
                                Text("\(t.name) (\(t.width)×\(t.height))").tag(Optional(t.id))
                            }
                        }
                        .onChange(of: selectedTemplate) { _, id in
                            loadTemplate(id)
                        }
                    }
                }

                glassSection("网格") {
                    gridField("宽 (颗)", text: $gridW)
                    gridField("高 (颗)", text: $gridH)
                    gridField("每格像素", text: $cellSize)
                }

                glassSection("色卡") {
                    Picker("色卡", selection: $paletteName) {
                        ForEach(palettes, id: \.display) { p in
                            Text("\(p.display) (\(p.count))").tag(p.display)
                        }
                    }
                    Button("查看色卡") { showColorChart = true }
                        .buttonStyle(.bordered)
                }

                glassSection("特效（默认关闭）") {
                    Toggle("邻接描边", isOn: $outlineCellOn)
                    Toggle("线稿描边", isOn: $outlineEdgeOn)
                    Toggle("黑白/灰度", isOn: $grayscaleOn)
                    Toggle("抖动过渡", isOn: $ditherOn)
                    Toggle("深色底图纸", isOn: $darkChartOn)
                    Toggle("限色数", isOn: $maxColorsOn)
                    if maxColorsOn {
                        Stepper("最多 \(maxColorsValue) 色", value: $maxColorsValue, in: 2...50)
                    }
                    Toggle("风格色板", isOn: $presetOn)
                    if presetOn {
                        Picker("风格", selection: $presetName) {
                            Text("马卡龙可爱").tag("pastel")
                            Text("Preppy/Y2K").tag("preppy")
                            Text("万圣节").tag("halloween")
                            Text("圣诞").tag("christmas")
                            Text("Cottagecore").tag("cottagecore")
                        }
                    }
                }

                glassSection("操作") {
                    Button(action: generate) {
                        Label("生成", systemImage: "sparkles")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isBusy || (imagePath == nil && selectedTemplate == nil))
                    if let result = lastResult {
                        Button("导出 PNG…") { exportPNG(result: result) }
                        Button("导出 PDF…") { exportPDF(result: result) }
                    }
                }

                HStack {
                    if isBusy { ProgressView().controlSize(.small) }
                    Text(statusText)
                        .font(.caption)
                        .foregroundStyle(isBusy ? Color.accentColor : .secondary)
                }
                .padding(.horizontal, 4)
            }
            .padding(12)
        }
    }

    private func glassSection<Content: View>(_ title: String,
                                             @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
            content()
        }
        .padding(12)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
    }

    private func gridField(_ label: String, text: Binding<String>) -> some View {
        HStack {
            Text(label).frame(width: 70, alignment: .leading)
            TextField(label, text: text)
                .textFieldStyle(.roundedBorder)
        }
    }

    // MARK: - 预览面板
    private var previewPanel: some View {
        VStack(spacing: 8) {
            ZStack {
                Rectangle()
                    .fill(Color.gray.opacity(0.12))
                if let img = showFinished ? finishedImage : chartImage {
                    previewImage(img)
                } else {
                    Text(isBusy ? "正在处理…" : "请选择图片或模板并生成")
                        .foregroundStyle(.secondary)
                }
            }
            .clipped()
            .gesture(dragGesture, including: editMode ? .none : .all)
            .gesture(editGesture, including: editMode ? .all : .none)
            .onTapGesture(count: 2) { offset = .zero }

            HStack {
                Toggle("适应窗口", isOn: $fitToWindow)
                Slider(value: $zoom, in: 25...400, step: 5)
                    .frame(maxWidth: 240)
                Text("\(Int(zoom))%").font(.caption).frame(width: 44)
                Toggle("成品效果", isOn: $showFinished)
                Spacer()
                Toggle("编辑模式", isOn: $editMode)
                if editMode {
                    TextField("色号", text: $editColorCode)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 70)
                    Button("撤销") { undoEdit() }
                        .disabled(editHistory.isEmpty)
                    Toggle("进度标记", isOn: Binding(
                        get: { !doneCells.isEmpty },
                        set: { _ in }
                    ))
                }
            }
            .padding(.horizontal)
        }
        .padding()
    }

    private func previewImage(_ img: NSImage) -> some View {
        GeometryReader { geo in
            let size = self.previewSize(geo: geo.size, img: img)
            Image(nsImage: img)
                .resizable()
                .interpolation(.none)
                .frame(width: size.width, height: size.height)
                .offset(offset)
                .position(x: geo.size.width / 2 + offset.width,
                          y: geo.size.height / 2 + offset.height)
                .onAppear { previewGeo = geo.size }
                .onChange(of: geo.size) { _, newValue in previewGeo = newValue }
        }
    }

    private func previewSize(geo: CGSize, img: NSImage) -> CGSize {
        let base = CGSize(width: img.size.width, height: img.size.height)
        let scale: CGFloat
        if fitToWindow {
            scale = min(geo.width / base.width, geo.height / base.height)
        } else {
            scale = CGFloat(zoom) / 100.0
        }
        return CGSize(width: base.width * scale, height: base.height * scale)
    }

    private var dragGesture: some Gesture {
        DragGesture()
            .onChanged { value in
                offset = value.translation
            }
            .onEnded { _ in }
    }

    // MARK: - 编辑模式
    private var editGesture: some Gesture {
        SpatialTapGesture()
            .onEnded { value in
                handleEditTap(location: value.location)
            }
    }

    private func handleEditTap(location: CGPoint) {
        guard let img = chartImage, let result = lastResult else { return }
        // 预览区内图像实际位置：居中 + offset
        let geo = previewSize(geo: previewGeo, img: img)
        let imgX = (previewGeo.width - geo.width) / 2 + offset.width
        let imgY = (previewGeo.height - geo.height) / 2 + offset.height
        let px = Int((location.x - imgX) / geo.width * CGFloat(result.gridW))
        let py = Int((location.y - imgY) / geo.height * CGFloat(result.gridH))
        guard px >= 0, px < result.gridW, py >= 0, py < result.gridH else { return }

        let code = editColorCode.trimmingCharacters(in: .whitespaces).uppercased()
        guard !code.isEmpty else { return }
        editHistory.append(["x": px, "y": py, "code": code])
        applyEdits()
    }

    private func saveTrack(key: String) {
        guard let eng = engine else { return }
        eng.request(op: "track_save", params: ["key": key,
                                               "cells": Array(doneCells)]) { _ in }
    }

    private func undoEdit() {
        if !editHistory.isEmpty {
            editHistory.removeLast()
        }
        applyEdits()
    }

    private func applyEdits() {
        guard let eng = engine, let path = imagePath, let result = lastResult else { return }
        isBusy = true
        var params: [String: Any] = [
            "image_path": path,
            "grid_w": result.gridW,
            "grid_h": result.gridH,
            "cell_size": result.cellSize,
            "palette": paletteName,
            "effects": effectsParams(),
            "overrides": editHistory,
        ]
        eng.request(op: "edit", params: params) { res in
            defer { isBusy = false }
            switch res {
            case .success(let r):
                guard let data = try? JSONSerialization.data(withJSONObject: r),
                      let gen = try? JSONDecoder().decode(GenerateResult.self, from: data) else {
                    statusText = "编辑解析失败"
                    return
                }
                lastResult = gen
                chartImage = NSImage(contentsOfFile: gen.chartPath)
                let key = (gen.chartPath as NSString).lastPathComponent
                trackKey = key
                for edit in editHistory {
                    doneCells.insert("\(edit["x"] ?? 0):\(edit["y"] ?? 0)")
                }
                saveTrack(key: key)
                statusText = "已编辑：\(editHistory.count) 处修改 | 已完成 \(doneCells.count) 格"
            case .failure(let e):
                statusText = "编辑失败：\(e.localizedDescription)"
            }
        }
    }

    // MARK: - 初始化
    private func setup() {
        guard let py = Engine.findPython() else {
            statusText = "未找到 Python 引擎（需要 pindou 环境）"
            return
        }
        guard let eng = Engine(pythonPath: py) else {
            statusText = "引擎启动失败"
            return
        }
        engine = eng
        eng.ping { result in
            switch result {
            case .success:
                statusText = "引擎就绪"
                loadPalettes(eng)
                loadTemplates(eng)
            case .failure(let e):
                statusText = "引擎连接失败：\(e.localizedDescription)"
            }
        }
    }

    private func loadPalettes(_ eng: Engine) {
        eng.request(op: "palettes", params: [:]) { result in
            if case .success(let r) = result,
               let arr = r["palettes"] as? [[String: Any]] {
                palettes = arr.compactMap { d -> PaletteInfo? in
                    guard let display = d["display"] as? String,
                          let count = d["count"] as? Int else { return nil }
                    return PaletteInfo(display: display, count: count,
                                       internalName: d["internal"] as? String ?? display)
                }
                if !palettes.isEmpty { paletteName = palettes[0].display }
            }
        }
    }

    private func loadTemplates(_ eng: Engine) {
        eng.request(op: "templates", params: [:]) { result in
            if case .success(let r) = result,
               let arr = r["templates"] as? [[String: Any]] {
                templates = arr.compactMap { d in
                    guard let id = d["id"] as? String, let name = d["name"] as? String,
                          let w = d["width"] as? Int, let h = d["height"] as? Int else { return nil }
                    return TemplateInfo(id: id, name: name, width: w, height: h)
                }
            }
        }
    }

    private func chooseImage() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.png, .jpeg, .webP]
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            imagePath = url.path
            selectedTemplate = nil
            statusText = "已选择图片"
        }
    }

    private func loadTemplate(_ id: String?) {
        guard let id, let eng = engine else { return }
        eng.request(op: "template_image", params: ["template_id": id]) { result in
            switch result {
            case .success(let r):
                if let p = r["image_path"] as? String {
                    imagePath = p
                    if let w = r["width"] as? Int { gridW = "\(w)" }
                    if let h = r["height"] as? Int { gridH = "\(h)" }
                    statusText = "已加载模板"
                }
            case .failure(let e):
                statusText = "模板加载失败：\(e.localizedDescription)"
            }
        }
    }

    // MARK: - 生成
    private func effectsParams() -> [[String: Any]] {
        var effects: [[String: Any]] = []
        if outlineCellOn { effects.append(["id": "outline_cell", "params": [:] as [String: Any]]) }
        if outlineEdgeOn { effects.append(["id": "outline_edge", "params": [:] as [String: Any]]) }
        if grayscaleOn { effects.append(["id": "grayscale", "params": [:] as [String: Any]]) }
        if ditherOn { effects.append(["id": "dither", "params": [:] as [String: Any]]) }
        if darkChartOn { effects.append(["id": "dark_chart", "params": [:] as [String: Any]]) }
        if maxColorsOn { effects.append(["id": "max_colors", "params": ["max": maxColorsValue]]) }
        if presetOn { effects.append(["id": "preset", "params": ["preset": presetName]]) }
        return effects
    }

    private func generate() {
        guard let eng = engine, let path = imagePath else { return }
        isBusy = true
        statusText = "正在处理…"
        var params: [String: Any] = [
            "image_path": path,
            "grid_w": Int(gridW) ?? 29,
            "grid_h": Int(gridH) ?? 29,
            "cell_size": Int(cellSize) ?? 60,
            "palette": paletteName,
            "show_finished": true,
            "effects": effectsParams(),
        ]
        if selectedTemplate != nil { params["board"] = Int(gridW) ?? 29 }
        eng.request(op: "generate", params: params) { result in
            defer { isBusy = false }
            switch result {
            case .success(let r):
                guard let data = try? JSONSerialization.data(withJSONObject: r),
                      let gen = try? JSONDecoder().decode(GenerateResult.self, from: data) else {
                    statusText = "解析结果失败"
                    return
                }
                lastResult = gen
                chartImage = NSImage(contentsOfFile: gen.chartPath)
                statusText = "完成：\(gen.gridW)×\(gen.gridH) | \(gen.totalBeads) 颗"
            case .failure(let e):
                statusText = "生成失败：\(e.localizedDescription)"
            }
        }
    }

    // MARK: - 导出
    private func savePanel(defaultName: String, types: [String]) -> String? {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = defaultName
        panel.allowedContentTypes = types.compactMap { UTType(filenameExtension: $0) }
        return panel.runModal() == .OK ? panel.url?.path : nil
    }

    private func exportPNG(result: GenerateResult) {
        guard let eng = engine,
              let dest = savePanel(defaultName: "perler_\(result.gridW)x\(result.gridH).png",
                                   types: ["png"]) else { return }
        eng.request(op: "export_png",
                    params: ["source_path": result.chartPath, "save_path": dest]) { result in
            switch result {
            case .success: statusText = "PNG 已导出"
            case .failure(let e): statusText = "PNG 导出失败：\(e.localizedDescription)"
            }
        }
    }

    private func exportPDF(result: GenerateResult) {
        guard let eng = engine,
              let dest = savePanel(defaultName: "perler_\(result.gridW)x\(result.gridH).pdf",
                                   types: ["pdf"]) else { return }
        eng.request(op: "export_pdf",
                    params: ["source_path": result.chartPath, "save_path": dest,
                             "mode": "a4", "cell_size": result.cellSize,
                             "bom": result.colorStatsAny]) { result in
            switch result {
            case .success: statusText = "PDF 已导出（含材料清单）"
            case .failure(let e): statusText = "PDF 导出失败：\(e.localizedDescription)"
            }
        }
    }
}
