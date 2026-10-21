import AppKit
import SwiftUI

// ============================================================================
// T9 主题取证：真实 ContentView / 特效画廊 / 色卡在亮暗双主题下的截图，
// 以及渲染后的关键平色采样（纸底/面板底），供报告做像素级核对。
// ============================================================================

enum ThemeProbe {
    /// 读取真实图纸并按产品逻辑 ≤2048 降采样（不画标记，用于主题截图）
    @MainActor
    static func loadChart(_ path: String) throws -> NSImage {
        guard let src = NSImage(contentsOfFile: path) else {
            throw ProbeError.message("无法读取图纸: \(path)")
        }
        var size = src.size
        let maxDim: CGFloat = 2048
        if max(size.width, size.height) > maxDim {
            let s = maxDim / max(size.width, size.height)
            size = CGSize(width: size.width * s, height: size.height * s)
        }
        let out = NSImage(size: size)
        out.lockFocus()
        src.draw(in: NSRect(origin: .zero, size: size))
        out.unlockFocus()
        return out
    }

    struct Shot {
        let path: String
        let paperSample: String
        let panelSample: String
    }

    @MainActor
    static func shoot(_ window: NSWindow, to path: String, samples: [CGPoint]) throws -> Shot {
        let rep = try snapshotContent(window, to: path)
        let pa = PixelAnalysis(rep)
        let colors = samples.map { pa.colorAtPoint($0).hex }
        return Shot(path: path,
                    paperSample: colors.first ?? "n/a",
                    panelSample: colors.count > 1 ? colors[1] : "n/a")
    }

