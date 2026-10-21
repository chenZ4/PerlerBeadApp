import AppKit
import SwiftUI

// ============================================================================
// 布局根因探针（T13 附加）：1280×800 下封面内容疑似比窗口宽（右侧 ~30pt 被裁）。
// 用 GeometryReader 读取 SwiftUI 根视图实际分配尺寸，并对比强制 frame 后的版心位置。
// ============================================================================

final class SizeCapture {
    var size: CGSize = .zero
}

enum LayoutProbe {
    @MainActor
    static func run(repoRoot: String, outDir: String) throws -> [String: Any] {
        var out: [String: Any] = [:]
        let capture = SizeCapture()
        let vm = AppViewModel()
        let window = makeWindow(NSSize(width: 1280, height: 800), title: "拼豆图纸", light: true)
        let root = ContentView(vm: vm)
            .background(GeometryReader { g in
                Color.clear.onAppear { capture.size = g.size }
            })
        window.contentView = NSHostingView(rootView: root)
        window.center()
        window.makeKeyAndOrderFront(nil)
        spin(1.2)
        let rep = try snapshotContent(window, to: outDir + "/layout_plain_1280.png")
        let pa = PixelAnalysis(rep)
        var plain: [String: Any] = ["captured_root_size": [Double(capture.size.width), Double(capture.size.height)],
                                    "window_content_size": arr(window.contentView?.bounds.size ?? .zero)]
        if let g = CoverProbe.detectCoverGeom(pa, windowSize: CGSize(width: 1280, height: 800), light: true) {
            plain["separator_x"] = Double(g.separatorX) / pa.scale
            plain["top_rule_bottom"] = Double(g.topRuleBottom) / pa.scale
            plain["bottom_rule_y"] = Double(g.bottomRuleY) / pa.scale
        }
        out["plain"] = plain
        window.close()

        // 强制 1280×800 的根尺寸，再测
        let capture2 = SizeCapture()
        let vm2 = AppViewModel()
        let window2 = makeWindow(NSSize(width: 1280, height: 800), title: "拼豆图纸", light: true)
        let root2 = ContentView(vm: vm2)
            .frame(width: 1280, height: 800)
            .background(GeometryReader { g in
                Color.clear.onAppear { capture2.size = g.size }
            })
        window2.contentView = NSHostingView(rootView: root2)
        window2.center()
        window2.makeKeyAndOrderFront(nil)
        spin(1.2)
        let rep2 = try snapshotContent(window2, to: outDir + "/layout_forced_1280.png")
        let pa2 = PixelAnalysis(rep2)
        var forced: [String: Any] = ["captured_root_size": [Double(capture2.size.width), Double(capture2.size.height)]]
        if let g = CoverProbe.detectCoverGeom(pa2, windowSize: CGSize(width: 1280, height: 800), light: true) {
            forced["separator_x"] = Double(g.separatorX) / pa2.scale
            forced["top_rule_bottom"] = Double(g.topRuleBottom) / pa2.scale
            forced["bottom_rule_y"] = Double(g.bottomRuleY) / pa2.scale
        }
        out["forced_frame_1280"] = forced
        out["interpretation"] = "若 plain 的 root 尺寸 > 1280 且 separator > 849 → ContentView 内部有 ≥1310pt 的最小宽度导致右侧被窗口裁剪；forced 后 separator≈849 则证实"
        window2.close()
        return out
    }
}
