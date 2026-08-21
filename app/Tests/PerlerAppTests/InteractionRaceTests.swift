import XCTest
import AppKit
@testable import PerlerApp

/// P0 交互竞态修复回归：
/// - 拖拽偏移多次手势累加不回跳
/// - 换图递增归属代币，迟到结果不污染新图状态
/// - track_load 回显 key，晚到响应不覆盖当前进度
/// - onStart 同步登记 rid，generate 返回后立即取消有效
final class InteractionRaceTests: XCTestCase {

    private func waitFor(_ cond: @escaping () -> Bool, timeout: TimeInterval = 30) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if cond() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        return false
    }

    private func makeTestImage(_ w: Int = 300, _ h: Int = 300) -> String {
        let tmp = NSTemporaryDirectory() + "perler_race_\(UUID().uuidString).png"
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w,
                                         pixelsHigh: h, bitsPerSample: 8,
                                         samplesPerPixel: 4, hasAlpha: true,
                                         isPlanar: false, colorSpaceName: .deviceRGB,
                                         bytesPerRow: 0, bitsPerPixel: 0),
              let ctx = NSGraphicsContext(bitmapImageRep: rep) else { return tmp }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = ctx
        NSColor.systemBlue.setFill()
        NSBezierPath(rect: NSRect(x: 0, y: 0, width: w, height: h)).fill()
        NSGraphicsContext.restoreGraphicsState()
        if let png = rep.representation(using: .png, properties: [:]) {
            try? png.write(to: URL(fileURLWithPath: tmp))
        }
        return tmp
    }

    // R1.1 两次拖拽：第二次从第一次终点继续（旧实现会跳回起点）
    @MainActor
    func testDragAccumulatesAcrossGestures() {
        let vm = AppViewModel()
        vm.offset = .zero
        vm.dragChanged(CGSize(width: 50, height: 30))
        XCTAssertEqual(vm.offset.width, 50)
        XCTAssertEqual(vm.offset.height, 30)
        vm.dragEnded()
        vm.dragChanged(CGSize(width: -20, height: 10))
        XCTAssertEqual(vm.offset.width, 30, "第二次拖拽应从上次终点累加")
        XCTAssertEqual(vm.offset.height, 40)
        vm.dragEnded()
    }

    // R1.2 双击复位清掉拖拽基准：复位后新手势以零为基准
    @MainActor
    func testResetPreviewClearsDragBase() {
        let vm = AppViewModel()
        vm.dragChanged(CGSize(width: 100, height: 0))
        vm.resetPreviewOffset()
        XCTAssertEqual(vm.offset, .zero)
        vm.dragChanged(CGSize(width: 10, height: 5))
        XCTAssertEqual(vm.offset.width, 10, "复位后新手势不应继承旧基准")
        XCTAssertEqual(vm.offset.height, 5)
    }

    // R1.3 换图递增归属代币
    @MainActor
    func testEpochBumpsOnImageChange() {
        let vm = AppViewModel()
        vm.setImagePath(makeTestImage())
        let e1 = vm.imageEpoch
        vm.setImagePath(makeTestImage())
        XCTAssertEqual(vm.imageEpoch, e1 + 1, "换图必须递增代币")
    }

    // R1.4 生成进行中换图：迟到的成功结果不得应用（chartImage 保持空）
    @MainActor
    func testLateResultNotAppliedAfterImageSwitch() {
        let vm = AppViewModel()
        vm.setup()
        XCTAssertTrue(waitFor({ vm.engine != nil && vm.palettes.count >= 4 }, timeout: 15))
        vm.setImagePath(makeTestImage())
        vm.gridW = "250"; vm.gridH = "250"; vm.cellSize = "40"
        vm.generate()
        XCTAssertTrue(waitFor({ vm.isBusy }), "生成应开始")
        vm.setImagePath(makeTestImage())  // 生成中换图 → 代币递增
        XCTAssertNil(vm.chartImage)
        XCTAssertTrue(waitFor({ !vm.isBusy }, timeout: 120), "旧请求最终应结束")
        let deadline = Date().addingTimeInterval(2)
        while Date() < deadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        XCTAssertNil(vm.chartImage, "迟到结果不得覆盖新图状态")
        XCTAssertNil(vm.lastResult, "迟到结果不得写入 lastResult")
    }

    // R1.5 track_load 响应回显 key（协议契约）
    func testTrackLoadEchoesKey() {
        guard let py = Engine.findPython(), let eng = Engine(pythonPath: py) else {
            XCTFail("未找到 pindou python")
            return
        }
        defer {
            let path = "track/echo_test_key.json"
            try? FileManager.default.removeItem(atPath: path)
        }
        let exp = expectation(description: "echo")
        eng.request(op: "track_save", params: ["key": "echo_test_key",
                                               "cells": ["1:1", "2:2"]]) { _ in
            eng.request(op: "track_load", params: ["key": "echo_test_key"]) { result in
                if case .success(let r) = result {
                    XCTAssertEqual(r["key"] as? String, "echo_test_key", "响应必须回显 key")
                    XCTAssertEqual(Set(r["track"] as? [String] ?? []),
                                   Set(["1:1", "2:2"]))
                } else {
                    XCTFail("track_load 失败")
                }
                exp.fulfill()
            }
        }
        wait(for: [exp], timeout: 15)
    }

    // R1.6 generate() 返回后立即取消：onStart 已同步登记 rid，取消必然生效
    @MainActor
    func testCancelRightAfterGenerateIsEffective() {
        let vm = AppViewModel()
        vm.setup()
        XCTAssertTrue(waitFor({ vm.engine != nil && vm.palettes.count >= 4 }, timeout: 15))
        vm.setImagePath(makeTestImage())
        vm.gridW = "250"; vm.gridH = "250"; vm.cellSize = "40"
        vm.generate()
        vm.cancelActive()  // 不等待任何异步派发，直接取消
        XCTAssertFalse(vm.isBusy)
        XCTAssertEqual(vm.statusText, "已取消")
        // 等待服务端处理完取消 + 可能的晚到消息
        let deadline = Date().addingTimeInterval(3)
        while Date() < deadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        XCTAssertEqual(vm.statusText, "已取消", "晚到消息不得覆盖取消状态")
        XCTAssertNil(vm.chartImage)

        let exp = expectation(description: "engine alive")
        vm.engine?.ping { result in
            if case .failure = result {
                XCTFail("取消后引擎应存活")
            }
            exp.fulfill()
        }
        wait(for: [exp], timeout: 10)
    }
}
