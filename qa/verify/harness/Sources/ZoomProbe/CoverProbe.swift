import AppKit
import SwiftUI
import Vision

// ============================================================================
// T13 封面改版验证探针（view-verify 独立验证，不改产品代码）
//  - 4 场景截图：1280×800 / 1440×900 × 亮/暗
//  - 像素测量：左侧 hero 图像覆盖率、四边活性（无纸底留白）、是否小图框住、
//    右侧列彩色缩略图残留、caption/scrim 近似对比度、CTA 首屏可见（OCR）
//  - OCR：示例面板文字是否消失、快捷键/输出表文字是否完整（无截断）
//  - 工作台/画廊回归：与 T10 期截图做像素 diff
// ============================================================================

enum CoverProbe {
    struct Scenario {
        let name: String
        let size: CGSize
        let light: Bool
    }

    struct ThemeColors {
        let flats: [RGB]        // 背景平色（纸/面板）
        let paper: RGB
        let dark: Bool
    }

    @MainActor
    static func run(repoRoot: String, outDir: String) throws -> [String: Any] {
        var out: [String: Any] = [:]
        let vm = AppViewModel()
        let window = makeWindow(NSSize(width: 1280, height: 800), title: "拼豆图纸", light: true)
        window.contentView = NSHostingView(rootView: ContentView(vm: vm))
        window.center()
        window.makeKeyAndOrderFront(nil)
        spin(0.8)
        let ready = waitUntil(30) { !vm.palettes.isEmpty || vm.statusText.contains("失败") }
        spin(1.0)
        out["engine_ready"] = ready
        out["status"] = vm.statusText

        let scenarios: [Scenario] = [
            Scenario(name: "1280x800_light", size: CGSize(width: 1280, height: 800), light: true),
            Scenario(name: "1440x900_light", size: CGSize(width: 1440, height: 900), light: true),
            Scenario(name: "1280x800_dark", size: CGSize(width: 1280, height: 800), light: false),
            Scenario(name: "1440x900_dark", size: CGSize(width: 1440, height: 900), light: false),
        ]
        var rows: [[String: Any]] = []
        let screenVisible = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1280, height: 800)
        out["screen_visible_frame"] = [Double(screenVisible.width), Double(screenVisible.height)]
        for sc in scenarios {
            let fitsScreen = sc.size.width <= screenVisible.width
                && sc.size.height <= screenVisible.height - 28
            let path = outDir + "/cover_" + sc.name + ".png"
            var actualSize = sc.size
            var renderMode = "window"
            let rep: NSBitmapImageRep
            if fitsScreen {
                window.appearance = NSAppearance(named: sc.light ? .aqua : .darkAqua)
                window.setContentSize(sc.size)
                spin(1.1)
                actualSize = window.contentView?.bounds.size ?? sc.size
                rep = try snapshotContent(window, to: path)
            } else {
                renderMode = "offscreen_exact_size"
                let offVM = AppViewModel()
                let offView = ContentView(vm: offVM)
                guard let offRep = renderOffscreen(view: offView, size: sc.size, light: sc.light) else {
                    throw ProbeError.message("离屏渲染失败: " + sc.name)
                }
                try writePNG(offRep, to: path)
                rep = offRep
            }
            let pa = PixelAnalysis(rep)
            var row = try measureCover(pa, windowSize: actualSize, light: sc.light)
            row["scenario"] = sc.name
            row["requested_size"] = [Double(sc.size.width), Double(sc.size.height)]
            row["actual_content_size"] = [Double(actualSize.width), Double(actualSize.height)]
            row["render_mode"] = renderMode
            row["screenshot"] = path
            rows.append(row)
            plog("COVER scenario=" + sc.name + " done (" + renderMode + ")")
        }
        out["scenarios"] = rows
        // 以 1280 light 为基准做 OCR 文本检查
        if let rep1280 = try? snapshotContent(window, to: nil) {
            _ = rep1280
        }
        window.setContentSize(NSSize(width: 1280, height: 800))
        window.appearance = NSAppearance(named: .aqua)
        spin(1.0)
        let basePath = outDir + "/cover_1280x800_light.png"
        let baseRep = try snapshotContent(window, to: basePath)
        let ocr = try runOCR(baseRep, windowSize: CGSize(width: 1280, height: 800))
        out["ocr_1280_light"] = ocr.texts.map { ["text": $0.text, "bbox": arr($0.bbox)] }
        out["ocr_texts_flat"] = ocr.texts.map { $0.text }
        // 示例面板 / 彩色缩略图检查
        var checks: [String: Any] = [:]
        let samplePanelKeys = ["示例图版", "示例", "CATALOGUE", "SAMPLES", "内置模板", "四叶草", "小幽灵", "彩虹", "笑脸"]
        checks["sample_panel_texts_found"] = samplePanelKeys.filter { key in
            ocr.texts.contains { $0.text.contains(key) }
        }
        checks["has_ellipsis_truncation"] = ocr.texts.filter { $0.text.contains("…") && !$0.text.contains("选择图片") }.map { $0.text }
        // 右列彩色像素（排除 hero 区）：用于确认无彩色模板缩略图
        let basePA = PixelAnalysis(baseRep)
        let hero = detectHero(pa: basePA, windowSize: CGSize(width: 1280, height: 800), light: true)
        let colorful = countColorfulRightOfHero(pa: basePA, hero: hero,
                                                windowSize: CGSize(width: 1280, height: 800),
                                                light: true)
        checks["colorful_pixels_right_of_hero"] = colorful
        // CTA 可见性：OCR 找「选择图片」
        if let cta = ocr.texts.first(where: { $0.text.contains("选择图片") }) {
            checks["cta_found"] = true
            checks["cta_bbox_points"] = arr(cta.bbox)
            checks["cta_fully_in_first_screen"] = cta.bbox.minY >= 0
                && cta.bbox.maxY <= 800 && cta.bbox.minX >= 0 && cta.bbox.maxX <= 1280
        } else {
            checks["cta_found"] = false
        }
        checks["drag_hint_found"] = ocr.texts.contains { $0.text.contains("拖入") }
        // 快捷键/输出表文字完整性（OCR 命中即代表未被截断到不可读）
        let expectedAlternatives: [[String]] = [
            ["打开图片"], ["生成图纸"], ["缩放", "缩放 / 重置"], ["对比原图"],
            ["PNG"], ["PDF", "A4"], ["色卡"], ["3670"], ["MARD 221"],
        ]
        checks["expected_texts"] = expectedAlternatives.map { alts in
            ["alternatives": alts,
             "found": alts.contains { key in ocr.texts.contains { $0.text.contains(key) } }]
        }
        // 右边界截断检查：文字 bbox 贴近/超出窗口右缘
        let nearRight = ocr.texts.filter { $0.bbox.maxX >= 1280 - 3 }
        checks["texts_near_or_past_right_edge"] = nearRight.map {
            ["text": $0.text, "max_x": Double($0.bbox.maxX)]
        }
        checks["ocr_text_count"] = ocr.texts.count
        out["checks_1280_light"] = checks

