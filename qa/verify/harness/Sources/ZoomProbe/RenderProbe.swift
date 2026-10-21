import AppKit
import SwiftUI

// ============================================================================
// 渲染测量探针：真实 ContentView（HEAD/工作区源码）+ 注入已驱动 AppViewModel，
// 在 1280×800 窗口中按 fit/zoom/offset 组合渲染，用合成洋红图（带中心青色标记）
// 精确测出「预览图在屏幕上的实际像素尺寸与位置」，与独立计算的期望值对比。
// ============================================================================

struct RenderState {
    let name: String
    let fit: Bool
    let zoom: Double
    let offset: CGSize
}

@MainActor
final class ProbeSession {
    let repoRoot: String
    let outDir: String
    let phase: String
    let window: NSWindow
    let vm: AppViewModel
    let synthetic: NSImage
    let imgW: CGFloat = 600
    let imgH: CGFloat = 450

    var viewport: CGSize = .zero
    var refCenter: CGPoint = .zero        // 点坐标，左上原点
    var contentSize: CGSize = .zero
    var screenshots: [String] = []
    var monitorHits: [String: Int] = [:]
    var monitor: Any?
    var eventNumber = 0
    var notes: [String] = []

    init(repoRoot: String, outDir: String, phase: String) {
        self.repoRoot = repoRoot
        self.outDir = outDir
        self.phase = phase
        self.window = makeWindow(NSSize(width: 1280, height: 800), title: "拼豆图纸", light: true)
        self.vm = AppViewModel()
        self.synthetic = makeSyntheticImage(width: 600, height: 450)
    }

    func setUp() throws {
        window.contentView = NSHostingView(rootView: ContentView(vm: vm))
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        spin(0.4)
        contentSize = window.contentView?.bounds.size ?? .zero
        notes.append("window_content=\(Int(contentSize.width))x\(Int(contentSize.height))")

        vm.imagePath = repoRoot + "/qa/ui/assets/source_eagle.png"
        vm.chartImage = synthetic
        vm.finishedImage = nil
        vm.fitToWindow = true
        vm.zoom = 100
        vm.offset = .zero

        let ok = waitUntil(10) { [weak self] in
            guard let self, let rep = try? snapshotContent(self.window, to: nil) else { return false }
            return PixelAnalysis(rep).count(matching: isMagenta) > 2000
        }
        guard ok else { throw ProbeError.message("注入后未渲染出预览图（chartImage 未显示）") }
        spin(0.3)
        viewport = vm.previewGeo
        guard viewport.width > 100, viewport.height > 100 else {
            throw ProbeError.message("previewGeo 未就绪: \(viewport)")
        }
        let rep = try snapshotContent(window, to: nil)
        let pa = PixelAnalysis(rep)
        guard let bb = pa.bbox(matching: isMagenta) else {
            throw ProbeError.message("参考态未测到洋红图")
        }
        let b = pa.points(bb)
        refCenter = CGPoint(x: b.midX, y: b.midY)
        if b.width < 0.9 * min(viewport.width, imgW) {
            notes.append("WARN 参考态疑似被裁剪: bbox=\(fmt(b))")
        }
        notes.append("viewport=\(fmt(viewport)) refCenter=\(fmt(refCenter))")
        installMonitor()
    }

    func installMonitor() {
        monitor = NSEvent.addLocalMonitorForEvents(
            matching: [.scrollWheel, .magnify, .keyDown, .leftMouseDown, .leftMouseDragged, .leftMouseUp]
        ) { [weak self] e in
            guard let self else { return e }
            self.monitorHits[Self.eventName(e.type), default: 0] += 1
            return e
        }
    }

    static func eventName(_ t: NSEvent.EventType) -> String {
        switch t {
        case .scrollWheel: return "scrollWheel"
        case .magnify: return "magnify"
        case .keyDown: return "keyDown"
        case .leftMouseDown: return "leftMouseDown"
        case .leftMouseDragged: return "leftMouseDragged"
        case .leftMouseUp: return "leftMouseUp"
        default: return "type\(t.rawValue)"
        }
    }

