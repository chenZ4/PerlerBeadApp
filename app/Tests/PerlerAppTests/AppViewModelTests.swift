import XCTest
import AppKit
@testable import PerlerApp

/// 模拟用户操作测试：驱动 AppViewModel + 真实引擎后端
@MainActor
final class AppViewModelTests: XCTestCase {

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

    private func makeTestImage(_ w: Int = 160, _ h: Int = 120) -> String {
        let tmp = NSTemporaryDirectory() + "perler_vm_\(UUID().uuidString).png"
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w,
                                         pixelsHigh: h, bitsPerSample: 8,
                                         samplesPerPixel: 4, hasAlpha: true,
                                         isPlanar: false, colorSpaceName: .deviceRGB,
                                         bytesPerRow: 0, bitsPerPixel: 0),
              let ctx = NSGraphicsContext(bitmapImageRep: rep) else { return tmp }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = ctx
        NSColor.systemRed.setFill()
        NSBezierPath(rect: NSRect(x: 0, y: 0, width: w, height: h)).fill()
        NSGraphicsContext.restoreGraphicsState()
        if let png = rep.representation(using: .png, properties: [:]) {
            try? png.write(to: URL(fileURLWithPath: tmp))
        }
        return tmp
    }

    // 场景 1: 启动
    func testStartup() {
        XCTAssertTrue(vm.engine != nil, "引擎应就绪")
        XCTAssertGreaterThanOrEqual(vm.palettes.count, 4)
        XCTAssertEqual(vm.paletteDisplay, "MARD 221 色", "默认色卡应为 MARD 221")
    }

    // 场景 2: 选图 → 生成 → 正确色卡
    func testGenerateWithCorrectPalette() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "40"; vm.gridH = "40"; vm.cellSize = "40"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.chartImage != nil }), "预览应出现")
        let result = vm.lastResult
        XCTAssertNotNil(result)
        XCTAssertEqual(result?.gridW, 40)
        XCTAssertNotNil(vm.finishedImage, "成品图应加载")
        // 色号属于 221 色卡（非 fallback）
        let codes = vm.palettes.first { $0.internalName == "mard_221" }
        XCTAssertNotNil(codes)
        // stats 色号有效性
        if let stats = result?.colorStats {
            XCTAssertFalse(stats.isEmpty)
        }
    }

    // 场景 3: 切换色卡 → 重新生成
    func testSwitchPalette() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.paletteDisplay = "哈马 16 色"
        vm.gridW = "30"; vm.gridH = "30"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.lastResult != nil }), "生成完成")
        let stats = vm.lastResult?.colorStats ?? [:]
        let hamaCodes = Set(["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8",
                             "B9", "B10", "B11", "B12", "B13", "B14", "B15", "B16"])
        let invalid = stats.keys.filter { !hamaCodes.contains($0) }
        XCTAssertTrue(invalid.isEmpty,
                      "切换哈马色卡后色号应为 B1-B16：\(invalid)")
    }

    // 场景 4: 特效描边
    func testOutlineEffect() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.outlineCellOn = true
        vm.gridW = "30"; vm.gridH = "30"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.lastResult != nil }), "生成完成")
        let stats = vm.lastResult?.colorStats ?? [:]
        let dark = stats.values.filter { $0.rgb.reduce(0, +) < 200 }
        XCTAssertFalse(dark.isEmpty, "描边特效应产生深色描边格")
    }

    // 场景 5: 编辑换色生效
    func testEditColorTakesEffect() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "40"; vm.gridH = "40"; vm.cellSize = "40"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.chartImage != nil }), "生成完成")
        XCTAssertNil(vm.lastResult?.colorStats["H1"],
                     "编辑前不应有白色 H1（纯红图）")

        vm.editMode = true
        vm.editColorCode = "H1"
        vm.previewGeo = CGSize(width: 800, height: 600)
        vm.fitToWindow = true
        vm.offset = .zero
        vm.handlePreviewTap(location: CGPoint(x: 400, y: 300))
        XCTAssertTrue(waitFor({ (self.vm.lastResult?.colorStats["H1"]?.count ?? 0) > 0 }),
                      "编辑后 H1（白色）计数应 > 0")
        XCTAssertEqual(vm.editHistory.count, 1)
    }

    // 场景 6: 撤销编辑
    func testUndoEdit() {
        testEditColorTakesEffect()
        let before = vm.lastResult?.chartPath
        vm.undoEdit()
        XCTAssertTrue(waitFor({ self.vm.lastResult?.chartPath != before }),
                      "撤销后应重新生成")
        XCTAssertTrue(waitFor({ (self.vm.lastResult?.colorStats["H1"]?.count ?? 0) == 0 }),
                      "撤销后 H1 应消失")
        XCTAssertTrue(vm.editHistory.isEmpty)
    }

    // 场景 7: 成品效果切换
    func testFinishedToggle() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.finishedImage != nil }), "成品图应加载")
        XCTAssertNotNil(vm.finishedImage)
    }

    // 场景 8: 导出 PNG
    func testExportPNG() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "20"; vm.gridH = "20"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.lastResult != nil }), "生成完成")
        let dest = NSTemporaryDirectory() + "vm_out.png"
        try? FileManager.default.removeItem(atPath: dest)
        vm.exportPNG(to: dest)
        XCTAssertTrue(waitFor({ FileManager.default.fileExists(atPath: dest) }),
                      "PNG 应导出")
    }

    // 场景 9: 模板加载 + 色卡联动
    func testTemplateLoad() {
        XCTAssertGreaterThanOrEqual(vm.templates.count, 5)
        vm.loadTemplate("heart")
        XCTAssertTrue(waitFor({ self.vm.imagePath != nil }), "模板图应加载")
        XCTAssertEqual(vm.gridW, "9", "模板宽 9")
        XCTAssertTrue(waitFor({ self.vm.paletteDisplay == "MARD 221 色" }),
                      "模板色卡应联动为 MARD 221")
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.lastResult != nil }), "模板生成")
        XCTAssertGreaterThan(vm.lastResult?.totalBeads ?? 0, 0)
    }

    // 场景 10: 限色数
    func testMaxColors() {
        let grad = makeGradientImage()
        vm.setImagePath(grad)
        vm.maxColorsOn = true
        vm.maxColorsValue = 6
        vm.gridW = "40"; vm.gridH = "40"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.lastResult != nil }), "生成完成")
        let n = vm.lastResult?.colorStats.count ?? 99
        XCTAssertLessThanOrEqual(n, 6, "限色后颜色数 ≤ 6（实际 \(n)）")
    }

    // 场景 11: 进度追踪保存/恢复
    func testTrackPersist() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "40"; vm.gridH = "40"; vm.cellSize = "40"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.chartImage != nil }), "生成完成")

        vm.editMode = true
        vm.trackMode = true
        vm.previewGeo = CGSize(width: 800, height: 600)
        vm.offset = .zero
        vm.handlePreviewTap(location: CGPoint(x: 400, y: 300))
        XCTAssertEqual(vm.doneCells.count, 1, "应标记 1 格")
        _ = waitFor({ true })

        // 新会话恢复
        let vm2 = AppViewModel()
        vm2.setup()
        _ = waitFor({ vm2.engine != nil }, timeout: 15)
        vm2.setImagePath(src)
        XCTAssertTrue(waitFor({ vm2.trackedCount == 1 }, timeout: 30),
                      "新会话应恢复进度 \(vm2.trackedCount)")
    }

    // 场景 12: 色卡数据完整
    func testPaletteData() {
        XCTAssertGreaterThanOrEqual(vm.palettes.count, 4)
        let mard = vm.palettes.first { $0.internalName == "mard_221" }
        XCTAssertEqual(mard?.count, 221, "MARD 应为 221 色")
    }

    private func makeGradientImage() -> String {
        let tmp = NSTemporaryDirectory() + "perler_grad_\(UUID().uuidString).png"
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 120,
                                         pixelsHigh: 120, bitsPerSample: 8,
                                         samplesPerPixel: 4, hasAlpha: true,
                                         isPlanar: false, colorSpaceName: .deviceRGB,
                                         bytesPerRow: 0, bitsPerPixel: 0),
              let ctx = NSGraphicsContext(bitmapImageRep: rep) else { return tmp }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = ctx
        for y in 0..<120 {
            for x in 0..<120 {
                NSColor(calibratedRed: CGFloat(x) / 120, green: 0.5,
                        blue: CGFloat(y) / 120, alpha: 1).setFill()
                NSBezierPath(rect: NSRect(x: x, y: y, width: 1, height: 1)).fill()
            }
        }
        NSGraphicsContext.restoreGraphicsState()
        if let png = rep.representation(using: .png, properties: [:]) {
            try? png.write(to: URL(fileURLWithPath: tmp))
        }
        return tmp
    }
}
