import AppKit
import SwiftUI

// ============================================================================
// 真实图纸渲染测量：用真实引擎产物（qa/ui/assets/eagle_chart.png，60×60 网格）
// 按产品的 ≤2048 降采样逻辑注入 chartImage，并在图像中心叠加 12×12 唯一色标记，
// 用该标记的渲染尺寸/位置反算实际显示比例与偏移（不依赖产品内部函数）。
// 同时输出真实内容态截图（供视觉走查/主题验证）。
// ============================================================================

enum RealChartProbe {
    struct MarkedChart {
        let image: NSImage
        let marker: RGB
        let markerPx: CGFloat
        let baseSize: CGSize
        let downsampled: Bool
    }

    /// 复刻产品 loadPreviewImage：≤2048 降采样；再在中心画 12×12 标记
    @MainActor
    static func makeMarkedChart(sourcePath: String) throws -> MarkedChart {
        guard let src = NSImage(contentsOfFile: sourcePath) else {
            throw ProbeError.message("无法读取真实图纸: \(sourcePath)")
        }
        var baseSize = src.size
        let maxDim: CGFloat = 2048
        var scale: CGFloat = 1
        if max(baseSize.width, baseSize.height) > maxDim {
            scale = maxDim / max(baseSize.width, baseSize.height)
            baseSize = CGSize(width: baseSize.width * scale, height: baseSize.height * scale)
        }
        let out = NSImage(size: baseSize)
        out.lockFocus()
        src.draw(in: NSRect(origin: .zero, size: baseSize))
        out.unlockFocus()

        guard let tiff = out.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff) else {
            throw ProbeError.message("图纸位图化失败")
        }
        let pa = PixelAnalysis(rep)
        let candidates: [RGB] = [
            RGB(255, 0, 255), RGB(0, 255, 255), RGB(0, 128, 255),
            RGB(0, 255, 0), RGB(255, 0, 0), RGB(255, 255, 0),
            RGB(128, 0, 255), RGB(255, 128, 0),
        ]
        var chosen = candidates[0]
        var chosenCount = -1
        for cand in candidates {
            let count = pa.count(matching: { $0.distance(to: cand) < 10 })
            if count == 0 { chosen = cand; chosenCount = 0; break }
        }
        if chosenCount != 0 {
            throw ProbeError.message("图纸中未找到唯一标记色（全部候选均出现）")
        }

        let markerPx: CGFloat = 12
        let marked = NSImage(size: baseSize)
        marked.lockFocus()
        out.draw(in: NSRect(origin: .zero, size: baseSize))
        NSColor(srgbRed: chosen.r / 255, green: chosen.g / 255,
                blue: chosen.b / 255, alpha: 1).setFill()
        NSRect(x: baseSize.width / 2 - markerPx / 2,
               y: baseSize.height / 2 - markerPx / 2,
               width: markerPx, height: markerPx).fill()
        marked.unlockFocus()
        return MarkedChart(image: marked, marker: chosen, markerPx: markerPx,
                           baseSize: baseSize, downsampled: scale < 1)
    }

    @MainActor
    static func run(_ s: ProbeSession) throws -> [String: Any] {
        let chartPath = s.repoRoot + "/qa/ui/assets/eagle_chart.png"
        let marked = try makeMarkedChart(sourcePath: chartPath)
        let markerPred: (RGB) -> Bool = { $0.distance(to: marked.marker) < 14 }
        s.vm.chartImage = marked.image
        s.vm.finishedImage = nil
        s.vm.fitToWindow = true
        s.vm.zoom = 100
        s.vm.offset = .zero
        spin(0.5)

        let states: [(String, Bool, Double, CGSize)] = [
            ("01_fit", true, 100, .zero),
            ("02_zoom_25", false, 25, .zero),
            ("03_zoom_50", false, 50, .zero),
            ("04_zoom_100", false, 100, .zero),
            ("05_zoom_50_offset_40_30", false, 50, CGSize(width: 40, height: 30)),
        ]
        var rows: [[String: Any]] = []
        let screenshots = s.screenshots
        for (name, fit, zoom, offset) in states {
            s.vm.fitToWindow = fit
            s.vm.zoom = zoom
            s.vm.offset = offset
            spin(0.42)
            let path = s.outDir + "/\(s.phase)_real_\(name).png"
            let rep = try snapshotContent(s.window, to: path)
            s.screenshots.append(path)
            let pa = PixelAnalysis(rep)
            let vp = s.viewport
            let imgSize = marked.baseSize
            let expScale: CGFloat = fit
                ? min(vp.width / imgSize.width, vp.height / imgSize.height)
                : CGFloat(zoom) / 100.0
            let expMarker = marked.markerPx * expScale
            let expCenter = CGPoint(x: s.refCenter.x + offset.width,
                                    y: s.refCenter.y + offset.height)
            // 标记检测限制在 plate 区域内（避免其它 UI 同色干扰）
            let x0 = max(0, Int((s.refCenter.x - vp.width / 2 - 20) * pa.scale))
            let x1 = min(pa.pxW, Int((s.refCenter.x + vp.width / 2 + 20) * pa.scale))
            let y0 = max(0, Int((s.refCenter.y - vp.height / 2 - 20) * pa.scale))
            let y1 = min(pa.pxH, Int((s.refCenter.y + vp.height / 2 + 20) * pa.scale))
            let bb = (x0 < x1 && y0 < y1)
                ? pa.bbox(matching: markerPred, xRange: x0..<x1, yRange: y0..<y1)
                : nil
            var row: [String: Any] = [
                "state": name,
                "fit_to_window": fit,
                "zoom": zoom,
                "offset": [Double(offset.width), Double(offset.height)],
                "base_image_points": arr(imgSize),
                "downsampled_from_original": marked.downsampled,
                "expected_scale": Double(expScale),
                "expected_marker_points": Double(expMarker),
                "expected_center_points": arr(expCenter),
                "product_preview_size_points": arr(s.vm.previewSize(img: marked.image)),
                "screenshot": path,
            ]
            if let bb {
                let b = pa.points(bb)
                row["measured_marker_points"] = arr(b.size)
                row["measured_marker_center"] = arr(CGPoint(x: b.midX, y: b.midY))
                row["measured_scale_from_marker"] = Double(b.width / marked.markerPx)
                row["center_error"] = arr(CGPoint(x: b.midX - expCenter.x,
                                                  y: b.midY - expCenter.y))
            } else {
                row["measured_marker_points"] = NSNull()
                row["measured_marker_center"] = NSNull()
                row["measured_scale_from_marker"] = NSNull()
                row["center_error"] = NSNull()
            }
            rows.append(row)
            plog("REAL state=\(name) done")
            let ms = (row["measured_scale_from_marker"] as? Double) ?? -1
            print(String(format: "REAL %-24@ fit=%@ expected_scale=%.4f measured_scale=%.4f",
                         name as NSString, fit ? "Y" : "N", Double(expScale), ms))
        }
        s.vm.chartImage = s.synthetic
        s.vm.fitToWindow = true
        s.vm.offset = .zero
        spin(0.35)
        _ = screenshots
        return [
            "chart_source": chartPath,
            "marker_color": marked.marker.hex,
            "marker_px": Double(marked.markerPx),
            "states": rows,
            "note": "fit 状态的真实图纸显示比例 = min(视口/图) ≈ 20.7%（<25% 时产品若对百分比做 25 下限钳制，标签会失真，见代码审计）",
        ]
    }
}
