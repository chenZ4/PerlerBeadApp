import XCTest
import AppKit
@testable import PerlerApp

/// T4 鲁棒性回归：取消/UTF-8/引用循环/stderr 排空（真实引擎后端）
final class RobustnessTests: XCTestCase {

    private func waitFor(_ cond: @escaping () -> Bool, timeout: TimeInterval = 30) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if cond() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        return false
    }

    private func makeTestImage(_ w: Int = 200, _ h: Int = 150, color: NSColor = .systemRed) -> String {
        let tmp = NSTemporaryDirectory() + "perler_rob_\(UUID().uuidString).png"
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

    // T4.1 取消后晚到响应被忽略，引擎仍存活
    func testCancelIgnoresLateResponse() {
        guard let py = Engine.findPython(), let eng = Engine(pythonPath: py) else {
            XCTFail("未找到 pindou python")
            return
        }
        let src = makeTestImage()
        var rid: Int?
        var completed = false
        let exp = expectation(description: "started")
        eng.request(op: "generate", params: [
            "image_path": src, "grid_w": 250, "grid_h": 250, "cell_size": 40,
        ], onStart: { r in
            rid = r
            exp.fulfill()
        }) { _ in
            completed = true
        }
        wait(for: [exp], timeout: 10)
        guard let rid else {
            XCTFail("未拿到请求 id")
            return
        }
        eng.cancel(requestID: rid)
        // 等待服务端把取消处理完 + 可能的晚到响应
        let deadline = Date().addingTimeInterval(3)
        while Date() < deadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        XCTAssertFalse(completed, "取消后原请求回调不应触发")

        let exp2 = expectation(description: "ping after cancel")
        eng.ping { result in
            if case .success(let ok) = result {
                XCTAssertTrue(ok, "取消后引擎应存活")
            } else {
                XCTFail("取消后引擎无响应")
            }
            exp2.fulfill()
        }
        wait(for: [exp2], timeout: 10)
    }

    // T4.2 UTF-8 分块：大量中文响应（palette_colors）无丢包
    func testUTF8LinesNoDataLoss() {
        guard let py = Engine.findPython(), let eng = Engine(pythonPath: py) else {
            XCTFail("未找到 pindou python")
            return
        }
        let count = 50
        let exp = expectation(description: "all palettes")
        exp.expectedFulfillmentCount = count
        var failures = 0
        for i in 0..<count {
            eng.request(op: "palette_colors", params: ["internal": "mard_221"]) { result in
                switch result {
                case .success(let r):
                    let colors = r["colors"] as? [[Int]] ?? []
                    let names = r["names"] as? [String] ?? []
                    if colors.count != 221 || names.count != 221 {
                        failures += 1
                    }
                case .failure:
                    failures += 1
                }
                if i == 0 { _ = i }
                exp.fulfill()
            }
        }
        wait(for: [exp], timeout: 60)
        XCTAssertEqual(failures, 0, "\(count) 次中文响应应全部完整")
    }

    // T4.3 stderr 排空：大流量 stderr 不阻塞引擎（串行队列饿死回归）
    func testStderrDrained() {
        guard let py = Engine.findPython() else {
            XCTFail("未找到 pindou python")
            return
        }
        let script = NSTemporaryDirectory() + "perler_fake_engine.py"
        let content = """
        import sys
        for _ in range(4000):
            sys.stderr.write("警告" * 60 + "\\n")
        sys.stderr.flush()
        for line in sys.stdin:
            if line.strip():
                print('{"id": 1, "ok": true, "pong": true}')
                sys.stdout.flush()
                break
        """
        try? content.write(toFile: script, atomically: true, encoding: .utf8)
        guard let eng = Engine(pythonPath: py, scriptPath: script) else {
            XCTFail("假引擎启动失败")
            return
        }
        let exp = expectation(description: "ping through stderr flood")
        eng.ping { result in
            if case .success(let ok) = result {
                XCTAssertTrue(ok)
            } else {
                XCTFail("stderr 阻塞导致引擎假死")
            }
            exp.fulfill()
        }
        wait(for: [exp], timeout: 15)
        XCTAssertTrue(eng.engineErrorLog.contains("警告"), "stderr 应被读取")
    }

    // T4.4 VM 编辑期间取消：状态复位且晚到响应不覆盖
    @MainActor
    func testVMCancelDuringEdit() {
        let vm = AppViewModel()
        vm.setup()
        XCTAssertTrue(waitFor({ vm.engine != nil && vm.palettes.count >= 4 }, timeout: 15))
        let src = makeTestImage(300, 300)
        vm.setImagePath(src)
        vm.gridW = "200"; vm.gridH = "200"; vm.cellSize = "40"
        vm.generate()
        XCTAssertTrue(waitFor({ vm.chartImage != nil && !vm.isBusy }, timeout: 60))
        vm.editMode = true
        vm.editColorCode = "H1"
        vm.previewGeo = CGSize(width: 800, height: 600)
        vm.fitToWindow = true
        vm.offset = .zero
        vm.handlePreviewTap(location: CGPoint(x: 400, y: 300))
        XCTAssertTrue(waitFor({ vm.isBusy }), "编辑请求应开始")
        vm.cancelActive()
        XCTAssertFalse(vm.isBusy, "取消后应复位")
        XCTAssertEqual(vm.statusText, "已取消")
        let cancelledStatus = vm.statusText
        let deadline = Date().addingTimeInterval(2)
        while Date() < deadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        XCTAssertEqual(vm.statusText, cancelledStatus, "晚到响应不应覆盖取消状态")
    }

    // T4.5 忙时点击编辑被忽略
    @MainActor
    func testTapIgnoredWhileBusy() {
        let vm = AppViewModel()
        vm.setup()
        XCTAssertTrue(waitFor({ vm.engine != nil && vm.palettes.count >= 4 }, timeout: 15))
        let src = makeTestImage()
        vm.setImagePath(src)
        vm.gridW = "30"; vm.gridH = "30"
        vm.generate()
        XCTAssertTrue(waitFor({ vm.chartImage != nil && !vm.isBusy }, timeout: 60))
        vm.editMode = true
        vm.editColorCode = "H1"
        vm.previewGeo = CGSize(width: 800, height: 600)
        vm.fitToWindow = true
        vm.isBusy = true
        vm.handlePreviewTap(location: CGPoint(x: 400, y: 300))
        XCTAssertEqual(vm.editHistory.count, 0, "忙时点击不应入编辑栈")
        vm.isBusy = false
    }

    // T4.6 undoEdit 后进度持久化（新 VM 重读 track 验证）
    @MainActor
    func testUndoEditPersistsTrack() {
        let src = makeTestImage()
        let vm = AppViewModel()
        vm.setup()
        XCTAssertTrue(waitFor({ vm.engine != nil && vm.palettes.count >= 4 }, timeout: 15))
        vm.setImagePath(src)
        vm.gridW = "40"; vm.gridH = "40"; vm.cellSize = "40"
        vm.generate()
        XCTAssertTrue(waitFor({ vm.chartImage != nil && !vm.isBusy }, timeout: 60))
        vm.editMode = true
        vm.editColorCode = "H1"
        vm.previewGeo = CGSize(width: 800, height: 600)
        vm.fitToWindow = true
        vm.offset = .zero
        vm.handlePreviewTap(location: CGPoint(x: 400, y: 300))
        XCTAssertTrue(waitFor({ vm.editHistory.count == 1 && !vm.isBusy }), "编辑 1 完成")
        vm.handlePreviewTap(location: CGPoint(x: 300, y: 300))
        XCTAssertTrue(waitFor({ vm.editHistory.count == 2 && !vm.isBusy }), "编辑 2 完成")
        XCTAssertEqual(vm.trackedCount, 2)
        vm.undoEdit()
        XCTAssertTrue(waitFor({ vm.editHistory.count == 1 && !vm.isBusy }), "撤销完成")
        XCTAssertEqual(vm.trackedCount, 1)

        // 新 VM 读同一图片路径 → track 恢复为撤销后的 1 格
        let vm2 = AppViewModel()
        vm2.setup()
        XCTAssertTrue(waitFor({ vm2.engine != nil }, timeout: 15))
        vm2.setImagePath(src)
        XCTAssertTrue(waitFor({ vm2.trackedCount == 1 }, timeout: 15),
                      "撤销后的进度应已持久化，实际 tracked=\(vm2.trackedCount)")
    }
}
