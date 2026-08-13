import Foundation
import AppKit

/// 主界面交互逻辑（可测试：模拟用户操作 = 调用 VM 方法 + 真实引擎后端）
@MainActor
final class AppViewModel: ObservableObject {

    // MARK: 引擎
    @Published var engine: Engine?
    @Published var statusText = "就绪"
    @Published var isBusy = false
    @Published var progress: Double = -1
    private var activeRequestID: Int?

    /// R4: 取消当前生成/编辑请求（rid 未就绪时也立即复位 UI）
    func cancelActive() {
        if let eng = engine, let rid = activeRequestID {
            eng.request(op: "cancel", params: [:], requestID: rid) { _ in }
        }
        isBusy = false
        progress = -1
        activeRequestID = nil
        statusText = "已取消"
    }

    // MARK: 参数
    @Published var imagePath: String?
    /// 最后编辑的维度（'w'/'h'）：固定比例下生成前按它联动另一侧
    private var lastEditedDim = "w"
    /// 程序写入联动值时抑制 didSet 记录（避免联动自身被当作用户编辑）
    private var linking = false
    /// 最近一次程序写入的字段值：用于区分「用户编辑」与「联动回声」
    private var lastProgrammaticW: String?
    private var lastProgrammaticH: String?
    @Published var gridW = "29" {
        didSet { if !linking && gridW != oldValue { lastEditedDim = "w" } }
    }
    @Published var gridH = "29" {
        didSet { if !linking && gridH != oldValue { lastEditedDim = "h" } }
    }
    @Published var cellSize = "60"
    @Published var ratioMode = "原始比例"
    @Published var paletteDisplay = "MARD 221 色"
    @Published var selectedTemplate: String?
    @Published var palettes: [PaletteInfo] = []
    @Published var templates: [TemplateInfo] = []

    let ratioOptions = ["原始比例", "等比完整", "1:1", "4:3", "3:4", "16:9", "9:16"]

    // 输入钳制（对齐 Tk 版规则）
    private static let gridRange = 1...500
    private static let cellRange = 16...160

    private func clampedGrid(_ text: String, fallback: Int) -> Int {
        let v = Int(text) ?? fallback
        return min(max(v, Self.gridRange.lowerBound), Self.gridRange.upperBound)
    }

    private func clampedCell(_ text: String) -> Int {
        let v = Int(text) ?? 60
        return min(max(v, Self.cellRange.lowerBound), Self.cellRange.upperBound)
    }

    /// R1: 比例模式 → 网格参数（exact_grid 强制精确，fit_box 等比完整）
    private func gridParams() -> (exact: Bool, fitBox: Bool) {
        switch ratioMode {
        case "等比完整":
            return (false, true)
        case "1:1", "4:3", "3:4", "16:9", "9:16":
            return (true, false)
        default:
            return (false, false)
        }
    }

    /// 固定比例联动（纯函数：返回联动后的 (w, h)）
    private func linkedDimensions(source: String, w: Int, h: Int) -> (Int, Int) {
        switch ratioMode {
        case "1:1":
            let side = source == "w" ? w : h
            return (side, side)
        case "4:3":
            return source == "w" ? (w, max(1, Int((Double(w) * 3 / 4).rounded())))
                                 : (max(1, Int((Double(h) * 4 / 3).rounded())), h)
        case "3:4":
            return source == "w" ? (w, max(1, Int((Double(w) * 4 / 3).rounded())))
                                 : (max(1, Int((Double(h) * 3 / 4).rounded())), h)
        case "16:9":
            return source == "w" ? (w, max(1, Int((Double(w) * 9 / 16).rounded())))
                                 : (max(1, Int((Double(h) * 16 / 9).rounded())), h)
        case "9:16":
            return source == "w" ? (w, max(1, Int((Double(w) * 16 / 9).rounded())))
                                 : (max(1, Int((Double(h) * 9 / 16).rounded())), h)
        default:
            return (w, h)
        }
    }

