import XCTest
import AppKit
@testable import PerlerApp

/// T8：预览缩放 / 平移 / 钳制数学 + VM previewSize 一致性
final class ZoomPanTests: XCTestCase {

    func testFitDisplaySize() {
        let size = PreviewViewport.displaySize(
            imageSize: CGSize(width: 400, height: 300),
            viewport: CGSize(width: 800, height: 600),
            zoom: 100, fitToWindow: true)
        XCTAssertEqual(size.width, 800, accuracy: 0.001)
        XCTAssertEqual(size.height, 600, accuracy: 0.001)
    }

    func testZoomDisplaySize() {
        let size = PreviewViewport.displaySize(
            imageSize: CGSize(width: 400, height: 300),
            viewport: CGSize(width: 800, height: 600),
            zoom: 200, fitToWindow: false)
        XCTAssertEqual(size.width, 800, accuracy: 0.001)
        XCTAssertEqual(size.height, 600, accuracy: 0.001)

        let size400 = PreviewViewport.displaySize(
            imageSize: CGSize(width: 400, height: 300),
            viewport: CGSize(width: 800, height: 600),
            zoom: 400, fitToWindow: false)
        XCTAssertEqual(size400.width, 1600, accuracy: 0.001)
        XCTAssertEqual(size400.height, 1200, accuracy: 0.001)
    }

    func testFittedZoomPercent() {
        // 400×300 图放进 200×200 视口：scale=0.5 → 50%
        let pct = PreviewViewport.fittedZoomPercent(
            imageSize: CGSize(width: 400, height: 300),
            viewport: CGSize(width: 200, height: 200))
        XCTAssertEqual(pct, 50, accuracy: 0.001)
        // 视口大于图片时按比例放大
        let pct2 = PreviewViewport.fittedZoomPercent(
            imageSize: CGSize(width: 100, height: 100),
            viewport: CGSize(width: 250, height: 250))
        XCTAssertEqual(pct2, 250, accuracy: 0.001)
    }

    func testFittedZoomPercentAllowsBelowManualMin() {
        // 3670×4270 图纸缩进 614×500 视口：fit ≈ 11.7%，不应被手动缩放下限 25% 钳制
        let pct = PreviewViewport.fittedZoomPercent(
            imageSize: CGSize(width: 3670, height: 4270),
            viewport: CGSize(width: 614, height: 500))
        XCTAssertEqual(pct, 500.0 / 4270.0 * 100, accuracy: 0.01)
        XCTAssertLessThan(pct, 25)
    }

    func testClampZoomBounds() {
        XCTAssertEqual(PreviewViewport.clampZoom(1), 25, accuracy: 0.001)
        XCTAssertEqual(PreviewViewport.clampZoom(999), 400, accuracy: 0.001)
        XCTAssertEqual(PreviewViewport.clampZoom(125), 125, accuracy: 0.001)
    }

    func testClampOffsetKeepsSmallImageCentered() {
        let clamped = PreviewViewport.clampOffset(
            CGSize(width: 500, height: -300),
            displaySize: CGSize(width: 100, height: 100),
            viewport: CGSize(width: 400, height: 400))
        XCTAssertEqual(clamped, .zero)
    }

    func testClampOffsetKeepsMinVisibleFraction() {
        let display = CGSize(width: 400, height: 400)
        let viewport = CGSize(width: 200, height: 200)
        // 拖到无穷远：只保留 15% 可见
        let clamped = PreviewViewport.clampOffset(
            CGSize(width: 10_000, height: 10_000),
            displaySize: display, viewport: viewport)
        // 图片左边缘： (200-400)/2 + ox = -100 + ox；可见宽度 = 200 - imgMinX = 15% * 400 = 60
        let imgMinX = (viewport.width - display.width) / 2 + clamped.width
        XCTAssertEqual(viewport.width - imgMinX, 60, accuracy: 0.5)
        let imgMinY = (viewport.height - display.height) / 2 + clamped.height
        XCTAssertEqual(viewport.height - imgMinY, 60, accuracy: 0.5)

        let clampedNeg = PreviewViewport.clampOffset(
            CGSize(width: -10_000, height: -10_000),
            displaySize: display, viewport: viewport)
        let imgMaxX = (viewport.width - display.width) / 2 + clampedNeg.width + display.width
        XCTAssertEqual(imgMaxX, 60, accuracy: 0.5)
    }

