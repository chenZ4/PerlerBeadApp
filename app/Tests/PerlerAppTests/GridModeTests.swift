import XCTest
import AppKit
@testable import PerlerApp

/// 网格比例模式 + 编辑/成品互斥 + PDF 模式（主诉修复回归）
@MainActor
final class GridModeTests: XCTestCase {

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

    /// 源图 160×120（4:3），便于验证比例行为
    private func makeTestImage(_ w: Int = 160, _ h: Int = 120) -> String {
        let tmp = NSTemporaryDirectory() + "perler_grid_\(UUID().uuidString).png"
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

    private func generate(_ w: String, _ h: String, ratio: String) -> GenerateResult? {
        vm.setImagePath(makeTestImage())
        vm.gridW = w
        vm.gridH = h
        vm.ratioMode = ratio
        vm.generate()
        _ = waitFor({ self.vm.lastResult != nil })
        return vm.lastResult
    }

    // 主诉修复：1:1 精确网格不被源图比例覆盖
    func testExactGridSquare() {
        let r = generate("40", "40", ratio: "1:1")
        XCTAssertEqual(r?.gridW, 40)
        XCTAssertEqual(r?.gridH, 40, "1:1 模式必须精确 40×40（不被源图 4:3 覆盖）")
    }

    // 4:3 精确网格
    func testExactGrid4x3() {
        let r = generate("40", "30", ratio: "4:3")
        XCTAssertEqual(r?.gridW, 40)
        XCTAssertEqual(r?.gridH, 30)
    }

    // 原始比例：宽基准 + 源图比例（4:3 源图 → 40×30）
    func testOriginalRatio() {
        let r = generate("40", "40", ratio: "原始比例")
        XCTAssertEqual(r?.gridW, 40)
        XCTAssertEqual(r?.gridH, 30, "原始比例按源图 4:3 计算高")
    }

    // 等比完整：适应框内（40×40 框 + 4:3 图 → 40×30 同原始比例；但换 3:4 图验证差异）
    func testFitBox() {
        let src = makeTestImage(120, 160)  // 3:4 竖图
        vm.setImagePath(src)
        vm.gridW = "40"; vm.gridH = "40"
        vm.ratioMode = "等比完整"
        vm.generate()
        _ = waitFor({ self.vm.lastResult != nil })
        let r = vm.lastResult
        XCTAssertEqual(r?.gridW, 30, "等比完整适应框内：宽应为 30")
        XCTAssertEqual(r?.gridH, 40)
    }

    // 比例联动：1:1 → 高=宽；4:3 → 高=宽*3/4；双向（对齐 Tk 版）
    func testRatioLink() {
        vm.gridW = "60"
        vm.ratioMode = "1:1"
        vm.applyRatioLink()
        XCTAssertEqual(vm.gridH, "60")
        vm.ratioMode = "4:3"
        vm.applyRatioLink()
        XCTAssertEqual(vm.gridH, "45")
        vm.ratioMode = "16:9"
        vm.applyRatioLink()
        XCTAssertEqual(vm.gridH, "34", "16:9 使用四舍五入（60*9/16=33.75→34）")
    }

    // 比例联动双向：编辑高 → 宽跟随（Tk 版行为）
    func testRatioLinkFromHeight() {
        vm.ratioMode = "4:3"
        vm.gridW = "10"
        vm.gridH = "30"
        vm.applyRatioLink(source: "h")
        XCTAssertEqual(vm.gridW, "40")
        XCTAssertEqual(vm.gridH, "30")
    }

    // 实时联动：编辑宽立即联动高（1:1），且联动回声不破坏状态
    func testImmediateLinkOnWidthEdit() {
        vm.ratioMode = "1:1"
        vm.gridW = "29"
        vm.gridH = "29"
        vm.gridW = "40"
        vm.gridFieldEdited("w")
        XCTAssertEqual(vm.gridH, "40", "改宽应立即联动高")
        vm.gridFieldEdited("h")   // 程序写入的回声，应被忽略
        XCTAssertEqual(vm.gridW, "40")
        XCTAssertEqual(vm.gridH, "40")
    }

    // 实时联动：编辑高立即联动宽（4:3 双向）
    func testImmediateLinkOnHeightEdit() {
        vm.ratioMode = "4:3"
        vm.gridW = "10"
        vm.gridH = "30"
        vm.gridFieldEdited("h")
        XCTAssertEqual(vm.gridW, "40", "改高应立即联动宽")
        XCTAssertEqual(vm.gridH, "30")
    }

    // 实时联动：清空/半输入不联动另一侧
    func testImmediateLinkSkipsInvalidInput() {
        vm.ratioMode = "1:1"
        vm.gridW = "40"
        vm.gridH = "40"
        vm.gridW = ""
        vm.gridFieldEdited("w")
        XCTAssertEqual(vm.gridH, "40", "清空宽时不应联动高")
    }

    // 生成前自动联动：1:1 下只改宽、高未联动 → 生成仍为正方形
    func testGenerateRelinksFromWidth() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.ratioMode = "1:1"
        vm.gridH = "29"
        vm.gridW = "40"      // didSet 记录 lastEditedDim = 'w'
        vm.generate()
        _ = waitFor({ self.vm.lastResult != nil })
        XCTAssertEqual(vm.lastResult?.gridW, 40)
        XCTAssertEqual(vm.lastResult?.gridH, 40, "生成前应按最后编辑的宽联动高（40×40 而非 40×29）")
    }