        window.close()

        // ---- 工作台 / 画廊回归（对比 T10 期截图） ----
        var regression: [String: Any] = [:]
        let chart = try ThemeProbe.loadChart(repoRoot + "/qa/ui/assets/eagle_chart.png")
        let wbVM = AppViewModel()
        let wb = makeWindow(NSSize(width: 1280, height: 800), title: "拼豆图纸", light: true)
        wb.contentView = NSHostingView(rootView: ContentView(vm: wbVM))
        wb.center()
        wb.makeKeyAndOrderFront(nil)
        spin(0.5)
        wbVM.imagePath = repoRoot + "/qa/ui/assets/source_eagle.png"
        wbVM.chartImage = chart
        wbVM.fitToWindow = true
        spin(1.2)
        let wbPath = outDir + "/cover_regression_workbench_light.png"
        let wbRep = try snapshotContent(wb, to: wbPath)
        regression["workbench_screenshot"] = wbPath
        if let old = try? NSBitmapImageRep(data: Data(contentsOf: URL(
            fileURLWithPath: outDir + "/theme_workbench_light_1280x800.png"))) {
            regression["workbench_diff_vs_T10"] = try diff(repA: wbRep, repB: old)
        }
        regression["workbench_has_image"] = PixelAnalysis(wbRep)
            .count(matching: { $0.r > 150 && $0.g > 150 && $0.b > 150 }) > 10000
        wb.close()

