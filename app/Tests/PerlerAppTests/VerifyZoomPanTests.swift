import XCTest
import AppKit
@testable import PerlerApp

/// T10 独立验证：缩放/平移视口数学的独立断言。
///
/// 本文件刻意与 T8 的 ZoomPanTests.swift 分离，期望值全部由「产品代码之外」的
/// 独立几何推导给出（注释保留推导过程），不复用 PreviewViewport 内部实现；
/// 用于交叉验证 T8 修复的数学正确性，而不是重复其自测。
final class VerifyZoomPanTests: XCTestCase {

    // MARK: - 1. 缩放：显示尺寸必须与 zoom 线性（用户可见的比例调节）

    func testZoomDisplaySizeIsLinearInZoom() {
        let image = CGSize(width: 600, height: 450)
        let viewport = CGSize(width: 800, height: 600)
        // 独立期望：display = image × zoom/100
        let at100 = PreviewViewport.displaySize(
            imageSize: image, viewport: viewport, zoom: 100, fitToWindow: false)
        XCTAssertEqual(at100.width, 600, accuracy: 0.001)
        XCTAssertEqual(at100.height, 450, accuracy: 0.001)

        let at200 = PreviewViewport.displaySize(
            imageSize: image, viewport: viewport, zoom: 200, fitToWindow: false)
        XCTAssertEqual(at200.width, 1200, accuracy: 0.001)
        XCTAssertEqual(at200.height, 900, accuracy: 0.001)
        XCTAssertEqual(at200.width / at100.width, 2.0, accuracy: 0.0001)

        let at400 = PreviewViewport.displaySize(
            imageSize: image, viewport: viewport, zoom: 400, fitToWindow: false)
        XCTAssertEqual(at400.width, 2400, accuracy: 0.001)
        XCTAssertEqual(at400.height, 1800, accuracy: 0.001)
        XCTAssertEqual(at400.width / at100.width, 4.0, accuracy: 0.0001)
    }

    func testZoomDisplaySizeWithNonSquareImageKeepsAspect() {
        let image = CGSize(width: 2048, height: 2383)   // 真实图纸降采样后的近方形
        let viewport = CGSize(width: 612, height: 490)
        for zoom in [25.0, 50.0, 100.0, 250.0] {
            let size = PreviewViewport.displaySize(
                imageSize: image, viewport: viewport, zoom: zoom, fitToWindow: false)
            // 独立期望：宽高都按 zoom/100 缩放
            XCTAssertEqual(size.width, image.width * zoom / 100, accuracy: 0.001)
            XCTAssertEqual(size.height, image.height * zoom / 100, accuracy: 0.001)
        }
    }

    // MARK: - 2. fit 模式：显示尺寸 = 视口内最大等比适配（与 zoom 无关）

    func testFitDisplaySizeIgnoresZoom() {
        let image = CGSize(width: 400, height: 300)
        let viewport = CGSize(width: 800, height: 600)
        // 独立期望：scale = min(800/400, 600/300) = 2 → 800×600
        let a = PreviewViewport.displaySize(
            imageSize: image, viewport: viewport, zoom: 25, fitToWindow: true)
        let b = PreviewViewport.displaySize(
            imageSize: image, viewport: viewport, zoom: 400, fitToWindow: true)
        XCTAssertEqual(a.width, 800, accuracy: 0.001)
        XCTAssertEqual(a.height, 600, accuracy: 0.001)
        XCTAssertEqual(a, b)
    }

    func testFitDisplaySizeConstrainedByHeight() {
        let image = CGSize(width: 2048, height: 2383)   // 高比宽大
        let viewport = CGSize(width: 612, height: 490)
        // 独立期望：scale = min(612/2048≈0.29883, 490/2383≈0.20562) = 0.20562
        let expectedScale = min(612.0 / 2048.0, 490.0 / 2383.0)
        let size = PreviewViewport.displaySize(
            imageSize: image, viewport: viewport, zoom: 100, fitToWindow: true)
        XCTAssertEqual(size.height, 2383 * expectedScale, accuracy: 0.001)
        XCTAssertEqual(size.height, 490, accuracy: 0.001)
        XCTAssertEqual(size.width, 2048 * expectedScale, accuracy: 0.001)
    }