    // 生成前自动联动：最后编辑的是高 → 以高为基准
    func testGenerateRelinksFromHeight() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.ratioMode = "1:1"
        vm.gridW = "29"
        vm.gridH = "50"      // didSet 记录 lastEditedDim = 'h'
        vm.generate()
        _ = waitFor({ self.vm.lastResult != nil })
        XCTAssertEqual(vm.lastResult?.gridW, 50, "最后编辑高时应以高为基准联动宽")
        XCTAssertEqual(vm.lastResult?.gridH, 50)
    }

    // 输入钳制：非法/越界输入回退或钳制，不崩溃
    func testGridInputClamping() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.ratioMode = "原始比例"
        vm.gridW = "abc"
        vm.gridH = "-3"
        vm.cellSize = "9999"
        vm.generate()
        _ = waitFor({ self.vm.lastResult != nil })
        XCTAssertNotNil(vm.lastResult, "非法输入应回退默认值而不崩溃")
        XCTAssertEqual(vm.lastResult?.cellSize, 160, "每格像素应钳制到 160")
    }

    // 编辑在精确网格下保持网格尺寸
    func testEditPreservesExactGrid() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "40"; vm.gridH = "40"
        vm.ratioMode = "1:1"
        vm.generate()
        _ = waitFor({ self.vm.lastResult != nil })
        XCTAssertEqual(vm.lastResult?.gridH, 40)
        vm.editMode = true
        vm.editColorCode = "H1"
        vm.previewGeo = CGSize(width: 800, height: 600)
        vm.fitToWindow = true
        vm.offset = .zero
        vm.handlePreviewTap(location: CGPoint(x: 400, y: 300))
        _ = waitFor({ (self.vm.lastResult?.colorStats["H1"]?.count ?? 0) > 0 })
        XCTAssertEqual(vm.lastResult?.gridW, 40, "编辑后网格应保持")
        XCTAssertEqual(vm.lastResult?.gridH, 40)
    }

    // R2: 编辑模式下强制显示图纸
    func testEditForcesChartView() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.generate()
        _ = waitFor({ self.vm.finishedImage != nil })
        vm.showFinished = true
        XCTAssertTrue(vm.effectiveShowFinished)
        vm.editMode = true
        XCTAssertFalse(vm.effectiveShowFinished, "编辑模式下应强制图纸")
    }

    // R3: PDF 1x1 模式导出
    func testPDFExport1x1() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "30"; vm.gridH = "30"; vm.cellSize = "40"
        vm.generate()
        _ = waitFor({ self.vm.lastResult != nil })
        let dest = NSTemporaryDirectory() + "grid_1x1.pdf"
        try? FileManager.default.removeItem(atPath: dest)
        vm.exportPDF(to: dest, mode: "1x1")
        let ok = waitFor({
            guard let data = try? Data(contentsOf: URL(fileURLWithPath: dest)) else { return false }
            return String(decoding: data, as: UTF8.self).hasPrefix("%PDF-")
        }, timeout: 30)
        XCTAssertTrue(ok, "1x1 PDF 应导出")
        vm.exportPDF(to: dest, mode: "a4")
        let ok2 = waitFor({
            guard let data = try? Data(contentsOf: URL(fileURLWithPath: dest)) else { return false }
            return String(decoding: data, as: UTF8.self).hasPrefix("%PDF-")
        }, timeout: 30)
        XCTAssertTrue(ok2, "A4 PDF 应导出")
    }
}

@MainActor
final class CancelTests: XCTestCase {

    var vm: AppViewModel!

    override func setUp() {
        super.setUp()
        vm = AppViewModel()
        vm.setup()
        let d = Date().addingTimeInterval(15)
        while Date() < d && vm.engine == nil {
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
    }

    override func tearDown() {
        vm = nil
        super.tearDown()
    }

    private func waitFor(_ cond: @escaping () -> Bool, timeout: TimeInterval = 30) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if cond() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        return false
    }

    // R4: 生成中取消 → 快速复位不挂死
    func testCancelGenerate() {
        let tmp = NSTemporaryDirectory() + "perler_cancel_\(UUID().uuidString).png"
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 300,
                                         pixelsHigh: 300, bitsPerSample: 8,
                                         samplesPerPixel: 4, hasAlpha: true,
                                         isPlanar: false, colorSpaceName: .deviceRGB,
                                         bytesPerRow: 0, bitsPerPixel: 0),
              let ctx = NSGraphicsContext(bitmapImageRep: rep) else {
            XCTFail("无法创建测试图")
            return
        }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = ctx
        NSColor.systemRed.setFill()
        NSBezierPath(rect: NSRect(x: 0, y: 0, width: 300, height: 300)).fill()
        NSGraphicsContext.restoreGraphicsState()
        try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: tmp))

        vm.setImagePath(tmp)
        vm.gridW = "300"; vm.gridH = "300"; vm.cellSize = "60"
        vm.generate()
        // 生成已开始（isBusy）
        _ = waitFor({ self.vm.isBusy }, timeout: 5)
        let t0 = Date()
        vm.cancelActive()
        let ok = waitFor({ !self.vm.isBusy && self.vm.statusText.contains("取消") },
                         timeout: 10)
        XCTAssertTrue(ok, "取消后 10s 内复位（实际 \(Date().timeIntervalSince(t0))s）")
        XCTAssertFalse(vm.isBusy)
    }
}
