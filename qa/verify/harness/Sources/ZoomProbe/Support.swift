import AppKit
import SwiftUI

// ============================================================================
// 独立验证探针公共设施（只读产品源码，不改产品代码）
// 用途：离屏创建真实 ContentView + 注入已驱动 AppViewModel；截图 + 像素测量；
//       合成 NSEvent 验证滚轮/键盘/拖拽事件接线。
// 说明：整个探针以「同步 + 手动跑主 RunLoop / 手动派发事件」执行，避免
//       SwiftUI + Swift Concurrency 在离屏 harness 中的调度不确定性。
// ============================================================================

enum ProbeError: LocalizedError {
    case message(String)
    var errorDescription: String? {
        if case .message(let m) = self { return m }
        return nil
    }
}

func plog(_ msg: String) {
    let t = Date().timeIntervalSince1970
    let line = "[" + String(format: "%.1f", t) + "] " + msg + "\u{0A}"
    FileHandle.standardError.write(line.data(using: .utf8)!)
}

/// 驱动主 RunLoop 若干秒 + 手动派发 NSApp 事件（app.run() 未启动时使用）
@MainActor
func spin(_ seconds: Double) {
    let end = Date().addingTimeInterval(seconds)
    repeat {
        _ = RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.02))
        drainEvents()
    } while Date() < end
}

@MainActor
func drainEvents() {
    var guardCount = 0
    while let ev = NSApp.nextEvent(matching: .any, until: Date(),
                                   inMode: .default, dequeue: true) {
        NSApp.sendEvent(ev)
        guardCount += 1
        if guardCount > 500 { break }
    }
}

@MainActor
func waitUntil(_ timeout: Double, _ cond: () -> Bool) -> Bool {
    let end = Date().addingTimeInterval(timeout)
    while Date() < end {
        if cond() { return true }
        spin(0.05)
    }
    return cond()
}

func writePNG(_ rep: NSBitmapImageRep, to path: String) throws {
    guard let data = rep.representation(using: .png, properties: [:]) else {
        throw ProbeError.message("PNG 编码失败: \(path)")
    }
    try data.write(to: URL(fileURLWithPath: path))
}

/// 截取窗口 contentView（SwiftUI + AppKit 混合），返回位图（scale 像素/点）
@MainActor
@discardableResult
func snapshotContent(_ window: NSWindow, to path: String?, scale: CGFloat = 2) throws -> NSBitmapImageRep {
    guard let view = window.contentView else { throw ProbeError.message("窗口没有 contentView") }
    view.layoutSubtreeIfNeeded()
    let bounds = view.bounds
    guard bounds.width > 10, bounds.height > 10,
          let rep = NSBitmapImageRep(bitmapDataPlanes: nil,
                                     pixelsWide: Int(bounds.width * scale),
                                     pixelsHigh: Int(bounds.height * scale),
                                     bitsPerSample: 8, samplesPerPixel: 4,
                                     hasAlpha: true, isPlanar: false,
                                     colorSpaceName: .deviceRGB,
                                     bytesPerRow: 0, bitsPerPixel: 0) else {
        throw ProbeError.message("位图创建失败")
    }
    rep.size = bounds.size
    view.cacheDisplay(in: bounds, to: rep)
    if let path { try writePNG(rep, to: path) }
    return rep
}

@MainActor
func makeWindow(_ size: NSSize, title: String, light: Bool) -> NSWindow {
    let w = NSWindow(contentRect: NSRect(origin: NSPoint(x: 160, y: 120), size: size),
                     styleMask: [.titled, .closable, .resizable, .miniaturizable],
                     backing: .buffered, defer: false)
    w.title = title
    w.appearance = NSAppearance(named: light ? .aqua : .darkAqua)
    w.isReleasedWhenClosed = false
    return w
}

// MARK: - 颜色

struct RGB: Equatable, CustomStringConvertible {
    var r: Double   // 0...255
    var g: Double
    var b: Double

    init(_ r: Double, _ g: Double, _ b: Double) { self.r = r; self.g = g; self.b = b }

