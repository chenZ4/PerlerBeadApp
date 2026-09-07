import XCTest
import AppKit
@testable import PerlerApp

/// 特效库全暴露回归（此前 15 项仅 7 项有 UI 入口）+ VM 级 WYSIWYG 联动
@MainActor
final class EffectsExposureTests: XCTestCase {

    var vm: AppViewModel!

    override func setUp() {
        super.setUp()
        vm = AppViewModel()
        vm.setup()
        _ = waitFor({ self.vm.engine != nil && self.vm.palettes.count >= 4 },
                    timeout: 15)
    }

    override func tearDown() {
        vm = nil
        super.tearDown()
    }

    private func waitFor(_ cond: @escaping () -> Bool, timeout: TimeInterval = 60) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if cond() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        return false
    }

    /// 多色测试图（软色调，饱和度调整后色卡映射应变化）
    private func makeMultiColorImage(_ w: Int = 160, _ h: Int = 120) -> String {
        let tmp = NSTemporaryDirectory() + "perler_fx_\(UUID().uuidString).png"
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w,
                                         pixelsHigh: h, bitsPerSample: 8,
                                         samplesPerPixel: 4, hasAlpha: true,
                                         isPlanar: false, colorSpaceName: .deviceRGB,
                                         bytesPerRow: 0, bitsPerPixel: 0),
              let ctx = NSGraphicsContext(bitmapImageRep: rep) else { return tmp }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = ctx
        NSColor(red: 0.85, green: 0.75, blue: 0.55, alpha: 1).setFill()
        NSBezierPath(rect: NSRect(x: 0, y: 0, width: w, height: h)).fill()
        NSColor(red: 0.75, green: 0.45, blue: 0.45, alpha: 1).setFill()
        NSBezierPath(rect: NSRect(x: 0, y: 0, width: w / 2, height: h / 2)).fill()
        NSColor(red: 0.55, green: 0.65, blue: 0.75, alpha: 1).setFill()
        NSBezierPath(rect: NSRect(x: w / 2, y: h / 2, width: w / 2, height: h / 2)).fill()
        NSGraphicsContext.restoreGraphicsState()
        if let png = rep.representation(using: .png, properties: [:]) {
            try? png.write(to: URL(fileURLWithPath: tmp))
        }
        return tmp
    }

    // 15 项特效全部可从 VM 装配（此前 8 项无入口）
    func testAllFifteenEffectsAssembled() {
        vm.chibiOn = true
        vm.mirrorOn = true
        vm.cropOn = true
        vm.grayscaleOn = true
        vm.adjustOn = true
        vm.celShadeOn = true
        vm.neonOn = true
        vm.duotoneOn = true
        vm.bgRemoveOn = true
        vm.outlineEdgeOn = true
        vm.ditherOn = true
        vm.outlineCellOn = true
        vm.maxColorsOn = true
        vm.presetOn = true
        vm.darkChartOn = true
        let ids = vm.effectsParams().compactMap { $0["id"] as? String }
        XCTAssertEqual(Set(ids).count, 15, "15 项特效应全部进 effects 参数：\(ids)")
        XCTAssertEqual(ids.first, "chibi", "几何阶段特效应排最前")
        XCTAssertEqual(ids.last, "dark_chart", "图纸阶段特效应排最后")
    }

    // 特效参数值正确装配（adjust/crop/bg_remove/duotone/neon）
    func testEffectParamsCarried() {
        vm.adjustOn = true
        vm.adjustBrightness = 1.25
        vm.cropOn = true
        vm.cropX0 = 0.25
        vm.bgRemoveOn = true
        vm.bgRemoveTolerance = 44
        vm.duotoneOn = true
        vm.duotoneColor1 = "#112233"
        vm.neonOn = true
        vm.neonDarkness = 0.6
        let byId = Dictionary(uniqueKeysWithValues:
            vm.effectsParams().compactMap { e -> (String, [String: Any])? in
                guard let id = e["id"] as? String else { return nil }
                return (id, (e["params"] as? [String: Any]) ?? [:])
            })
        XCTAssertEqual(byId["adjust"]?["brightness"] as? Double, 1.25)
        XCTAssertEqual(byId["crop"]?["x0"] as? Double, 0.25)
        XCTAssertEqual(byId["bg_remove"]?["tolerance"] as? Int, 44)
        XCTAssertEqual(byId["duotone"]?["color1"] as? String, "#112233")
        XCTAssertEqual(byId["neon"]?["darkness"] as? Double, 0.6)
    }

    // 全特效开启真实引擎生成不报错（协议层接受全部参数）
    func testGenerateSucceedsWithAllEffects() {
        vm.setImagePath(makeMultiColorImage())
        vm.mirrorOn = true
        vm.adjustOn = true
        vm.celShadeOn = true
        vm.bgRemoveOn = true
        vm.duotoneOn = true
        vm.outlineEdgeOn = true
        vm.maxColorsOn = true
        vm.presetOn = true
        vm.gridW = "40"
        vm.gridH = "30"
        vm.generate()
        _ = waitFor({ self.vm.lastResult != nil || self.vm.statusText.contains("失败") })
        XCTAssertNotNil(vm.lastResult, "全特效生成应成功：\(vm.statusText)")
    }

    // WYSIWYG：原始比例 UI 联动配对 = 引擎最终网格（主诉回归，VM 级）
    func testEngineHonorsLinkedPairOriginalRatio() {
        vm.setImagePath(makeMultiColorImage(160, 120))   // ar = 4/3
        vm.ratioMode = "原始比例"
        vm.gridW = "40"
        vm.gridH = "29"
        vm.gridFieldEdited("w")
        XCTAssertEqual(vm.gridH, "30")
        vm.generate()
        _ = waitFor({ self.vm.lastResult != nil })
        XCTAssertEqual(vm.lastResult?.gridW, 40)
        XCTAssertEqual(vm.lastResult?.gridH, 30, "引擎应原样生效 UI 联动配对 40×30")
    }

    // WYSIWYG：竖图改高联动宽，引擎原样生效
    func testEngineHonorsLinkedPairPortraitHeightEdit() {
        vm.setImagePath(makeMultiColorImage(120, 160))   // ar = 3/4
        vm.ratioMode = "原始比例"
        vm.gridW = "29"
        vm.gridH = "40"
        vm.gridFieldEdited("h")
        XCTAssertEqual(vm.gridW, "30")
        vm.generate()
        _ = waitFor({ self.vm.lastResult != nil })
        XCTAssertEqual(vm.lastResult?.gridW, 30, "引擎应原样生效 30×40")
        XCTAssertEqual(vm.lastResult?.gridH, 40)
    }
}
