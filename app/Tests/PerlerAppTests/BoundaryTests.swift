import XCTest
import AppKit
@testable import PerlerApp

/// T2 边界与异常测试（真实引擎后端）
@MainActor
final class BoundaryTests: XCTestCase {

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

    private func makeTestImage(_ w: Int = 160, _ h: Int = 120, color: NSColor = .systemRed) -> String {
        let tmp = NSTemporaryDirectory() + "perler_bnd_\(UUID().uuidString).png"
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w,
                                         pixelsHigh: h, bitsPerSample: 8,
                                         samplesPerPixel: 4, hasAlpha: true,
                                         isPlanar: false, colorSpaceName: .deviceRGB,
                                         bytesPerRow: 0, bitsPerPixel: 0),
              let ctx = NSGraphicsContext(bitmapImageRep: rep) else { return tmp }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = ctx
        color.setFill()
        NSBezierPath(rect: NSRect(x: 0, y: 0, width: w, height: h)).fill()
        NSGraphicsContext.restoreGraphicsState()
        if let png = rep.representation(using: .png, properties: [:]) {
            try? png.write(to: URL(fileURLWithPath: tmp))
        }
        return tmp
    }

    // T2.1 非法网格值：不崩，回退默认
    func testInvalidGridValues() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "abc"
        vm.gridH = "0"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.lastResult != nil }), "非法网格值应仍能生成")
        XCTAssertEqual(vm.lastResult?.gridW, 29, "非法宽回退 29")
    }

    // T2.2 空色号编辑：忽略不崩
    func testEmptyColorCode() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "40"; vm.gridH = "40"; vm.cellSize = "40"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.chartImage != nil }), "生成完成")
        vm.editMode = true
        vm.editColorCode = "   "
        vm.handlePreviewTap(location: CGPoint(x: 400, y: 300))
        XCTAssertEqual(vm.editHistory.count, 0, "空色号不应入编辑栈")
        XCTAssertEqual(vm.lastResult?.chartPath ?? "", vm.lastResult?.chartPath ?? "")
    }

    // T2.3 无效色号编辑：引擎忽略该格，不崩，有效编辑仍生效
    func testInvalidColorCodeEdit() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "40"; vm.gridH = "40"; vm.cellSize = "40"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.chartImage != nil }), "生成完成")
        vm.editMode = true
        vm.editColorCode = "ZZZ"
        vm.handlePreviewTap(location: CGPoint(x: 400, y: 300))
        // 无效色号：引擎应忽略该格；本地栈仍记录（不崩即可）
        XCTAssertEqual(vm.editHistory.count, 1)
        XCTAssertTrue(waitFor({ self.vm.lastResult != nil }), "编辑请求返回")
        // 有效色号叠加
        vm.editColorCode = "H1"
        vm.handlePreviewTap(location: CGPoint(x: 200, y: 200))
        XCTAssertTrue(waitFor({ (self.vm.lastResult?.colorStats["H1"]?.count ?? 0) > 0 }),
                      "有效色号编辑应生效")
    }

    // T2.4 连续快速生成 ×3：全部完成无挂起
    func testRapidGenerate() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "30"; vm.gridH = "30"
        vm.generate()
        vm.generate()
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.lastResult != nil }), "最后一次生成完成")
        XCTAssertFalse(vm.isBusy, "不应卡在处理中")
        XCTAssertTrue(waitFor({ !self.vm.isBusy }))
    }

    // T2.5 生成中切换色卡再生成：最终用新色卡
    func testSwitchPaletteWhileBusy() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "30"; vm.gridH = "30"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.lastResult != nil }), "首次生成")
        let firstPath = vm.lastResult?.chartPath
        vm.paletteDisplay = "哈马 16 色"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.lastResult?.chartPath != firstPath }),
                      "第二次生成应完成")
        let stats = vm.lastResult?.colorStats ?? [:]
        let hama = Set(["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8",
                        "B9", "B10", "B11", "B12", "B13", "B14", "B15", "B16"])
        let invalid = stats.keys.filter { !hama.contains($0) }
        XCTAssertTrue(invalid.isEmpty, "最终结果应为哈马色卡：\(invalid)")
    }

    // T2.6 换图后编辑状态应清空（防残留污染新图）
    func testSwitchImageClearsEditState() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "40"; vm.gridH = "40"; vm.cellSize = "40"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.chartImage != nil }), "生成完成")
        vm.editMode = true
        vm.editColorCode = "H1"
        vm.handlePreviewTap(location: CGPoint(x: 400, y: 300))
        XCTAssertTrue(waitFor({ (self.vm.lastResult?.colorStats["H1"]?.count ?? 0) > 0 }),
                      "编辑生效")
        XCTAssertEqual(vm.editHistory.count, 1)

        // 切换新图
        let src2 = makeTestImage(color: .systemBlue)
        vm.setImagePath(src2)
        XCTAssertEqual(vm.editHistory.count, 0, "换图后编辑历史应清空")
        XCTAssertTrue(vm.doneCells.isEmpty, "换图后进度标记应清空")
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.lastResult != nil }), "新图生成")
        let count = vm.lastResult?.colorStats["H1"]?.count ?? 0
        XCTAssertEqual(count, 0, "新图不应带旧编辑（H1 不应存在）")
    }

    // T2.7 成品效果显示时点击编辑：应换算到成品图或禁用编辑
    func testEditWhileFinishedShown() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "40"; vm.gridH = "40"; vm.cellSize = "40"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.chartImage != nil && self.vm.finishedImage != nil }),
                      "生成完成")
        vm.editMode = true
        vm.showFinished = true
        vm.editColorCode = "H1"
        vm.previewGeo = CGSize(width: 800, height: 600)
        vm.fitToWindow = true
        vm.offset = .zero
        vm.handlePreviewTap(location: CGPoint(x: 400, y: 300))
        // 成品图与图纸尺寸不同，点击换算应正确（编辑仍生效且作用于网格中心）
        XCTAssertTrue(waitFor({ (self.vm.lastResult?.colorStats["H1"]?.count ?? 0) > 0 }),
                      "成品模式下点击编辑仍应生效")
    }

    // T2.8 offset 偏移后编辑点击换算正确
    func testEditWithOffset() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "40"; vm.gridH = "40"; vm.cellSize = "40"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.chartImage != nil }), "生成完成")
        vm.editMode = true
        vm.editColorCode = "H1"
        vm.previewGeo = CGSize(width: 800, height: 600)
        vm.fitToWindow = false
        vm.zoom = 200
        vm.offset = CGSize(width: -100, height: -80)
        // 图像左上角 = (800-w)/2 - 100；点击图像中心应命中网格中心
        let size = vm.previewSize(img: vm.chartImage!)
        let imgX = (vm.previewGeo.width - size.width) / 2 + vm.offset.width
        let imgY = (vm.previewGeo.height - size.height) / 2 + vm.offset.height
        let tap = CGPoint(x: imgX + size.width / 2, y: imgY + size.height / 2)
        vm.handlePreviewTap(location: tap)
        XCTAssertTrue(waitFor({ (self.vm.lastResult?.colorStats["H1"]?.count ?? 0) > 0 }),
                      "偏移后点击编辑应命中网格中心")
    }

    // T2.9 引擎超时：不可达路径（引擎存活时跳过）；验证超时机制不误伤
    func testTimeoutNoFalsePositive() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "20"; vm.gridH = "20"
        let t0 = Date()
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.lastResult != nil }), "正常请求不应超时")
        XCTAssertLessThan(Date().timeIntervalSince(t0), 30, "不应触发超时")
    }

    // T2.10 模板 → 自定义图片切换：状态正确
    func testTemplateThenCustomImage() {
        vm.loadTemplate("heart")
        XCTAssertTrue(waitFor({ self.vm.imagePath != nil }), "模板加载")
        let src = makeTestImage()
        vm.setImagePath(src)
        XCTAssertNil(vm.selectedTemplate, "切回自定义后模板选择应清空")
        vm.gridW = "30"; vm.gridH = "30"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.lastResult != nil }), "自定义生成")
        XCTAssertEqual(vm.lastResult?.gridW, 30)
    }

    // T2.11 导出 PDF 含 BOM 页
    func testExportPDFWithBOM() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "30"; vm.gridH = "30"; vm.cellSize = "40"
        vm.generate()
        XCTAssertTrue(waitFor({ self.vm.lastResult != nil }), "生成完成")
        let dest = NSTemporaryDirectory() + "vm_out.pdf"
        try? FileManager.default.removeItem(atPath: dest)
        vm.exportPDF(to: dest)
        // 等待 PDF 写入完成（字节头 %PDF）
        let contentOK = waitFor({
            guard let data = try? Data(contentsOf: URL(fileURLWithPath: dest)) else { return false }
            return data.count > 8 && data.prefix(5).elementsEqual(Data("%PDF-".utf8))
        }, timeout: 30)
        XCTAssertTrue(contentOK, "PDF 应导出且内容有效")
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: dest)) else {
            XCTFail("无法读取 PDF")
            return
        }
        let text = String(decoding: data, as: UTF8.self)
        let pages = text.components(separatedBy: "/Type /Page").count - 1
        XCTAssertGreaterThanOrEqual(pages, 2, "应含 BOM 材料页 + 图纸页（实际 \(pages) 页）")
    }

    // T2.12 长流程稳定性：5 次生成 + 3 次编辑不挂起
    func testLongFlowStability() {
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "30"; vm.gridH = "30"; vm.cellSize = "40"
        var lastPath: String?
        for i in 0..<5 {
            vm.outlineCellOn = (i % 2 == 0)
            vm.generate()
            XCTAssertTrue(waitFor({ self.vm.lastResult != nil
                                    && self.vm.lastResult?.chartPath != lastPath }),
                          "第 \(i + 1) 次生成完成")
            lastPath = vm.lastResult?.chartPath
        }
        vm.editMode = true
        vm.editColorCode = "H1"
        vm.previewGeo = CGSize(width: 800, height: 600)
        vm.fitToWindow = true
        vm.offset = .zero
        var editPath: String?
        let taps: [CGPoint] = [CGPoint(x: 300, y: 300),
                               CGPoint(x: 400, y: 300),
                               CGPoint(x: 500, y: 300)]
        for (i, tap) in taps.enumerated() {
            editPath = vm.lastResult?.chartPath
            vm.handlePreviewTap(location: tap)
            XCTAssertTrue(waitFor({ self.vm.lastResult?.chartPath != editPath
                                    && (self.vm.lastResult?.colorStats["H1"]?.count ?? 0) >= i + 1 }),
                          "第 \(i + 1) 次编辑生效")
        }
        XCTAssertFalse(vm.isBusy, "长流程后不应卡在处理中")
    }
}