    /// 程序写入联动值（统一入口：置 linking 抑制 didSet 并记录回声指纹）
    private func writeLinked(_ w: Int, _ h: Int) {
        linking = true
        gridW = "\(w)"
        gridH = "\(h)"
        lastProgrammaticW = gridW
        lastProgrammaticH = gridH
        linking = false
    }

    /// 选择固定比例时联动（对齐 Tk 版双向联动行为）
    func applyRatioLink(source: String = "w") {
        let w = clampedGrid(gridW, fallback: 50)
        let h = clampedGrid(gridH, fallback: 50)
        let (nw, nh) = linkedDimensions(source: source, w: w, h: h)
        writeLinked(nw, nh)
    }

    /// 输入框内容变化 → 立即联动另一侧（实时联动）
    /// 仅当两侧都是合法数字时才联动，避免清空/半输入时误算；
    /// 程序写入的回声（值与上次联动结果一致）会被忽略，防止覆盖 lastEditedDim。
    func gridFieldEdited(_ source: String) {
        if gridW == lastProgrammaticW && gridH == lastProgrammaticH { return }
        guard Int(gridW.trimmingCharacters(in: .whitespaces)) != nil,
              Int(gridH.trimmingCharacters(in: .whitespaces)) != nil else {
            lastEditedDim = source
            return
        }
        lastEditedDim = source
        let w = clampedGrid(gridW, fallback: 50)
        let h = clampedGrid(gridH, fallback: 50)
        let (nw, nh) = linkedDimensions(source: source, w: w, h: h)
        writeLinked(nw, nh)
    }

    /// 输入框回车提交：规范化当前维度并联动另一侧
    func commitDimension(_ source: String) {
        lastEditedDim = source
        let w = clampedGrid(gridW, fallback: 50)
        let h = clampedGrid(gridH, fallback: 50)
        let (nw, nh) = linkedDimensions(source: source, w: w, h: h)
        writeLinked(nw, nh)
    }

    // MARK: 特效（全部默认关闭）
    @Published var outlineCellOn = false
    @Published var outlineEdgeOn = false
    @Published var grayscaleOn = false
    @Published var ditherOn = false
    @Published var darkChartOn = false
    @Published var maxColorsOn = false
    @Published var maxColorsValue = 12
    @Published var presetOn = false
    @Published var presetName = "pastel"

    // MARK: 结果
    @Published var chartImage: NSImage?
    @Published var finishedImage: NSImage?
    @Published private(set) var lastResult: GenerateResult?

    // MARK: 编辑与进度
    @Published var editMode = false
    @Published var editColorCode = "H7"
    @Published var trackMode = false
    @Published private(set) var editHistory: [[String: Any]] = []
    @Published private(set) var doneCells: Set<String> = []
    @Published private(set) var trackedCount = 0
    private var trackKey: String?

    // MARK: 预览
    @Published var zoom: Double = 100
    @Published var fitToWindow = true
    @Published var showFinished = false
    @Published var offset = CGSize.zero
    @Published var previewGeo = CGSize(width: 800, height: 600)

    var paletteInternal: String {
        palettes.first { $0.display == paletteDisplay }?.internalName ?? "mard_221"
    }

    /// R2: 编辑模式下强制显示图纸（成品切换在编辑时无效，避免点击错位）
    var effectiveShowFinished: Bool {
        !editMode && showFinished
    }

    var totalGrid: Int {
        (lastResult?.gridW ?? 0) * (lastResult?.gridH ?? 0)
    }

    // MARK: - 初始化
    func setup() {
        guard let py = Engine.findPython() else {
            statusText = "未找到 Python 引擎（需要 pindou 环境）"
            return
        }
        guard let eng = Engine(pythonPath: py) else {
            statusText = "引擎启动失败"
            return
        }
        engine = eng
        // F1/F4: 引擎异常退出 → 状态栏显示退出与日志
        eng.onEngineExit = { [weak self] in
            guard let self else { return }
            let log = eng.engineErrorLog
            let tail = String(log.suffix(200))
            self.statusText = "引擎已退出\(tail.isEmpty ? "" : "：\(tail)")"
            self.isBusy = false
            self.progress = -1
        }
        // F4: ping 5s 超时
        eng.ping { [weak self] result in
            guard let self else { return }
            switch result {
            case .success:
                self.statusText = "引擎就绪"
                self.loadPalettes()
                self.loadTemplates()
            case .failure(let e):
                self.statusText = "引擎连接失败：\(e.localizedDescription)"
            }
        }
    }