    func testFittedZoomPercentReportsRealRatioBelowManualMin() {
        // 真实图纸 2048×2383 放进 612×490 视口：fit ≈ 20.56%，低于手动下限 25%
        // 产品必须如实显示 20.56%（而不是 25%），否则用户看到「比例调节失效/欺骗」
        let pct = PreviewViewport.fittedZoomPercent(
            imageSize: CGSize(width: 2048, height: 2383),
            viewport: CGSize(width: 612, height: 490))
        XCTAssertEqual(pct, 20.5623, accuracy: 0.01)
    }

    // MARK: - 3. 钳制：至少保留 15% 画面可见，且小图居中

    func testClampOffsetZeroWhenImageFitsViewport() {
        // 图 ≤ 视口：不需要平移，强制居中（否则会露出空白）
        let clamped = PreviewViewport.clampOffset(
            CGSize(width: 500, height: -300),
            displaySize: CGSize(width: 400, height: 300),
            viewport: CGSize(width: 800, height: 600))
        XCTAssertEqual(clamped, .zero)
    }

    func testClampOffsetBoundsMatchIndependentGeometry() {
        // 独立推导：display 1200×900，viewport 612×490，minVisible=15%
        // x 轴：可见宽 = 0.15×1200 = 180；offset 上限 = v/2 + i/2 − visible
        //      = 306 + 600 − 180 = 726；下限 = −726
        // y 轴：可见高 = 0.15×900 = 135；上限 = 245 + 450 − 135 = 560；下限 = −560
        let display = CGSize(width: 1200, height: 900)
        let viewport = CGSize(width: 612, height: 490)

        let pos = PreviewViewport.clampOffset(
            CGSize(width: 10_000, height: 10_000),
            displaySize: display, viewport: viewport)
        XCTAssertEqual(pos.width, 726, accuracy: 0.001)
        XCTAssertEqual(pos.height, 560, accuracy: 0.001)

        let neg = PreviewViewport.clampOffset(
            CGSize(width: -10_000, height: -10_000),
            displaySize: display, viewport: viewport)
        XCTAssertEqual(neg.width, -726, accuracy: 0.001)
        XCTAssertEqual(neg.height, -560, accuracy: 0.001)
    }

    func testClampOffsetAtBoundaryKeepsExactly15PercentVisible() {
        let display = CGSize(width: 1200, height: 900)
        let viewport = CGSize(width: 612, height: 490)
        let clamped = PreviewViewport.clampOffset(
            CGSize(width: 999_999, height: 0),
            displaySize: display, viewport: viewport)
        // 图像矩形（视口坐标系）：左 = (v−i)/2 + offset
        let imgLeft = (viewport.width - display.width) / 2 + clamped.width
        let visibleWidth = viewport.width - imgLeft
        XCTAssertEqual(visibleWidth, 0.15 * display.width, accuracy: 0.01)
        // 未超界的轴保持原值（0）
        XCTAssertEqual(clamped.height, 0, accuracy: 0.001)
    }

    func testClampOffsetKeepsInBoundsValueUnchanged() {
        let display = CGSize(width: 1200, height: 900)
        let viewport = CGSize(width: 612, height: 490)
        let clamped = PreviewViewport.clampOffset(
            CGSize(width: 100, height: -80),
            displaySize: display, viewport: viewport)
        XCTAssertEqual(clamped.width, 100, accuracy: 0.001)
        XCTAssertEqual(clamped.height, -80, accuracy: 0.001)
    }

    // MARK: - 4. 锚点缩放：锚点下的图像点缩放前后不动

    func testAnchoredZoomPreservesImagePointUnderAnchor() {
        let viewport = CGSize(width: 800, height: 600)
        let oldSize = CGSize(width: 400, height: 300)
        let newSize = CGSize(width: 800, height: 600)
        let oldOffset = CGSize(width: 10, height: 20)
        let anchor = CGPoint(x: 500, y: 400)
        let newOffset = PreviewViewport.anchoredOffset(
            currentOffset: oldOffset, oldSize: oldSize, newSize: newSize,
            anchor: anchor, viewport: viewport)
        // 独立不变量：锚点处图像归一化坐标 (anchor−center−offset)/size 前后相等
        let cx = viewport.width / 2, cy = viewport.height / 2
        let beforeX = (anchor.x - cx - oldOffset.width) / oldSize.width
        let afterX = (anchor.x - cx - newOffset.width) / newSize.width
        let beforeY = (anchor.y - cy - oldOffset.height) / oldSize.height
        let afterY = (anchor.y - cy - newOffset.height) / newSize.height
        XCTAssertEqual(beforeX, afterX, accuracy: 1e-9)
        XCTAssertEqual(beforeY, afterY, accuracy: 1e-9)
    }