    func testAnchoredOffsetAtCenterScalesOffset() {
        let newOffset = PreviewViewport.anchoredOffset(
            currentOffset: CGSize(width: 10, height: 20),
            oldSize: CGSize(width: 400, height: 300),
            newSize: CGSize(width: 800, height: 600),
            anchor: CGPoint(x: 400, y: 300),
            viewport: CGSize(width: 800, height: 600))
        XCTAssertEqual(newOffset.width, 20, accuracy: 0.001)
        XCTAssertEqual(newOffset.height, 40, accuracy: 0.001)
    }

    func testAnchoredOffsetKeepsPointUnderCursor() {
        let viewport = CGSize(width: 800, height: 600)
        let anchor = CGPoint(x: 500, y: 400)
        let oldSize = CGSize(width: 400, height: 300)
        let newSize = CGSize(width: 800, height: 600)
        let oldOffset = CGSize(width: 10, height: 20)
        let newOffset = PreviewViewport.anchoredOffset(
            currentOffset: oldOffset, oldSize: oldSize, newSize: newSize,
            anchor: anchor, viewport: viewport)
        let center = CGPoint(x: viewport.width / 2, y: viewport.height / 2)
        let beforeX = (anchor.x - center.x - oldOffset.width) / oldSize.width
        let afterX = (anchor.x - center.x - newOffset.width) / newSize.width
        XCTAssertEqual(beforeX, afterX, accuracy: 0.0001)
        let beforeY = (anchor.y - center.y - oldOffset.height) / oldSize.height
        let afterY = (anchor.y - center.y - newOffset.height) / newSize.height
        XCTAssertEqual(beforeY, afterY, accuracy: 0.0001)
    }

    func testViewportPointFromPlatePointAccountsForInsetAndTopLeftOrigin() {
        // 图版 644×522，内边距 16 → 预览视口 612×490（左上原点）
        let topLeft = PreviewViewport.viewportPoint(fromPlatePoint: CGPoint(x: 16, y: 16),
                                                    inset: 16)
        XCTAssertEqual(topLeft, .zero)
        let bottomRight = PreviewViewport.viewportPoint(fromPlatePoint: CGPoint(x: 628, y: 506),
                                                        inset: 16)
        XCTAssertEqual(bottomRight.x, 612, accuracy: 0.001)
        XCTAssertEqual(bottomRight.y, 490, accuracy: 0.001)
        // 垂直中线不应镜像
        let center = PreviewViewport.viewportPoint(fromPlatePoint: CGPoint(x: 322, y: 261),
                                                   inset: 16)
        XCTAssertEqual(center.x, 306, accuracy: 0.001)
        XCTAssertEqual(center.y, 245, accuracy: 0.001)
    }

    @MainActor
    func testViewModelPreviewSizeMatchesViewportMath() {
        let vm = AppViewModel()
        vm.previewGeo = CGSize(width: 200, height: 200)
        let image = NSImage(size: NSSize(width: 400, height: 300))

        vm.fitToWindow = true
        let fitted = vm.previewSize(img: image)
        let expectedFit = PreviewViewport.displaySize(
            imageSize: image.size, viewport: vm.previewGeo, zoom: vm.zoom, fitToWindow: true)
        XCTAssertEqual(fitted.width, expectedFit.width, accuracy: 0.001)
        XCTAssertEqual(fitted.height, expectedFit.height, accuracy: 0.001)

        vm.fitToWindow = false
        vm.zoom = 200
        let zoomed = vm.previewSize(img: image)
        let expectedZoom = PreviewViewport.displaySize(
            imageSize: image.size, viewport: vm.previewGeo, zoom: 200, fitToWindow: false)
        XCTAssertEqual(zoomed.width, expectedZoom.width, accuracy: 0.001)
        XCTAssertEqual(zoomed.height, expectedZoom.height, accuracy: 0.001)
    }
}