    func loadPalettes() {
        guard let eng = engine else { return }
        eng.request(op: "palettes", params: [:]) { [weak self] result in
            guard let self, case .success(let r) = result,
                  let arr = r["palettes"] as? [[String: Any]] else { return }
            let list = arr.compactMap { d -> PaletteInfo? in
                guard let display = d["display"] as? String,
                      let count = d["count"] as? Int else { return nil }
                return PaletteInfo(display: display, count: count,
                                   internalName: d["internal"] as? String ?? display)
            }
            self.palettes = list
            if !list.isEmpty {
                self.paletteDisplay = list.contains { $0.display == "MARD 221 色" }
                    ? "MARD 221 色" : list[0].display
            }
        }
    }

    func loadTemplates() {
        guard let eng = engine else { return }
        eng.request(op: "templates", params: [:]) { [weak self] result in
            guard let self, case .success(let r) = result,
                  let arr = r["templates"] as? [[String: Any]] else { return }
            self.templates = arr.compactMap { d in
                guard let id = d["id"] as? String, let name = d["name"] as? String,
                      let w = d["width"] as? Int, let h = d["height"] as? Int else { return nil }
                return TemplateInfo(id: id, name: name, width: w, height: h)
            }
        }
    }

    // MARK: - 图片 / 模板
    func setImagePath(_ path: String) {
        imagePath = path
        selectedTemplate = nil
        resetForNewImage(path)
        statusText = "已选择图片"
    }

    /// 换图/换模板时重置结果与编辑状态（防止旧编辑污染新图）
    private func resetForNewImage(_ keySource: String) {
        editHistory = []
        doneCells = []
        trackedCount = 0
        lastResult = nil
        chartImage = nil
        finishedImage = nil
        offset = .zero
        progress = -1
        trackKey = stableKey(keySource)
        loadTrack()
    }