    init(hex: UInt32) {
        self.r = Double((hex >> 16) & 0xFF)
        self.g = Double((hex >> 8) & 0xFF)
        self.b = Double(hex & 0xFF)
    }

    var description: String { hex }

    var hex: String {
        String(format: "#%02X%02X%02X", Int(r.rounded()), Int(g.rounded()), Int(b.rounded()))
    }

    var hsv: (h: Double, s: Double, v: Double) {
        let rr = r / 255, gg = g / 255, bb = b / 255
        let mx = max(rr, gg, bb), mn = min(rr, gg, bb)
        let d = mx - mn
        var h: Double = 0
        if d > 0.00001 {
            if mx == rr { h = 60 * ((gg - bb) / d).truncatingRemainder(dividingBy: 6) }
            else if mx == gg { h = 60 * ((bb - rr) / d + 2) }
            else { h = 60 * ((rr - gg) / d + 4) }
        }
        if h < 0 { h += 360 }
        let s = mx <= 0 ? 0 : d / mx
        return (h, s, mx)
    }

    func distance(to o: RGB) -> Double {
        let dr = r - o.r, dg = g - o.g, db = b - o.b
        return (dr * dr + dg * dg + db * db).squareRoot()
    }
}

/// WCAG 相对亮度与对比度
func relativeLuminance(_ c: RGB) -> Double {
    func ch(_ v: Double) -> Double {
        let s = v / 255
        return s <= 0.03928 ? s / 12.92 : pow((s + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * ch(c.r) + 0.7152 * ch(c.g) + 0.0722 * ch(c.b)
}

func contrastRatio(_ a: RGB, _ b: RGB) -> Double {
    let la = relativeLuminance(a), lb = relativeLuminance(b)
    let hi = max(la, lb), lo = min(la, lb)
    return (hi + 0.05) / (lo + 0.05)
}

// MARK: - 像素分析（基于位图原始数据，快；与 colorAt 抽样校验）

struct PixelAnalysis {
    let rep: NSBitmapImageRep
    let scale: CGFloat
    let pxW: Int
    let pxH: Int
    private let bytes: UnsafeMutablePointer<UInt8>
    private let bpr: Int
    private let spp: Int

    init(_ rep: NSBitmapImageRep) {
        self.rep = rep
        self.scale = rep.size.width > 0 ? CGFloat(rep.pixelsWide) / rep.size.width : 2
        self.pxW = rep.pixelsWide
        self.pxH = rep.pixelsHigh
        guard let data = rep.bitmapData else { fatalError("bitmapData 为空") }
        self.bytes = data
        self.bpr = rep.bytesPerRow
        self.spp = rep.samplesPerPixel
    }

    func colorAt(px x: Int, _ y: Int) -> RGB {
        let i = y * bpr + x * spp
        return RGB(Double(bytes[i]), Double(bytes[i + 1]), Double(bytes[i + 2]))
    }

    func colorAtPoint(_ p: CGPoint) -> RGB {
        let x = min(pxW - 1, max(0, Int(p.x * scale)))
        let y = min(pxH - 1, max(0, Int(p.y * scale)))
        return colorAt(px: x, y)
    }

    /// 单次扫描同时得到 count 与包围盒（设备像素坐标，左上原点）
    func stats(matching pred: (RGB) -> Bool,
               xRange: Range<Int>? = nil, yRange: Range<Int>? = nil) -> (count: Int, bbox: CGRect?) {
        let x0 = max(0, xRange?.lowerBound ?? 0), x1 = min(pxW, xRange?.upperBound ?? pxW)
        let y0 = max(0, yRange?.lowerBound ?? 0), y1 = min(pxH, yRange?.upperBound ?? pxH)
        guard x1 > x0, y1 > y0 else { return (0, nil) }
        var minX = Int.max, minY = Int.max, maxX = Int.min, maxY = Int.min
        var count = 0
        for y in y0..<y1 {
            let row = y * bpr
            for x in x0..<x1 {
                let i = row + x * spp
                let c = RGB(Double(bytes[i]), Double(bytes[i + 1]), Double(bytes[i + 2]))
                if pred(c) {
                    count += 1
                    if x < minX { minX = x }
                    if x > maxX { maxX = x }
                    if y < minY { minY = y }
                    if y > maxY { maxY = y }
                }
            }
        }
        guard count > 0 else { return (0, nil) }
        return (count, CGRect(x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1))
    }

    func bbox(matching pred: (RGB) -> Bool,
              xRange: Range<Int>? = nil, yRange: Range<Int>? = nil) -> CGRect? {
        stats(matching: pred, xRange: xRange, yRange: yRange).bbox
    }

    func count(matching pred: (RGB) -> Bool,
               xRange: Range<Int>? = nil, yRange: Range<Int>? = nil) -> Int {
        stats(matching: pred, xRange: xRange, yRange: yRange).count
    }

    /// 设备像素矩形 → 点矩形（左上原点）
    func points(_ px: CGRect) -> CGRect {
        CGRect(x: px.origin.x / scale, y: px.origin.y / scale,
               width: px.size.width / scale, height: px.size.height / scale)
    }
}

// MARK: - 合成图（纯洋红 + 中心 4×4 青色标记：用于精确测量实际渲染尺寸）

@MainActor
func makeSyntheticImage(width: Int, height: Int) -> NSImage {
    let size = NSSize(width: width, height: height)
    let img = NSImage(size: size)
    img.lockFocus()
    NSColor(srgbRed: 1.0, green: 0.0, blue: 1.0, alpha: 1.0).setFill()
    NSRect(origin: .zero, size: size).fill()
    NSColor(srgbRed: 0, green: 1, blue: 1, alpha: 1).setFill()
    // 中心 4×4 标记（图像中心映射到显示中心，裁剪态也能测缩放）
    NSRect(x: CGFloat(width) / 2 - 2, y: CGFloat(height) / 2 - 2, width: 4, height: 4).fill()
    // 左上角 6×6 标记（判断方向）
    NSRect(x: 0, y: CGFloat(height) - 6, width: 6, height: 6).fill()
    img.unlockFocus()
    return img
}

func isMagenta(_ c: RGB) -> Bool { c.r > 200 && c.g < 80 && c.b > 200 }
func isCyan(_ c: RGB) -> Bool { c.r < 80 && c.g > 200 && c.b > 200 }

func isNear(_ c: RGB, _ hex: UInt32, tolerance: Double = 5) -> Bool {
    let t = RGB(hex: hex)
    return abs(c.r - t.r) <= tolerance && abs(c.g - t.g) <= tolerance && abs(c.b - t.b) <= tolerance
}

// MARK: - JSON 输出

func writeJSON(_ obj: Any, to path: String) throws {
    let data = try JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: URL(fileURLWithPath: path))
}

func ensureDir(_ path: String) throws {
    try FileManager.default.createDirectory(atPath: path, withIntermediateDirectories: true)
}

func repoRootFromEnv() -> String {
    ProcessInfo.processInfo.environment["PERLER_REPO_ROOT"]
        ?? FileManager.default.currentDirectoryPath
}

// MARK: - 数组化 JSON 值

func arr(_ p: CGPoint) -> [Double] { [Double(p.x), Double(p.y)] }
func arr(_ s: CGSize) -> [Double] { [Double(s.width), Double(s.height)] }
func arr(_ r: CGRect) -> [Double] { [Double(r.origin.x), Double(r.origin.y), Double(r.width), Double(r.height)] }
func fmt(_ s: CGSize) -> String { String(format: "(%.1f,%.1f)", s.width, s.height) }
func fmt(_ p: CGPoint) -> String { String(format: "(%.1f,%.1f)", p.x, p.y) }
func fmt(_ r: CGRect) -> String { String(format: "(%.1f,%.1f,%.1f,%.1f)", r.origin.x, r.origin.y, r.width, r.height) }
