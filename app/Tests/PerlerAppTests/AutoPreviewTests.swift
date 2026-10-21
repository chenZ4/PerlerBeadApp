import XCTest
import AppKit
@testable import PerlerApp

/// T5 自动预览 / 脏标记 / 新参数装配 / warnings 解码回归
@MainActor
final class AutoPreviewTests: XCTestCase {

    var vm: AppViewModel!

    override func setUp() {
        super.setUp()
        vm = AppViewModel()
        vm.setup()
        _ = waitFor({ self.vm.engine != nil && self.vm.palettes.count >= 4 }, timeout: 15)
    }

    override func tearDown() {
        vm = nil
        super.tearDown()
    }

    private func waitFor(_ cond: @escaping () -> Bool, timeout: TimeInterval = 40) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if cond() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        return false
    }

    private func makeImage(_ w: Int = 120, _ h: Int = 90) -> String {
        let tmp = NSTemporaryDirectory() + "perler_auto_\(UUID().uuidString).png"
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h,
                                         bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                         isPlanar: false, colorSpaceName: .deviceRGB,
                                         bytesPerRow: 0, bitsPerPixel: 0),
              let ctx = NSGraphicsContext(bitmapImageRep: rep) else { return tmp }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = ctx
        NSColor(red: 0.9, green: 0.5, blue: 0.2, alpha: 1).setFill()
        NSBezierPath(rect: NSRect(x: 0, y: 0, width: w, height: h)).fill()
        NSColor(red: 0.2, green: 0.4, blue: 0.9, alpha: 1).setFill()
        NSBezierPath(ovalIn: NSRect(x: 10, y: 10, width: w / 2, height: h / 2)).fill()
        NSGraphicsContext.restoreGraphicsState()
        if let png = rep.representation(using: .png, properties: [:]) {
            try? png.write(to: URL(fileURLWithPath: tmp))
        }
        return tmp
    }

    // 脏标记：parametersDidChange 置 true；取消 pending 后可手动生成清除
    func testNeedsRegenerateFlag() {
        vm.autoPreviewEnabled = false
        vm.parametersDidChange()
        XCTAssertTrue(vm.needsRegenerate, "参数变更后应有脏标记")
        vm.cancelPendingAutoPreview()
        vm.setImagePath(makeImage())
        vm.autoPreviewEnabled = true
        vm.gridW = "20"
        vm.gridH = "15"
        vm.parametersDidChange()
        XCTAssertTrue(vm.needsRegenerate)
    }

    // 特效开关/参数 → effectsParams 装配（含 T5 新暴露参数）
    func testEffectParamsIncludeTunables() {
        vm.outlineCellOn = true
        vm.outlineCellWidth = 2
        vm.outlineEdgeOn = true
        vm.outlineEdgeStrength = 0.7
        vm.ditherOn = true
        vm.ditherStrength = 0.5
        vm.grayscaleOn = true
        vm.grayscaleContrast = 1.3
        let byId = Dictionary(uniqueKeysWithValues: vm.effectsParams().compactMap { e -> (String, [String: Any])? in
            guard let id = e["id"] as? String else { return nil }
            return (id, (e["params"] as? [String: Any]) ?? [:])
        })
        XCTAssertEqual(byId["outline_cell"]?["width"] as? Int, 2)
        XCTAssertEqual(byId["outline_edge"]?["strength"] as? Double, 0.7)
        XCTAssertEqual(byId["dither"]?["strength"] as? Double, 0.5)
        XCTAssertEqual(byId["grayscale"]?["contrast"] as? Double, 1.3)
        vm.cancelPendingAutoPreview()
    }

    // crop 默认参数：打开开关即有明显裁剪（不再是恒等裁剪）
    func testCropDefaultsAreVisible() {
        vm.autoPreviewEnabled = false
        vm.cropOn = true
        XCTAssertGreaterThan(vm.cropX1, vm.cropX0)
        XCTAssertGreaterThan(vm.cropX0, 0.0)
        XCTAssertLessThan(vm.cropX1, 1.0)
        let crop = vm.effectsParams().first { ($0["id"] as? String) == "crop" }
        let p = crop?["params"] as? [String: Any] ?? [:]
        XCTAssertEqual(p["x0"] as? Double, 0.1)
        XCTAssertEqual(p["x1"] as? Double, 0.9)
        vm.cancelPendingAutoPreview()
    }

    // warnings 字段解码（向后兼容：旧响应无 warnings → []）
    func testWarningsDecoding() throws {
        let base: [String: Any] = [
            "chart_path": "/tmp/a.png", "chart_size": [10, 10],
            "grid_w": 2, "grid_h": 2, "cell_size": 4,
        ]
        let d1 = try JSONSerialization.data(withJSONObject: base)
        let r1 = try JSONDecoder().decode(GenerateResult.self, from: d1)
        XCTAssertEqual(r1.warnings, [])
        var withW = base
        withW["warnings"] = ["大头(Q版)：未检测到人脸，已跳过"]
        let d2 = try JSONSerialization.data(withJSONObject: withW)
        let r2 = try JSONDecoder().decode(GenerateResult.self, from: d2)
        XCTAssertEqual(r2.warnings.count, 1)
        XCTAssertTrue(r2.warnings[0].contains("大头"))
    }

    // 自动预览：debounce 后自动生成，无需点「生成」
    func testAutoPreviewGenerates() {
        vm.setImagePath(makeImage())
        vm.gridW = "20"
        vm.gridH = "15"
        vm.autoPreviewEnabled = true
        vm.parametersDidChange()
        let done = waitFor({ self.vm.lastResult != nil && !self.vm.needsRegenerate }, timeout: 60)
        XCTAssertTrue(done, "自动预览应完成并清除脏标记：\(vm.statusText) / engine=\(vm.engine?.engineErrorLog ?? "")")
        XCTAssertNotNil(vm.chartImage)
    }

    // 手动生成优先：手动 generate 会取消 pending 自动预览，且不被覆盖
    func testManualGenerateWinsOverAutoPreview() {
        vm.setImagePath(makeImage())
        vm.gridW = "20"
        vm.gridH = "15"
        vm.autoPreviewEnabled = true
        vm.parametersDidChange()
        vm.generate()
        let done = waitFor({ self.vm.lastResult != nil }, timeout: 60)
        XCTAssertTrue(done, vm.statusText + " / engine=" + (vm.engine?.engineErrorLog ?? ""))
        XCTAssertFalse(vm.needsRegenerate)
    }
}