    func loadTemplate(_ id: String?) {
        guard let id, let eng = engine else { return }
        eng.request(op: "template_image", params: ["template_id": id]) { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(let r):
                if let p = r["image_path"] as? String {
                    self.imagePath = p
                    self.selectedTemplate = id
                    if let w = r["width"] as? Int { self.gridW = "\(w)" }
                    if let h = r["height"] as? Int { self.gridH = "\(h)" }
                    self.resetForNewImage("tpl_\(id)")
                    self.syncPaletteToTemplate(id)
                    self.statusText = "已加载模板"
                }
            case .failure(let e):
                self.statusText = "模板加载失败：\(e.localizedDescription)"
            }
        }
    }

    /// 模板-色卡联动：模板 palette 名同步到选择器
    private func syncPaletteToTemplate(_ templateId: String) {
        guard let eng = engine else { return }
        eng.request(op: "templates", params: [:]) { [weak self] result in
            guard let self, case .success(let r) = result,
                  let arr = r["templates"] as? [[String: Any]],
                  let tpl = arr.first(where: { ($0["id"] as? String) == templateId }),
                  let internalName = tpl["palette"] as? String else { return }
            if let info = self.palettes.first(where: { $0.internalName == internalName }) {
                self.paletteDisplay = info.display
            }
        }
    }

    // MARK: - 生成
    func effectsParams() -> [[String: Any]] {
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

    func generate() {
        guard let eng = engine, let path = imagePath else { return }
        isBusy = true
        progress = 0
        statusText = "正在处理…"
        let gp = gridParams()
        var w = clampedGrid(gridW, fallback: 29)
        var h = clampedGrid(gridH, fallback: 29)
        if gp.exact {
            // 生成前按最后编辑的维度联动，保证固定比例下尺寸一致（对齐 Tk 行为）
            let (nw, nh) = linkedDimensions(source: lastEditedDim, w: w, h: h)
            w = nw
            h = nh
            writeLinked(nw, nh)
        }
        let params: [String: Any] = [
            "image_path": path,
            "grid_w": w,
            "grid_h": h,
            "cell_size": clampedCell(cellSize),
            "palette": paletteInternal,
            "show_finished": true,
            "effects": effectsParams(),
            "fit_box": gp.fitBox,
            "exact_grid": gp.exact,
        ]
        eng.request(op: "generate", params: params,
                    onProgress: { [weak self] p in
                        Task { @MainActor in self?.progress = p }
                    },
                    onStart: { [weak self] rid in
                        self?.activeRequestID = rid
                    }) { [weak self] result in
            guard let self else { return }
            defer {
                self.isBusy = false
                self.progress = -1
                self.activeRequestID = nil
            }
            switch result {
            case .success(let r):
                guard let data = try? JSONSerialization.data(withJSONObject: r),
                      let gen = try? JSONDecoder().decode(GenerateResult.self, from: data) else {
                    statusText = "解析结果失败"
                    return
                }
                applyResult(gen)
                statusText = "完成：\(gen.gridW)×\(gen.gridH) | \(gen.totalBeads) 颗"
            case .failure(let e):
                statusText = "生成失败：\(e.localizedDescription)"
            }
        }
    }

    private func applyResult(_ gen: GenerateResult) {
        lastResult = gen
        chartImage = loadPreviewImage(path: gen.chartPath)
        if let fp = gen.finishedPath {
            finishedImage = loadPreviewImage(path: fp)
        } else {
            finishedImage = nil
        }
        if trackKey != nil { loadTrack() }
    }

    /// F5: 预览图降采样（≤2048px），避免大图在主线程渲染卡顿
    private func loadPreviewImage(path: String) -> NSImage? {
        guard let img = NSImage(contentsOfFile: path) else { return nil }
        let maxDim: CGFloat = 2048
        let w = img.size.width
        let h = img.size.height
        guard w > 0, h > 0, max(w, h) > maxDim else { return img }
        let scale = maxDim / max(w, h)
        let newSize = NSSize(width: w * scale, height: h * scale)
        let out = NSImage(size: newSize)
        out.lockFocus()
        img.draw(in: NSRect(origin: .zero, size: newSize),
                 from: .zero, operation: .copy, fraction: 1.0)
        out.unlockFocus()
        return out
    }

    // MARK: - 编辑
    func handlePreviewTap(location: CGPoint) {
        guard let img = chartImage, let result = lastResult else { return }
        let geo = previewSize(img: img)
        let imgX = (previewGeo.width - geo.width) / 2 + offset.width
        let imgY = (previewGeo.height - geo.height) / 2 + offset.height
        let px = Int((location.x - imgX) / geo.width * CGFloat(result.gridW))
        let py = Int((location.y - imgY) / geo.height * CGFloat(result.gridH))
        guard px >= 0, px < result.gridW, py >= 0, py < result.gridH else { return }

        if trackMode {
            toggleTrackedCell(x: px, y: py)
        } else {
            let code = editColorCode.trimmingCharacters(in: .whitespaces).uppercased()
            guard !code.isEmpty else { return }
            editHistory.append(["x": px, "y": py, "code": code])
            applyEdits()
        }
    }

    func undoEdit() {
        guard let popped = editHistory.popLast() else { return }
        let key = cellKey(popped)
        doneCells.remove(key)
        trackedCount = doneCells.count
        applyEdits()
    }

    private func applyEdits() {
        guard let eng = engine, let path = imagePath, let result = lastResult else { return }
        isBusy = true
        statusText = "正在应用编辑…"
        let gp = gridParams()
        eng.request(op: "edit", params: [
            "image_path": path,
            "grid_w": result.gridW,
            "grid_h": result.gridH,
            "cell_size": result.cellSize,
            "palette": paletteInternal,
            "effects": effectsParams(),
            "fit_box": gp.fitBox,
            "exact_grid": gp.exact,
            "overrides": editHistory,
        ]) { [weak self] res in
            guard let self else { return }
            defer { self.isBusy = false }
            switch res {
            case .success(let r):
                guard let data = try? JSONSerialization.data(withJSONObject: r),
                      let gen = try? JSONDecoder().decode(GenerateResult.self, from: data) else {
                    statusText = "编辑解析失败"
                    return
                }
                applyResult(gen)
                for edit in editHistory {
                    doneCells.insert(cellKey(edit))
                }
                trackedCount = doneCells.count
                saveTrack()
                statusText = "已编辑：\(editHistory.count) 处 | 已完成 \(doneCells.count) 格"
            case .failure(let e):
                statusText = "编辑失败：\(e.localizedDescription)"
            }
        }
    }

    // MARK: - 进度追踪
    private func toggleTrackedCell(x: Int, y: Int) {
        let key = "\(x):\(y)"
        if doneCells.contains(key) {
            doneCells.remove(key)
        } else {
            doneCells.insert(key)
        }
        trackedCount = doneCells.count
        saveTrack()
        statusText = "进度：\(doneCells.count)/\(totalGrid) 格"
    }

    private func cellKey(_ edit: [String: Any]) -> String {
        "\(edit["x"] ?? 0):\(edit["y"] ?? 0)"
    }

    private func stableKey(_ path: String) -> String {
        var h = UInt64(5381)
        for b in path.utf8 {
            h = (h &* 33) ^ UInt64(b)
        }
        return String(h, radix: 16)
    }

    private func saveTrack() {
        guard let eng = engine, let key = trackKey else { return }
        eng.request(op: "track_save",
                    params: ["key": key, "cells": Array(doneCells)]) { _ in }
    }

    private func loadTrack() {
        guard let eng = engine, let key = trackKey else {
            doneCells = []
            trackedCount = 0
            return
        }
        eng.request(op: "track_load", params: ["key": key]) { [weak self] result in
            guard let self, case .success(let r) = result else { return }
            let cells = r["track"] as? [String] ?? []
            self.doneCells = Set(cells)
            self.trackedCount = cells.count
        }
    }

    // MARK: - 预览
    func previewSize(img: NSImage) -> CGSize {
        let base = CGSize(width: img.size.width, height: img.size.height)
        let scale: CGFloat
        if fitToWindow {
            scale = min(previewGeo.width / base.width, previewGeo.height / base.height)
        } else {
            scale = CGFloat(zoom) / 100.0
        }
        return CGSize(width: base.width * scale, height: base.height * scale)
    }

    // MARK: - 导出
    func exportPNG(to path: String) {
        guard let eng = engine, let result = lastResult else { return }
        eng.request(op: "export_png",
                    params: ["source_path": result.chartPath, "save_path": path]) { [weak self] res in
            guard let self else { return }
            switch res {
            case .success: self.statusText = "PNG 已导出"
            case .failure(let e): self.statusText = "PNG 导出失败：\(e.localizedDescription)"
            }
        }
    }

    func exportPDF(to path: String, mode: String = "a4", includeBOM: Bool = true) {
        guard let eng = engine, let result = lastResult else { return }
        var params: [String: Any] = [
            "source_path": result.chartPath, "save_path": path,
            "mode": mode, "cell_size": result.cellSize,
        ]
        if includeBOM { params["bom"] = result.colorStatsAny }
        eng.request(op: "export_pdf", params: params) { [weak self] res in
            guard let self else { return }
            switch res {
            case .success:
                let modeName = mode == "1x1" ? "1:1 实物" : "A4"
                self.statusText = "PDF 已导出（\(modeName)）"
            case .failure(let e): self.statusText = "PDF 导出失败：\(e.localizedDescription)"
            }
        }
    }

    // MARK: - 重置
    func resetPreviewOffset() {
        offset = .zero
    }
}