        let gVM = AppViewModel()
        gVM.imagePath = repoRoot + "/qa/ui/assets/source_eagle.png"
        gVM.chartImage = chart
        let gallery = makeWindow(NSSize(width: 1180, height: 780), title: "特效画廊", light: true)
        gallery.contentView = NSHostingView(rootView: EffectsGalleryView(vm: gVM, onApply: {}))
        gallery.center()
        gallery.makeKeyAndOrderFront(nil)
        spin(1.4)
        let gPath = outDir + "/cover_regression_gallery_light.png"
        let gRep = try snapshotContent(gallery, to: gPath)
        regression["gallery_screenshot"] = gPath
        if let old = try? NSBitmapImageRep(data: Data(contentsOf: URL(
            fileURLWithPath: outDir + "/theme_gallery_light.png"))) {
            regression["gallery_diff_vs_T10"] = try diff(repA: gRep, repB: old)
        }
        gallery.close()
        out["regression"] = regression

        return out
    }

    /// 离屏精确尺寸渲染（本机屏幕可见高度 862pt，1440×900 的真实窗口会被系统压到 834pt；
    /// 用 NSHostingView 离屏渲染 1440×900 以验证该尺寸下的布局）
    @MainActor
    static func renderOffscreen(view: ContentView, size: CGSize, light: Bool) -> NSBitmapImageRep? {
        let host = NSHostingView(rootView: view)
        host.appearance = NSAppearance(named: light ? .aqua : .darkAqua)
        host.frame = NSRect(origin: .zero, size: size)
        host.layoutSubtreeIfNeeded()
        spin(0.6)
        host.layoutSubtreeIfNeeded()
        host.display()
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil,
                                         pixelsWide: Int(size.width * 2),
                                         pixelsHigh: Int(size.height * 2),
                                         bitsPerSample: 8, samplesPerPixel: 4,
                                         hasAlpha: true, isPlanar: false,
                                         colorSpaceName: .deviceRGB,
                                         bytesPerRow: 0, bitsPerPixel: 0) else { return nil }
        rep.size = size
        host.cacheDisplay(in: NSRect(origin: .zero, size: size), to: rep)
        return rep
    }

    // MARK: - 封面像素测量（v3：用产品发丝线/分隔线定位版心，精确可靠）

    @MainActor
    static func flatColors(light: Bool) -> [RGB] {
        light ? [RGB(hex: 0xF4EDE1), RGB(hex: 0xEBE1D2), RGB(hex: 0xFBF6EC)]
              : [RGB(hex: 0x17120D), RGB(hex: 0x1E1811), RGB(hex: 0x261E15)]
    }

    @MainActor
    static func hairlineColors(light: Bool) -> (strong: RGB, soft: RGB) {
        light ? (RGB(hex: 0xB7A488), RGB(hex: 0xD5C4AC))
              : (RGB(hex: 0x52422F), RGB(hex: 0x3A2F23))
    }

    /// 精确纸底（UI 平色，容差 3.5）：判断「边缘无纸底/无框住留白」，不受 scrim 渐变影响
    @MainActor
    static func isExactPaper(_ pa: PixelAnalysis, _ x: Int, _ y: Int, _ flats: [RGB]) -> Bool {
        let c = pa.colorAt(px: x, y)
        return flats.contains { c.distance(to: $0) < 1.5 }
    }

    struct CoverGeom {
        let separatorX: Int
        let topRuleBottom: Int
        let bottomRuleY: Int
        let widthPx: Int
        let heightPx: Int
    }

    @MainActor
    static func detectCoverGeom(_ pa: PixelAnalysis, windowSize: CGSize, light: Bool) -> CoverGeom? {
        let (strong, soft) = hairlineColors(light: light)
        let W = pa.pxW, H = pa.pxH, s = pa.scale
        let nearLine: (RGB) -> Bool = { c in
            c.distance(to: strong) < 26 || c.distance(to: soft) < 22
        }
        let bodyY0 = Int(80 * s), bodyY1 = Int((windowSize.height - 30) * s)

        var separatorX = -1
        for x in Int(0.4 * Double(W))..<W {
            var hits = 0, total = 0
            for y in stride(from: bodyY0, to: bodyY1, by: 4) {
                total += 1
                if nearLine(pa.colorAt(px: x, y)) { hits += 1 }
            }
            if total > 0 && Double(hits) / Double(total) > 0.80 { separatorX = x; break }
        }
        guard separatorX > 0 else { return nil }

        var bottomRuleY = -1
        for y in stride(from: max(0, H - Int(160 * s)), to: H - 4, by: 1) {
            var hits = 0, total = 0
            for x in stride(from: 20, to: W - 20, by: 8) {
                total += 1
                if nearLine(pa.colorAt(px: x, y)) { hits += 1 }
            }
            if total > 0 && Double(hits) / Double(total) > 0.90 { bottomRuleY = y }
        }
        guard bottomRuleY > 0 else { return nil }

        var topRuleBottom = -1
        for y in stride(from: Int(60 * s), to: min(H - 1, Int(115 * s)), by: 1) {
            var hits = 0, total = 0
            for x in stride(from: 20, to: W - 20, by: 8) {
                total += 1
                if nearLine(pa.colorAt(px: x, y)) { hits += 1 }
            }
            if total > 0 && Double(hits) / Double(total) > 0.90 { topRuleBottom = y }
        }
        if topRuleBottom < 0 { topRuleBottom = Int(79 * s) }

        return CoverGeom(separatorX: separatorX, topRuleBottom: topRuleBottom,
                         bottomRuleY: bottomRuleY, widthPx: W, heightPx: H)
    }

    @MainActor
    static func measureCover(_ pa: PixelAnalysis, windowSize: CGSize, light: Bool) throws -> [String: Any] {
        let flats = flatColors(light: light)
        guard let g = detectCoverGeom(pa, windowSize: windowSize, light: light) else {
            return ["error": "未检测到版心（竖分隔线/底部发丝线缺失）"]
        }
        let s = pa.scale
        let windowH = windowSize.height
        let heroTop = g.topRuleBottom + 1
        let heroBottom = g.bottomRuleY - 1
        let heroLeft = 0
        let heroRight = g.separatorX - 1
        let inset = 2

        func edgeImageFraction() -> [String: Double] {
            let n = 120
            var left = 0, right = 0, top = 0, bottom = 0
            for i in 0..<n {
                let t = Double(i) / Double(n - 1)
                let xx = heroLeft + Int(CGFloat(heroRight - heroLeft) * CGFloat(t))
                let yy = heroTop + Int(CGFloat(heroBottom - heroTop) * CGFloat(t))
                if !isExactPaper(pa, heroLeft + inset, yy, flats) { left += 1 }
                if !isExactPaper(pa, heroRight - inset, yy, flats) { right += 1 }
                if !isExactPaper(pa, xx, heroTop + inset, flats) { top += 1 }
                if !isExactPaper(pa, xx, heroBottom - inset, flats) { bottom += 1 }
            }
            return ["left": Double(left) / Double(n), "right": Double(right) / Double(n),
                    "top": Double(top) / Double(n), "bottom": Double(bottom) / Double(n)]
        }

        var paperPx = 0, totalPx = 0
        for y in stride(from: heroTop + 2, to: heroBottom - 2, by: 4) {
            for x in stride(from: heroLeft + 2, to: heroRight - 2, by: 4) {
                totalPx += 1
                if isExactPaper(pa, x, y, flats) { paperPx += 1 }
            }
        }

        let expectedHeroWidth = windowSize.width - 431
        let expectedHeroTop = 74.0 + 5.0
        let expectedHeroBottom = windowH - 39.0
        let heroW = CGFloat(heroRight - heroLeft + 1) / s
        let heroH = CGFloat(heroBottom - heroTop + 1) / s

        let caption = measureCaption(pa, geom: g, windowSize: windowSize, light: light)
        return [
            "window_points": arr(windowSize),
            "hero_rect_points": [0.0, Double(CGFloat(heroTop) / s), Double(heroW), Double(heroH)],
            "separator_x_points": Double(CGFloat(g.separatorX) / s),
            "top_rule_bottom_points": Double(CGFloat(g.topRuleBottom) / s),
            "bottom_rule_y_points": Double(CGFloat(g.bottomRuleY) / s),
            "hero_width_fraction_of_window": Double(heroW / windowSize.width),
            "expected_hero_width_from_code": Double(expectedHeroWidth),
            "hero_width_vs_code_error_points": Double(heroW - expectedHeroWidth),
            "expected_hero_top_from_code": expectedHeroTop,
            "hero_top_vs_code_error_points": Double(CGFloat(heroTop) / s - expectedHeroTop),
            "expected_hero_bottom_from_code": expectedHeroBottom,
            "hero_bottom_vs_code_error_points": Double(CGFloat(heroBottom) / s - expectedHeroBottom),
            "hero_touches_left_edge": heroLeft == 0,
            "hero_edge_image_fraction": edgeImageFraction(),
            "paper_fraction_inside_hero": Double(paperPx) / Double(max(1, totalPx)),
            "framed_small_image_suspect": heroW < 0.50 * windowSize.width || heroH < 0.80 * (windowH - 74 - 39),
            "caption": caption,
        ]
    }

    @MainActor
    static func measureCaption(_ pa: PixelAnalysis, geom g: CoverGeom,
                               windowSize: CGSize, light: Bool) -> [String: Any] {
        let s = pa.scale
        let heroTop = CGFloat(g.topRuleBottom + 1) / s
        let heroBottom = CGFloat(g.bottomRuleY - 1) / s
        let heroRight = CGFloat(g.separatorX - 1) / s
        let heroH = heroBottom - heroTop
        let captionROI = CGRect(x: 8, y: heroBottom - heroH * 0.30,
                                width: heroRight * 0.62, height: heroH * 0.30 - 6)
        var caption: [String: Any] = ["roi_points": arr(captionROI)]
        guard let band = detectCreamBand(pa: pa, roi: captionROI, light: light) else {
            caption["text_band_points"] = NSNull()
            caption["approx_contrast_p95_p20"] = NSNull()
            return caption
        }
        caption["text_band_points"] = arr(band)
        caption["approx_contrast_p95_p20"] = bandContrast(pa: pa, roi: band, light: light)
        let bgLum = meanBackgroundLuminance(pa: pa, roi: band, light: light)
        let midROI = CGRect(x: 8, y: heroTop + heroH * 0.45,
                            width: heroRight * 0.62, height: heroH * 0.15)
        let midLum = meanLuminance(pa: pa, roi: midROI)
        caption["caption_bg_lum"] = bgLum
        caption["mid_hero_lum"] = midLum
        caption["scrim_darkening_ratio"] = midLum > 0.0001 ? bgLum / midLum : NSNull()
        _ = windowSize
        return caption
    }

    // MARK: - caption 检测与对比度

    @MainActor
    static func detectCreamBand(pa: PixelAnalysis, roi: CGRect, light: Bool) -> CGRect? {
        let cream = light ? RGB(hex: 0xF4EDE1) : RGB(hex: 0xF0E7D8)
        let x0 = max(0, Int(roi.minX * pa.scale)), x1 = min(pa.pxW, Int(roi.maxX * pa.scale))
        let y0 = max(0, Int(roi.minY * pa.scale)), y1 = min(pa.pxH, Int(roi.maxY * pa.scale))
        guard x1 > x0, y1 > y0 else { return nil }
        var rows: [(y: Int, count: Int)] = []
        for y in y0..<y1 {
            var count = 0
            for x in x0..<x1 {
                let c = pa.colorAt(px: x, y)
                if c.distance(to: cream) < 42 && c.r > 200 { count += 1 }
            }
            if count > max(12, (x1 - x0) / 40) { rows.append((y, count)) }
        }
        guard !rows.isEmpty else { return nil }
        let minY = rows.map { $0.y }.min()!, maxY = rows.map { $0.y }.max()!
        return CGRect(x: roi.minX, y: CGFloat(minY) / pa.scale,
                      width: roi.width, height: CGFloat(maxY - minY + 1) / pa.scale)
    }

    @MainActor
    static func bandContrast(pa: PixelAnalysis, roi: CGRect, light: Bool) -> Double? {
        var lums: [Double] = []
        for y in stride(from: Int(roi.minY * pa.scale), to: Int(roi.maxY * pa.scale), by: 2) {
            for x in stride(from: Int(roi.minX * pa.scale), to: Int(roi.maxX * pa.scale), by: 2) {
                let c = pa.colorAt(px: x, y)
                lums.append(relativeLuminance(c))
            }
        }
        guard lums.count > 100 else { return nil }
        lums.sort()
        let p95 = lums[Int(Double(lums.count - 1) * 0.95)]
        let p20 = lums[Int(Double(lums.count - 1) * 0.20)]
        return (p95 + 0.05) / (p20 + 0.05)
    }

    @MainActor
    static func meanLuminance(pa: PixelAnalysis, roi: CGRect) -> Double {
        var sum = 0.0, n = 0
        for y in stride(from: Int(roi.minY * pa.scale), to: Int(roi.maxY * pa.scale), by: 3) {
            for x in stride(from: Int(roi.minX * pa.scale), to: Int(roi.maxX * pa.scale), by: 3) {
                sum += relativeLuminance(pa.colorAt(px: x, y))
                n += 1
            }
        }
        return n > 0 ? sum / Double(n) : 0
    }

    @MainActor
    static func meanBackgroundLuminance(pa: PixelAnalysis, roi: CGRect, light: Bool) -> Double {
        // 排除文字亮像素（亮度前 15%）后求均值
        var lums: [Double] = []
        for y in stride(from: Int(roi.minY * pa.scale), to: Int(roi.maxY * pa.scale), by: 2) {
            for x in stride(from: Int(roi.minX * pa.scale), to: Int(roi.maxX * pa.scale), by: 2) {
                lums.append(relativeLuminance(pa.colorAt(px: x, y)))
            }
        }
        guard lums.count > 100 else { return 0 }
        lums.sort()
        let cut = Int(Double(lums.count - 1) * 0.85)
        let kept = lums[0...max(0, cut)]
        return kept.reduce(0, +) / Double(kept.count)
    }

    // MARK: - hero 检测 & 彩色像素

    @MainActor
    static func detectHero(pa: PixelAnalysis, windowSize: CGSize, light: Bool) -> CGRect {
        let flat = light
            ? [RGB(hex: 0xF4EDE1), RGB(hex: 0xEBE1D2), RGB(hex: 0xFBF6EC)]
            : [RGB(hex: 0x17120D), RGB(hex: 0x1E1811), RGB(hex: 0x261E15)]
        let isFlat: (RGB) -> Bool = { c in flat.contains { c.distance(to: $0) < 14 } }
        let W = pa.pxW, H = pa.pxH
        var rowFrac: [Double] = []
        for y in stride(from: 0, to: H, by: 4) {
            var nonFlat = 0, total = 0
            for x in stride(from: 0, to: W, by: 4) {
                total += 1
                if !isFlat(pa.colorAt(px: x, y)) { nonFlat += 1 }
            }
            rowFrac.append(Double(nonFlat) / Double(max(1, total)))
        }
        let bodyRows = rowFrac.enumerated().filter { $0.element > 0.25 }.map { $0.offset * 4 }
        guard let bodyTop = bodyRows.first, let bodyBottom = bodyRows.last else { return .zero }
        var colFrac: [Double] = []
        for x in stride(from: 0, to: W, by: 4) {
            var nonFlat = 0, total = 0
            for y in stride(from: bodyTop, through: bodyBottom, by: 4) {
                total += 1
                if !isFlat(pa.colorAt(px: x, y)) { nonFlat += 1 }
            }
            colFrac.append(Double(nonFlat) / Double(max(1, total)))
        }
        let cols = colFrac.enumerated().filter { $0.element > 0.5 }.map { $0.offset * 4 }
        guard let left = cols.first, let right = cols.last else { return .zero }
        return CGRect(x: CGFloat(left) / pa.scale, y: CGFloat(bodyTop) / pa.scale,
                      width: CGFloat(right - left + 4) / pa.scale,
                      height: CGFloat(bodyBottom - bodyTop + 4) / pa.scale)
    }

    @MainActor
    static func countColorfulRightOfHero(pa: PixelAnalysis, hero: CGRect,
                                         windowSize: CGSize, light: Bool) -> Int {
        let x0 = max(0, Int((hero.maxX + 6) * pa.scale))
        let y0 = max(0, Int(hero.minY * pa.scale))
        let y1 = min(pa.pxH, Int(hero.maxY * pa.scale))
        guard x0 < pa.pxW, y1 > y0 else { return -1 }
        var count = 0
        for y in stride(from: y0, to: y1, by: 2) {
            for x in stride(from: x0, to: pa.pxW, by: 2) {
                let c = pa.colorAt(px: x, y)
                let hsv = c.hsv
                // 排除暖棕/黄铜色相（h 20-60），找绿/青/蓝/品红/鲜红缩略图
                let isColorful = hsv.s > 0.55 && hsv.v > 0.35
                    && !(hsv.h >= 20 && hsv.h <= 65)
                if isColorful { count += 1 }
            }
        }
        return count
    }

    // MARK: - OCR

    struct OCRText {
        let text: String
        let bbox: CGRect     // 点坐标，左上原点
    }

    @MainActor
    static func runOCR(_ rep: NSBitmapImageRep, windowSize: CGSize) throws -> (texts: [OCRText], image: CGImage) {
        guard let cg = rep.cgImage else { throw ProbeError.message("OCR: cgImage 为空") }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["zh-Hans", "en-US"]
        request.usesLanguageCorrection = true
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        try handler.perform([request])
        let obs = request.results ?? []
        let W = windowSize.width, H = windowSize.height
        var texts: [OCRText] = []
        for o in obs {
            guard let cand = o.topCandidates(1).first else { continue }
            let bb = o.boundingBox
            let rect = CGRect(x: bb.minX * W, y: (1 - bb.maxY) * H,
                              width: bb.width * W, height: bb.height * H)
            texts.append(OCRText(text: cand.string, bbox: rect))
        }
        return (texts, cg)
    }

    // MARK: - 图像 diff

    @MainActor
    static func diff(repA: NSBitmapImageRep, repB: NSBitmapImageRep) throws -> [String: Any] {
        guard repA.pixelsWide == repB.pixelsWide, repA.pixelsHigh == repB.pixelsHigh else {
            return ["size_mismatch": [repA.pixelsWide, repA.pixelsHigh, repB.pixelsWide, repB.pixelsHigh]]
        }
        let pa = PixelAnalysis(repA), pb = PixelAnalysis(repB)
        var changed = 0, total = 0
        var sumDiff = 0.0
        let step = 2
        for y in stride(from: 0, to: pa.pxH, by: step) {
            for x in stride(from: 0, to: pa.pxW, by: step) {
                let a = pa.colorAt(px: x, y), b = pb.colorAt(px: x, y)
                let d = max(abs(a.r - b.r), max(abs(a.g - b.g), abs(a.b - b.b)))
                sumDiff += d
                total += 1
                if d > 8 { changed += 1 }
            }
        }
        return ["changed_fraction": Double(changed) / Double(max(1, total)),
                "mean_abs_diff": sumDiff / Double(max(1, total))]
    }
}
