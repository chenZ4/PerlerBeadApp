import XCTest
@testable import PerlerApp

final class EngineTests: XCTestCase {

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

    func testPing() {
        let exp = expectation(description: "ping")
        engine?.ping { result in
            if case .success(let ok) = result {
                XCTAssertTrue(ok)
            } else {
                XCTFail("ping 失败")
            }
            exp.fulfill()
        }
        wait(for: [exp], timeout: 10)
    }

    func testPalettes() {
        let exp = expectation(description: "palettes")
        engine?.request(op: "palettes", params: [:]) { result in
            switch result {
            case .success(let r):
                let arr = r["palettes"] as? [[String: Any]] ?? []
                XCTAssertGreaterThanOrEqual(arr.count, 4)
            case .failure(let e):
                XCTFail("palettes 失败: \(e)")
            }
            exp.fulfill()
        }
        wait(for: [exp], timeout: 10)
    }

    func testEffectsList() {
        let exp = expectation(description: "effects")
        engine?.request(op: "effects", params: [:]) { result in
            switch result {
            case .success(let r):
                let effects = r["effects"] as? [String: Any] ?? [:]
                XCTAssertGreaterThanOrEqual(effects.count, 8)
            case .failure(let e):
                XCTFail("effects 失败: \(e)")
            }
            exp.fulfill()
        }
        wait(for: [exp], timeout: 10)
    }

    func testGenerateAndExport() {
        // 生成一张临时测试图
        let tmp = NSTemporaryDirectory() + "perler_swift_\(UUID().uuidString).png"
        let size = NSSize(width: 120, height: 90)
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 120,
                                         pixelsHigh: 90, bitsPerSample: 8,
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
        NSBezierPath(rect: NSRect(x: 0, y: 0, width: 120, height: 90)).fill()
        NSGraphicsContext.restoreGraphicsState()
        guard let png = rep.representation(using: .png, properties: [:]) else {
            XCTFail("PNG 编码失败")
            return
        }
        try? png.write(to: URL(fileURLWithPath: tmp))

        let exp = expectation(description: "generate")
        var gen: GenerateResult?
        engine?.request(op: "generate", params: [
            "image_path": tmp,
            "grid_w": 40,
            "grid_h": 40,
            "cell_size": 40,
            "show_finished": true,
            "effects": [["id": "outline_cell", "params": [:] as [String: Any]]],
        ]) { result in
            switch result {
            case .success(let r):
                guard let data = try? JSONSerialization.data(withJSONObject: r),
                      let g = try? JSONDecoder().decode(GenerateResult.self, from: data) else {
                    XCTFail("解码失败")
                    break
                }
                gen = g
                XCTAssertEqual(g.gridW, 40)
                XCTAssertTrue(FileManager.default.fileExists(atPath: g.chartPath))
            case .failure(let e):
                XCTFail("generate 失败: \(e)")
            }
            exp.fulfill()
        }
        wait(for: [exp], timeout: 60)

        guard let result = gen else { return }
        let exp2 = expectation(description: "export")
        engine?.request(op: "export_pdf", params: [
            "source_path": result.chartPath,
            "save_path": NSTemporaryDirectory() + "swift_out.pdf",
            "mode": "a4",
            "cell_size": result.cellSize,
            "bom": result.colorStatsAny,
        ]) { res in
            switch res {
            case .success(let r):
                let p = r["save_path"] as? String ?? ""
                XCTAssertTrue(FileManager.default.fileExists(atPath: p))
            case .failure(let e):
                XCTFail("export_pdf 失败: \(e)")
            }
            exp2.fulfill()
        }
        wait(for: [exp2], timeout: 60)
    }
}