    func apply(_ s: RenderState) {
        vm.fitToWindow = s.fit
        vm.zoom = s.zoom
        vm.offset = s.offset
        spin(0.38)
    }

    func capture(_ name: String) throws -> PixelAnalysis {
        let path = outDir + "/\(phase)_\(name).png"
        let rep = try snapshotContent(window, to: path)
        screenshots.append(path)
        return PixelAnalysis(rep)
    }

    /// 独立计算期望几何（不调用产品 previewSize / PreviewViewport）。
    /// plateRect：预览图实际被裁剪的边界 = GeometryReader(viewport) 外扩 padding(16)。
    func expectedGeometry(for s: RenderState) -> (scale: CGFloat, display: CGSize, center: CGPoint,
                                                  displayRect: CGRect, viewportRect: CGRect,
                                                  plateRect: CGRect) {
        let scale: CGFloat = s.fit
            ? min(viewport.width / imgW, viewport.height / imgH)
            : CGFloat(s.zoom) / 100.0
        let display = CGSize(width: imgW * scale, height: imgH * scale)
        let center = CGPoint(x: refCenter.x + s.offset.width, y: refCenter.y + s.offset.height)
        let displayRect = CGRect(x: center.x - display.width / 2, y: center.y - display.height / 2,
                                 width: display.width, height: display.height)
        let vpRect = CGRect(x: refCenter.x - viewport.width / 2,
                            y: refCenter.y - viewport.height / 2,
                            width: viewport.width, height: viewport.height)
        let plateRect = vpRect.insetBy(dx: -16, dy: -16)
        return (scale, display, center, displayRect, vpRect, plateRect)
    }

    /// CGRect → JSON 安全值（CGRect.null 的无限值不能进 JSON）
    func finiteRectJSON(_ r: CGRect) -> Any {
        guard !r.isNull, !r.isInfinite,
              r.origin.x.isFinite, r.origin.y.isFinite,
              r.size.width.isFinite, r.size.height.isFinite else { return NSNull() }
        return arr(r)
    }

    func measure(_ s: RenderState) throws -> [String: Any] {
        apply(s)
        let pa = try capture(s.name)
        let (scale, display, center, displayRect, vpRect, plateRect) = expectedGeometry(for: s)
        let expectedVisible = displayRect.intersection(plateRect)
        let visibleFinite = !expectedVisible.isNull && !expectedVisible.isInfinite
        let measuredBB = pa.bbox(matching: isMagenta).map { pa.points($0) }
        let marker = markerMeasurement(pa: pa, expectedCenter: center, scale: scale)

        var result: [String: Any] = [
            "state": s.name,
            "fit_to_window": s.fit,
            "zoom": s.zoom,
            "offset": [Double(s.offset.width), Double(s.offset.height)],
            "expected_scale": Double(scale),
            "expected_display_points": arr(display),
            "expected_center_points": arr(center),
            "expected_plate_rect": finiteRectJSON(plateRect),
            "expected_visible_rect": finiteRectJSON(expectedVisible),
            "clipped": visibleFinite ? expectedVisible != displayRect : true,
            "measured_bbox_points": measuredBB.map { arr($0) } ?? NSNull(),
            "visible_magenta_px": pa.count(matching: isMagenta),
            "screenshot": screenshots.last ?? "",
        ]
        if let m = measuredBB, visibleFinite {
            let err = CGRect(x: m.origin.x - expectedVisible.origin.x,
                             y: m.origin.y - expectedVisible.origin.y,
                             width: m.width - expectedVisible.width,
                             height: m.height - expectedVisible.height)
            result["bbox_error_points"] = arr(err)
            result["measured_center_points"] = arr(CGPoint(x: m.midX, y: m.midY))
            result["measured_size_points"] = [Double(m.width), Double(m.height)]
            let centerDelta = CGPoint(x: m.midX - refCenter.x, y: m.midY - refCenter.y)
            result["measured_offset_from_ref"] = arr(centerDelta)
        } else {
            result["bbox_error_points"] = NSNull()
            result["measured_center_points"] = measuredBB.map { arr(CGPoint(x: $0.midX, y: $0.midY)) } ?? NSNull()
            result["measured_size_points"] = measuredBB.map { [Double($0.width), Double($0.height)] } ?? NSNull()
            result["measured_offset_from_ref"] = measuredBB.map {
                arr(CGPoint(x: $0.midX - refCenter.x, y: $0.midY - refCenter.y))
            } ?? NSNull()
        }
        if let marker { result["center_marker"] = marker }
        return result
    }