    func testAnchoredZoomAtCenterScalesOffsetByFactor() {
        // 独立推导：锚点=视口中心时，图像中心距锚点距离按 f 缩放 → offset' = offset×f
        let viewport = CGSize(width: 800, height: 600)
        let newOffset = PreviewViewport.anchoredOffset(
            currentOffset: CGSize(width: 10, height: 20),
            oldSize: CGSize(width: 400, height: 300),
            newSize: CGSize(width: 800, height: 600),
            anchor: CGPoint(x: 400, y: 300),     // 中心
            viewport: viewport)
        XCTAssertEqual(newOffset.width, 20, accuracy: 1e-9)
        XCTAssertEqual(newOffset.height, 40, accuracy: 1e-9)
    }

    func testAnchoredZoomOutShrinksOffset() {
        // 200% → 50%（f=0.25）；锚点中心，offset 应缩为 1/4
        let viewport = CGSize(width: 800, height: 600)
        let newOffset = PreviewViewport.anchoredOffset(
            currentOffset: CGSize(width: 80, height: -40),
            oldSize: CGSize(width: 800, height: 600),
            newSize: CGSize(width: 200, height: 150),
            anchor: CGPoint(x: 400, y: 300),
            viewport: viewport)
        XCTAssertEqual(newOffset.width, 20, accuracy: 1e-9)
        XCTAssertEqual(newOffset.height, -10, accuracy: 1e-9)
    }

    // MARK: - 5. 缩放范围与退化输入

    func testClampZoomRange() {
        XCTAssertEqual(PreviewViewport.clampZoom(0), PreviewViewport.minZoom)
        XCTAssertEqual(PreviewViewport.clampZoom(-5), PreviewViewport.minZoom)
        XCTAssertEqual(PreviewViewport.clampZoom(10_000), PreviewViewport.maxZoom)
        XCTAssertEqual(PreviewViewport.clampZoom(175), 175, accuracy: 1e-9)
    }

    func testDegenerateInputsDoNotCrash() {
        let zero = CGSize.zero
        XCTAssertEqual(PreviewViewport.displaySize(
            imageSize: zero, viewport: CGSize(width: 100, height: 100),
            zoom: 100, fitToWindow: false), .zero)
        XCTAssertEqual(PreviewViewport.displaySize(
            imageSize: CGSize(width: 100, height: 100), viewport: zero,
            zoom: 100, fitToWindow: true), .zero)
        XCTAssertEqual(PreviewViewport.clampOffset(
            CGSize(width: 10, height: 10), displaySize: zero, viewport: zero), .zero)
    }

    // MARK: - 6. ViewModel 渲染尺寸一致性（用户实际看到的预览尺寸）

    @MainActor
    func testViewModelPreviewSizeMatchesIndependentMath() {
        let vm = AppViewModel()
        vm.previewGeo = CGSize(width: 612, height: 490)
        let image = NSImage(size: NSSize(width: 600, height: 450))

        // fit：独立期望 = min(612/600, 490/450)=1.02 → 612×459
        vm.fitToWindow = true
        vm.zoom = 400   // fit 模式应忽略 zoom
        let fit = vm.previewSize(img: image)
        XCTAssertEqual(fit.width, 612, accuracy: 0.001)
        XCTAssertEqual(fit.height, 459, accuracy: 0.001)

        // 手动：独立期望 = 600×450 × zoom/100
        vm.fitToWindow = false
        for zoom in [25.0, 50.0, 100.0, 200.0, 400.0] {
            vm.zoom = zoom
            let s = vm.previewSize(img: image)
            XCTAssertEqual(s.width, 600 * zoom / 100, accuracy: 0.001)
            XCTAssertEqual(s.height, 450 * zoom / 100, accuracy: 0.001)
        }
    }
}