    @MainActor
    static func run(repoRoot: String, outDir: String) throws -> [String: Any] {
        var out: [String: Any] = [:]
        var shots: [[String: String]] = []
        let chartPath = repoRoot + "/qa/ui/assets/eagle_chart.png"
        let chart = try loadChart(chartPath)

        // ---------- 1. 开始页（封面空状态 + hero） ----------
        let coverVM = AppViewModel()
        let cover = makeWindow(NSSize(width: 1280, height: 800), title: "拼豆图纸", light: true)
        cover.contentView = NSHostingView(rootView: ContentView(vm: coverVM))
        cover.center()
        cover.makeKeyAndOrderFront(nil)
        spin(0.8)
        let coverReady = waitUntil(25) {
            !coverVM.templates.isEmpty || coverVM.statusText.contains("失败")
        }
        spin(0.8)
        let s1 = try shoot(cover, to: outDir + "/theme_cover_light_1280x800.png",
                           samples: [CGPoint(x: 6, y: 6), CGPoint(x: 6, y: cover.boundsHeight - 8)])
        shots.append(["name": "cover_light_1280x800", "path": s1.path,
                      "paper": s1.paperSample, "statusbar": s1.panelSample])
        cover.setContentSize(NSSize(width: 1440, height: 900))
        spin(0.9)
        let s2 = try shoot(cover, to: outDir + "/theme_cover_light_1440x900.png",
                           samples: [CGPoint(x: 6, y: 6), CGPoint(x: 6, y: cover.boundsHeight - 8)])
        shots.append(["name": "cover_light_1440x900", "path": s2.path,
                      "paper": s2.paperSample, "statusbar": s2.panelSample])
        cover.appearance = NSAppearance(named: .darkAqua)
        spin(1.0)
        let s3 = try shoot(cover, to: outDir + "/theme_cover_dark_1440x900.png",
                           samples: [CGPoint(x: 6, y: 6), CGPoint(x: 6, y: cover.boundsHeight - 8)])
        shots.append(["name": "cover_dark_1440x900", "path": s3.path,
                      "paper": s3.paperSample, "statusbar": s3.panelSample])
        cover.setContentSize(NSSize(width: 1280, height: 800))
        spin(0.9)
        let s4 = try shoot(cover, to: outDir + "/theme_cover_dark_1280x800.png",
                           samples: [CGPoint(x: 6, y: 6), CGPoint(x: 6, y: cover.boundsHeight - 8)])
        shots.append(["name": "cover_dark_1280x800", "path": s4.path,
                      "paper": s4.paperSample, "statusbar": s4.panelSample])
        out["cover"] = [
            "templates": coverVM.templates.count,
            "palettes": coverVM.palettes.count,
            "status": coverVM.statusText,
            "ready": coverReady,
        ]
        cover.close()

        // ---------- 2. 工作台（真实图纸内容）亮 / 暗 ----------
        let wbVM = AppViewModel()
        let wb = makeWindow(NSSize(width: 1280, height: 800), title: "拼豆图纸", light: true)
        wb.contentView = NSHostingView(rootView: ContentView(vm: wbVM))
        wb.center()
        wb.makeKeyAndOrderFront(nil)
        spin(0.5)
        wbVM.imagePath = repoRoot + "/qa/ui/assets/source_eagle.png"
        wbVM.chartImage = chart
        wbVM.fitToWindow = true
        wbVM.zoom = 100
        wbVM.offset = .zero
        spin(1.2)
        let w1 = try shoot(wb, to: outDir + "/theme_workbench_light_1280x800.png",
                           samples: [CGPoint(x: 6, y: 6), CGPoint(x: 290, y: 120)])
        shots.append(["name": "workbench_light_1280x800", "path": w1.path,
                      "paper": w1.paperSample, "sidebar": w1.panelSample])
        wb.appearance = NSAppearance(named: .darkAqua)
        spin(1.2)
        let w2 = try shoot(wb, to: outDir + "/theme_workbench_dark_1280x800.png",
                           samples: [CGPoint(x: 6, y: 6), CGPoint(x: 290, y: 120)])
        shots.append(["name": "workbench_dark_1280x800", "path": w2.path,
                      "paper": w2.paperSample, "sidebar": w2.panelSample])
        wb.close()

        // ---------- 3. 特效画廊 ----------
        let gVM = AppViewModel()
        gVM.imagePath = repoRoot + "/qa/ui/assets/source_eagle.png"
        gVM.chartImage = chart
        let gallery = makeWindow(NSSize(width: 1180, height: 780), title: "特效画廊", light: true)
        gallery.contentView = NSHostingView(rootView: EffectsGalleryView(vm: gVM, onApply: {}))
        gallery.center()
        gallery.makeKeyAndOrderFront(nil)
        spin(1.4)
        let g1 = try shoot(gallery, to: outDir + "/theme_gallery_light.png",
                           samples: [CGPoint(x: 6, y: 6), CGPoint(x: 8, y: gallery.boundsHeight - 8)])
        shots.append(["name": "gallery_light", "path": g1.path,
                      "paper": g1.paperSample, "bottom": g1.panelSample])
        gallery.appearance = NSAppearance(named: .darkAqua)
        spin(1.2)
        let g2 = try shoot(gallery, to: outDir + "/theme_gallery_dark.png",
                           samples: [CGPoint(x: 6, y: 6), CGPoint(x: 8, y: gallery.boundsHeight - 8)])
        shots.append(["name": "gallery_dark", "path": g2.path,
                      "paper": g2.paperSample, "bottom": g2.panelSample])
        gallery.close()

        // ---------- 4. 色卡 ----------
        let cVM = AppViewModel()
        cVM.setup()
        let ok = waitUntil(25) { !cVM.palettes.isEmpty && cVM.engine != nil }
        spin(0.5)
        let chartWin = makeWindow(NSSize(width: 1200, height: 800), title: "色卡", light: true)
        chartWin.contentView = NSHostingView(
            rootView: ColorChartView(paletteInternal: cVM.paletteInternal,
                                     paletteDisplay: cVM.paletteDisplay,
                                     engine: cVM.engine))
        chartWin.center()
        chartWin.makeKeyAndOrderFront(nil)
        spin(3.0)
        let c1 = try shoot(chartWin, to: outDir + "/theme_colorschart_light.png",
                           samples: [CGPoint(x: 6, y: 6), CGPoint(x: cVM.engine == nil ? 6 : 8,
                                                                  y: chartWin.boundsHeight - 8)])
        shots.append(["name": "colorschart_light", "path": c1.path,
                      "paper": c1.paperSample, "bottom": c1.panelSample])
        chartWin.appearance = NSAppearance(named: .darkAqua)
        spin(1.5)
        let c2 = try shoot(chartWin, to: outDir + "/theme_colorschart_dark.png",
                           samples: [CGPoint(x: 6, y: 6), CGPoint(x: 8, y: chartWin.boundsHeight - 8)])
        shots.append(["name": "colorschart_dark", "path": c2.path,
                      "paper": c2.paperSample, "bottom": c2.panelSample])
        chartWin.close()

        out["engine_ready"] = ok
        out["palettes"] = cVM.palettes.count
        out["shots"] = shots
        out["hero_asset_exists"] = FileManager.default.fileExists(
            atPath: repoRoot + "/app/Sources/PerlerApp/Resources/hero_photo_to_beads.jpg")
        return out
    }
}

private extension NSWindow {
    var boundsHeight: CGFloat { contentView?.bounds.height ?? frame.height }
}