    /// 图像中心 4×4 青色标记 → 实际渲染缩放（在裁剪态也能测）
    func markerMeasurement(pa: PixelAnalysis, expectedCenter: CGPoint, scale: CGFloat) -> [String: Any]? {
        guard scale >= 0.75 else { return nil }
        let r = max(30.0, 10.0 / scale)
        let x0 = max(0, Int((expectedCenter.x - r) * pa.scale))
        let x1 = min(pa.pxW, Int((expectedCenter.x + r) * pa.scale))
        let y0 = max(0, Int((expectedCenter.y - r) * pa.scale))
        let y1 = min(pa.pxH, Int((expectedCenter.y + r) * pa.scale))
        guard x0 < x1, y0 < y1,
              let bb = pa.bbox(matching: isCyan, xRange: x0..<x1, yRange: y0..<y1) else { return nil }
        let b = pa.points(bb)
        return [
            "size_points": arr(b.size),
            "center_points": arr(CGPoint(x: b.midX, y: b.midY)),
            "scale_from_marker": Double(b.width / 4.0),
            "expected_center": arr(expectedCenter),
            "center_error": arr(CGPoint(x: b.midX - expectedCenter.x, y: b.midY - expectedCenter.y)),
        ]
    }
}

// MARK: - 渲染阶段

enum RenderProbe {
    static let states: [RenderState] = [
        RenderState(name: "01_fit_default", fit: true, zoom: 100, offset: .zero),
        RenderState(name: "02_zoom_25", fit: false, zoom: 25, offset: .zero),
        RenderState(name: "03_zoom_50", fit: false, zoom: 50, offset: .zero),
        RenderState(name: "04_zoom_100", fit: false, zoom: 100, offset: .zero),
        RenderState(name: "05_zoom_200", fit: false, zoom: 200, offset: .zero),
        RenderState(name: "06_zoom_400", fit: false, zoom: 400, offset: .zero),
        RenderState(name: "07_offset_zoom50_80_60", fit: false, zoom: 50,
                    offset: CGSize(width: 80, height: 60)),
        RenderState(name: "08_offset_zoom200_50_30", fit: false, zoom: 200,
                    offset: CGSize(width: 50, height: 30)),
        RenderState(name: "09_extreme_offset_zoom50", fit: false, zoom: 50,
                    offset: CGSize(width: 9999, height: 9999)),
        RenderState(name: "10_fit_restored", fit: true, zoom: 100, offset: .zero),
    ]

    @MainActor
    static func run(_ s: ProbeSession) throws -> [String: Any] {
        var rows: [[String: Any]] = []
        for st in states {
            let row = try s.measure(st)
            rows.append(row)
            plog("RENDER state=\(st.name) done")
            let m = row["measured_size_points"].flatMap { $0 as? [Double] } ?? []
            let e = row["expected_display_points"] as? [Double] ?? []
            let err = row["bbox_error_points"] as? [Double] ?? []
            print(String(format: "STATE %-26@ expected=%@ measured=%@ err=%@",
                         st.name as NSString,
                         String(format: "%.1fx%.1f", e.first ?? 0, e.last ?? 0),
                         String(format: "%.1fx%.1f", m.first ?? 0, m.last ?? 0),
                         err.map { String(format: "%.1f", $0) }.joined(separator: ",")))
        }
        return ["states": rows, "screenshots": s.screenshots, "notes": s.notes]
    }
}
