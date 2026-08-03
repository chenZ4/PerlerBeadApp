import XCTest
@testable import PerlerApp

/// 核心回归：色卡正确性 / 编辑生效 / finished 可用
final class RegressionTests: XCTestCase {

    var engine: Engine?

    override func setUp() {
        super.setUp()
        guard let py = Engine.findPython() else {
            XCTFail("未找到 pindou python")
            return
        }
        engine = Engine(pythonPath: py)
    }

    override func tearDown() {
        engine = nil
        super.tearDown()
    }

    private func makeTestImage(_ w: Int = 120, _ h: Int = 90) -> String {
        let tmp = NSTemporaryDirectory() + "perler_reg_\(UUID().uuidString).png"
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

    private func waitFor(_ cond: @escaping () -> Bool, timeout: TimeInterval = 60) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if cond() { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        return false
    }

    /// 引擎响应按回调执行（闭包驱动）
    private func request(_ op: String, _ params: [String: Any],
                         completion: @escaping (Result<[String: Any], Error>) -> Void) {
        engine?.request(op: op, params: params, completion: completion)
    }

    func testGenerateUsesCorrectPalette() {
        // 关键回归：generate 必须使用 221 色卡（而非 fallback 8 色）
        let src = makeTestImage()
        let done = expectation(description: "gen")
        var stats: [String: ColorStat] = [:]
        request("generate", ["image_path": src, "grid_w": 30, "grid_h": 30,
                             "cell_size": 40, "palette": "mard_221"]) { result in
            if case .success(let r) = result,
               let data = try? JSONSerialization.data(withJSONObject: r),
               let g = try? JSONDecoder().decode(GenerateResult.self, from: data) {
                stats = g.colorStats
            } else {
                XCTFail("generate 失败")
            }
            done.fulfill()
        }
        wait(for: [done], timeout: 60)
        // 断言：映射色号必须属于 221 色卡（fallback 8 色的色号是 A1-A8 且 ≤8 种）
        let codesDone = expectation(description: "codes")
        var validCodes: Set<String> = []
        request("palette_colors", ["internal": "mard_221"]) { result in
            if case .success(let r) = result {
                validCodes = Set(r["codes"] as? [String] ?? [])
            }
            codesDone.fulfill()
        }
        wait(for: [codesDone], timeout: 30)
        XCTAssertFalse(stats.isEmpty, "应有映射结果")
        let invalid = stats.keys.filter { !validCodes.contains($0) }
        XCTAssertTrue(invalid.isEmpty,
                      "色号不属于 221 色卡（fallback 泄漏）：\(invalid)")
        XCTAssertTrue(stats.keys.count <= 221)
        // 响应应包含 finished_path（成品图可用）
        let genDone = expectation(description: "gen2")
        var finishedPath: String?
        request("generate", ["image_path": src, "grid_w": 30, "grid_h": 30,
                             "cell_size": 40, "palette": "MARD 221 色"]) { result in
            if case .success(let r) = result {
                finishedPath = r["finished_path"] as? String
            }
            genDone.fulfill()
        }
        wait(for: [genDone], timeout: 60)
        XCTAssertNotNil(finishedPath, "finished_path 必须返回")
        XCTAssertTrue(FileManager.default.fileExists(atPath: finishedPath ?? ""),
                      "finished 文件必须存在")
    }

    func testEditTakesEffect() {
        // 关键回归：编辑覆盖必须真实生效（目标色计数 > 0）
        let src = makeTestImage()
        var gridW = 0
        let g1 = expectation(description: "g1")
        request("generate", ["image_path": src, "grid_w": 30, "grid_h": 30,
                             "cell_size": 40, "palette": "mard_221"]) { result in
            if case .success(let r) = result {
                gridW = r["grid_w"] as? Int ?? 0
            }
            g1.fulfill()
        }
        wait(for: [g1], timeout: 60)

        let g2 = expectation(description: "g2")
        var statsAfter: [String: ColorStat] = [:]
        request("edit", ["image_path": src, "grid_w": gridW, "grid_h": gridW,
                         "cell_size": 40, "palette": "mard_221",
                         "overrides": [["x": 5, "y": 5, "code": "H1"]]]) { result in
            if case .success(let r) = result,
               let data = try? JSONSerialization.data(withJSONObject: r),
               let g = try? JSONDecoder().decode(GenerateResult.self, from: data) {
                statsAfter = g.colorStats
            } else {
                XCTFail("edit 失败: \(result)")
            }
            g2.fulfill()
        }
        wait(for: [g2], timeout: 60)
        XCTAssertGreaterThan(statsAfter["H1"]?.count ?? 0, 0,
                             "编辑后 H1（白色）应出现且计数 > 0")
    }
}
