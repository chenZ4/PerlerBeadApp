import AppKit
import SwiftUI

// ============================================================================
// R1 定向复验（T10 追加）：滚轮/双指缩放锚点 y 轴镜像是否修复。
//  1) EventCatcherView.isFlipped == true（NSView 坐标 = 左上原点，与 SwiftUI 一致）
//  2) PreviewViewport.viewportPoint(fromPlatePoint:inset:) 正确扣除 16pt padding
//  3) 闭包契约：onZoom(factor, viewportPoint) → applyZoom 锚点语义 = 视口左上坐标
// 真实滚轮事件仍受「合成 NSEvent 无法关联窗口」限制，见报告 R2。
// ============================================================================

enum AnchorProbe {
    @MainActor
    static func run(_ s: ProbeSession) throws -> [String: Any] {
        var out: [String: Any] = [:]
        let catcher = s.findView(in: s.window.contentView, nameContains: "EventCatcherView")
        out["event_catcher_found"] = catcher != nil
        guard let catcher else { return out }

        out["is_flipped"] = catcher.isFlipped
        out["bounds"] = [Double(catcher.bounds.width), Double(catcher.bounds.height)]
        var insetValue: CGFloat = -1
        for child in Mirror(reflecting: catcher).children where child.label == "inset" {
            if let v = child.value as? CGFloat { insetValue = v }
        }
        out["inset"] = Double(insetValue)

        let platePts: [(String, CGPoint)] = [
            ("top_left_corner", CGPoint(x: 0, y: 0)),
            ("viewport_origin", CGPoint(x: insetValue, y: insetValue)),
            ("center", CGPoint(x: catcher.bounds.midX, y: catcher.bounds.midY)),
            ("cursor_20pct_top", CGPoint(x: catcher.bounds.width * 0.3,
                                         y: catcher.bounds.height * 0.2)),
        ]
        var conversions: [[String: Any]] = []
        for (name, p) in platePts {
            let got = PreviewViewport.viewportPoint(fromPlatePoint: p, inset: insetValue)
            let expected = CGPoint(x: p.x - insetValue, y: p.y - insetValue)
            conversions.append([
                "name": name,
                "plate_point": arr(p),
                "product_viewport_point": arr(got),
                "independent_expected": arr(expected),
                "error": arr(CGPoint(x: got.x - expected.x, y: got.y - expected.y)),
            ])
        }
        out["conversion"] = conversions

        guard let onZoom = s.mirrorClosure("onZoom", from: catcher,
                                           as: ((CGFloat, CGPoint) -> Void).self) else {
            out["on_zoom_closure_found"] = false
            return out
        }
        out["on_zoom_closure_found"] = true

        let platePoint = CGPoint(x: catcher.bounds.width * 0.3,
                                 y: catcher.bounds.height * 0.2)
        let viewportPoint = PreviewViewport.viewportPoint(fromPlatePoint: platePoint,
                                                          inset: insetValue)

        s.vm.chartImage = s.synthetic
        s.vm.fitToWindow = false
        s.vm.zoom = 100
        s.vm.offset = .zero
        spin(0.45)
        let pathBefore = s.outDir + "/" + s.phase + "_anchor2_before.png"
        _ = try snapshotContent(s.window, to: pathBefore)
        s.screenshots.append(pathBefore)

        onZoom(2.0, viewportPoint)
        spin(0.55)
        let pathAfter = s.outDir + "/" + s.phase + "_anchor2_after.png"
        _ = try snapshotContent(s.window, to: pathAfter)
        s.screenshots.append(pathAfter)

        let vp = s.viewport
        let cx = vp.width / 2, cy = vp.height / 2
        let expX = (viewportPoint.x - cx) - ((viewportPoint.x - cx) - 0) * 2.0
        let expY = (viewportPoint.y - cy) - ((viewportPoint.y - cy) - 0) * 2.0
        let expectedOffset = CGSize(width: expX, height: expY)
        let actual = s.vm.offset
        let dx = actual.width - expectedOffset.width
        let dy = actual.height - expectedOffset.height
        let mirroredY = (vp.height - viewportPoint.y)
        let counterfactual = (mirroredY - cy) - ((mirroredY - cy) - 0) * 2.0
        out["anchor_zoom"] = [
            "simulated_plate_point": arr(platePoint),
            "passed_viewport_anchor": arr(viewportPoint),
            "expected_offset": arr(expectedOffset),
            "actual_offset": arr(actual),
            "offset_error_points": [Double(dx), Double(dy)],
            "offset_matches_expected": abs(dx) < 0.01 && abs(dy) < 0.01,
            "zoom_after": s.vm.zoom,
            "offset_y_sign": actual.height > 0 ? "positive(正确: 锚点在上半部→图像下移)"
                : (actual.height < 0 ? "negative(镜像 bug 特征)" : "zero"),
            "old_bug_counterfactual_offset_y": Double(counterfactual),
            "interpretation": "y 为正且与独立公式零误差 → 锚点不再上下镜像；若仍镜像应得到旧值",
        ]
        return out
    }
}
