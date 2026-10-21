import AppKit
import SwiftUI

// ============================================================================
// 事件接线探针：合成 NSEvent（NSApp.postEvent + 手动派发）走 app 事件循环，
// 验证键盘快捷键 / 拖拽平移 / 滚轮缩放 / 双指平移的事件路径与状态变化。
// 前置控制组（ControlDragView）用于区分「产品未接线」与「合成事件不可用」。
// ============================================================================

final class DragSink: ObservableObject {
    @Published var translation: CGSize = .zero
    @Published var dragHits = 0
    @Published var keyHits = 0
}

struct ControlDragView: View {
    @ObservedObject var sink: DragSink
    var body: some View {
        Color.orange
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .gesture(DragGesture(minimumDistance: 1)
                .onChanged { v in
                    sink.dragHits += 1
                    sink.translation = v.translation
                })
            .overlay(
                Button("") { sink.keyHits += 1 }
                    .keyboardShortcut("k", modifiers: .command)
                    .opacity(0.001)
                    .frame(width: 0, height: 0)
            )
    }
}

extension ProbeSession {
    // MARK: 事件合成

    func postMouse(_ type: NSEvent.EventType, at p: CGPoint, in window: NSWindow, clickCount: Int = 1) {
        eventNumber += 1
        let isUp = (type == .leftMouseUp)
        guard let ev = NSEvent.mouseEvent(
            with: type, location: p, modifierFlags: [],
            timestamp: ProcessInfo.processInfo.systemUptime,
            windowNumber: window.windowNumber, context: nil,
            eventNumber: eventNumber, clickCount: clickCount,
            pressure: isUp ? 0 : 1) else { return }
        NSApp.postEvent(ev, atStart: false)
    }

    /// delta 为 SwiftUI 坐标（左上原点，y 向下）；内部转换为窗口坐标（y 向上）
    func drag(in window: NSWindow, from p0: CGPoint, delta: CGSize, steps: Int = 8) {
        let dyWin = -delta.height
        postMouse(.leftMouseDown, at: p0, in: window)
        for i in 1...steps {
            let t = CGFloat(i) / CGFloat(steps)
            let p = CGPoint(x: p0.x + delta.width * t, y: p0.y + dyWin * t)
            postMouse(.leftMouseDragged, at: p, in: window)
            spin(0.02)
        }
        postMouse(.leftMouseUp, at: CGPoint(x: p0.x + delta.width, y: p0.y + dyWin), in: window)
        spin(0.25)
    }

    func postKey(_ keyCode: UInt16, chars: String, command: Bool = true, in window: NSWindow) {
        for down in [true, false] {
            eventNumber += 1
            guard let ev = NSEvent.keyEvent(
                with: down ? .keyDown : .keyUp, location: .zero,
                modifierFlags: command ? .command : [],
                timestamp: ProcessInfo.processInfo.systemUptime,
                windowNumber: window.windowNumber, context: nil,
                characters: chars, charactersIgnoringModifiers: chars,
                isARepeat: false, keyCode: keyCode) else { continue }
            NSApp.postEvent(ev, atStart: false)
        }
    }

    /// 滚动/平移事件：CGEvent → NSEvent。返回值的 synthetic_window 说明合成事件是否携带 window。
    func postScroll(deltaY: Int32, deltaX: Int32, precise: Bool,
                    at windowPoint: CGPoint, command: Bool, in window: NSWindow) -> [String: Any] {
        guard let cg = CGEvent(scrollWheelEvent2Source: nil,
                               units: precise ? .pixel : .line,
                               wheelCount: 2, wheel1: deltaY, wheel2: deltaX, wheel3: 0) else {
            return ["posted": false]
        }
        cg.setIntegerValueField(.scrollWheelEventIsContinuous, value: precise ? 1 : 0)
        if command { cg.flags = .maskCommand }
        let frame = window.frame
        cg.location = CGPoint(x: frame.origin.x + windowPoint.x,
                              y: frame.origin.y + windowPoint.y)
        guard let ev = NSEvent(cgEvent: cg) else { return ["posted": false] }
        NSApp.postEvent(ev, atStart: false)
        return ["posted": true, "synthetic_window": ev.window != nil,
                "synthetic_window_number": ev.windowNumber,
                "scrolling_delta_y": Double(ev.scrollingDeltaY),
                "precise": ev.hasPreciseScrollingDeltas]
    }

    // MARK: 查询

    func findView(in root: NSView?, nameContains: String) -> NSView? {
        guard let root else { return nil }
        if String(describing: type(of: root)).contains(nameContains) { return root }
        for sub in root.subviews {
            if let found = findView(in: sub, nameContains: nameContains) { return found }
        }
        return nil
    }

    func mirrorClosure<T>(_ label: String, from object: Any, as type: T.Type) -> T? {
        for child in Mirror(reflecting: object).children where child.label == label {
            if let f = child.value as? T { return f }
        }
        return nil
    }

    func stateSnapshot() -> [String: Any] {
        ["fit_to_window": vm.fitToWindow,
         "zoom": vm.zoom,
         "offset": arr(vm.offset),
         "preview_geo": arr(vm.previewGeo)]
    }

    func resetToFit() {
        vm.fitToWindow = true
        vm.zoom = 100
        vm.offset = .zero
        spin(0.35)
    }
}

enum EventProbe {
    @MainActor
    static func run(_ s: ProbeSession) throws -> [String: Any] {
        var out: [String: Any] = [:]
        out["synthesized_event_notes"] = [
            "鼠标/键盘事件经 NSApp.postEvent 进入 app 事件循环（控制组验证）",
            "CGEvent 生成的 scrollWheel NSEvent 无法关联窗口（AppKit 限制）；若修复代码按 event.window 过滤则收不到，见 synthetic_window 字段",
            "magnify（双指捏合）事件无公开合成 API，仅静态审计 + 人工验收",
        ]

        // ---------- 控制组：证明合成事件通路本身可用 ----------
        let sink = DragSink()
        let ctrl = makeWindow(NSSize(width: 420, height: 320), title: "control", light: true)
        ctrl.contentView = NSHostingView(rootView: ControlDragView(sink: sink))
        ctrl.center()
        ctrl.makeKeyAndOrderFront(nil)
        spin(0.5)
        s.drag(in: ctrl, from: CGPoint(x: 210, y: 160),
               delta: CGSize(width: 80, height: 40))
        spin(0.25)
        s.postKey(40, chars: "k", in: ctrl)   // kVK_ANSI_K
        spin(0.4)
        out["control"] = [
            "drag_hits": sink.dragHits,
            "drag_translation": arr(sink.translation),
            "key_hits": sink.keyHits,
            "interpretation": "drag_hits>0 && key_hits>0 说明合成鼠标/键盘事件可驱动 SwiftUI 手势与快捷键；若为 0，则后续失败归因于事件合成而非产品",
        ]
        ctrl.close()
        s.window.makeKeyAndOrderFront(nil)
        spin(0.45)

        plog("EVENT control done")
        let plate = CGPoint(x: s.refCenter.x, y: s.contentSize.height - s.refCenter.y)
        out["plate_center_window_coords"] = arr(plate)

        // ---------- 1. 键盘快捷键 ----------
        s.resetToFit()
        s.postKey(24, chars: "=", in: s.window)      // ⌘=
        spin(0.5)
        out["key_zoom_in"] = s.stateSnapshot()

        s.resetToFit()
        s.postKey(27, chars: "-", in: s.window)      // ⌘-
        spin(0.5)
        out["key_zoom_out"] = s.stateSnapshot()

        s.resetToFit()
        s.vm.fitToWindow = false
        s.vm.zoom = 300
        s.vm.offset = CGSize(width: 60, height: 40)
        spin(0.4)
        s.postKey(29, chars: "0", in: s.window)      // ⌘0
        spin(0.5)
        out["key_reset"] = s.stateSnapshot()
        plog("EVENT keyboard done")

        // ---------- 2. 滚轮缩放 / 双指平移 ----------
        s.resetToFit()
        s.vm.fitToWindow = false
        s.vm.zoom = 200
        spin(0.35)
        let beforeWheel = s.stateSnapshot()
        let wheelPost = s.postScroll(deltaY: 10, deltaX: 0, precise: false,
                                     at: plate, command: false, in: s.window)
        spin(0.55)
        out["wheel_zoom"] = ["post": wheelPost, "before": beforeWheel, "after": s.stateSnapshot()]

        s.resetToFit()
        s.vm.fitToWindow = false
        s.vm.zoom = 200
        spin(0.35)
        let beforePan = s.stateSnapshot()
        let panPost = s.postScroll(deltaY: -30, deltaX: 40, precise: true,
                                   at: plate, command: false, in: s.window)
        spin(0.55)
        out["two_finger_pan"] = ["post": panPost, "before": beforePan, "after": s.stateSnapshot()]
        plog("EVENT wheel done")

        // ---------- 3. 拖拽平移（真实 SwiftUI DragGesture 路径） ----------
        s.resetToFit()
        s.vm.fitToWindow = false
        s.vm.zoom = 200
        s.vm.offset = .zero
        spin(0.35)
        s.drag(in: s.window, from: plate, delta: CGSize(width: 60, height: 40))
        spin(0.35)
        out["drag_pan_zoom200"] = ["expected_offset": [60.0, 40.0], "after": s.stateSnapshot()]

        // fit 状态下拖拽：修复后应自动切出 fit 且偏移生效（fit→manual 不跳变）
        s.resetToFit()
        s.drag(in: s.window, from: plate, delta: CGSize(width: 80, height: 60))
        spin(0.35)
        out["drag_from_fit"] = ["expected_offset": [80.0, 60.0], "after": s.stateSnapshot()]

        // 极端拖拽：基线无钳制可把图拖丢；修复后至少保留 15% 可见
        s.resetToFit()
        s.vm.fitToWindow = false
        s.vm.zoom = 200
        s.vm.offset = .zero
        spin(0.35)
        for _ in 0..<5 {
            s.drag(in: s.window, from: plate,
                   delta: CGSize(width: 400, height: 400), steps: 5)
        }
        spin(0.45)
        let extremePath = s.outDir + "/\(s.phase)_event_drag_extreme.png"
        let rep = try snapshotContent(s.window, to: extremePath)
        s.screenshots.append(extremePath)
        let pa = PixelAnalysis(rep)
        let magenta = pa.count(matching: isMagenta)
        let (_, display, _, _, _, _) = s.expectedGeometry(
            for: RenderState(name: "drag_extreme", fit: false, zoom: 200, offset: .zero))
        let totalPx = display.width * display.height * pa.scale * pa.scale
        out["drag_extreme"] = [
            "after": s.stateSnapshot(),
            "visible_magenta_px": magenta,
            "display_area_px": Double(totalPx),
            "visible_fraction": totalPx > 0 ? Double(magenta) / Double(totalPx) : 0,
            "screenshot": extremePath,
            "interpretation": "钳制生效时 visible_fraction 应 >= 0.15（至少保留 15% 画面）",
        ]
        plog("EVENT drag done")

        // ---------- 4. EventCatcherView 与事件闭包链（T8 新增） ----------
        s.resetToFit()
        let catcher = s.findView(in: s.window.contentView, nameContains: "EventCatcherView")
        out["event_catcher"] = ["found": catcher != nil]
        if let catcher {
            var info: [String: Any] = [
                "class": String(describing: type(of: catcher)),
                "bounds": [Double(catcher.bounds.width), Double(catcher.bounds.height)],
                "frame": arr(catcher.frame),
                "is_hidden": catcher.isHidden,
                "hit_test_is_nil": catcher.hitTest(CGPoint(x: catcher.bounds.midX,
                                                           y: catcher.bounds.midY)) == nil,
                "expected_plate_size_points": [Double(s.viewport.width), Double(s.viewport.height)],
            ]
            let onZoom = s.mirrorClosure("onZoom", from: catcher,
                                         as: ((CGFloat, CGPoint) -> Void).self)
            let onPan = s.mirrorClosure("onPan", from: catcher,
                                        as: ((CGSize) -> Void).self)
            info["on_zoom_closure_found"] = onZoom != nil
            info["on_pan_closure_found"] = onPan != nil
            if let onZoom {
                s.vm.fitToWindow = false
                s.vm.zoom = 200
                s.vm.offset = .zero
                spin(0.35)
                onZoom(1.25, CGPoint(x: s.viewport.width / 2, y: s.viewport.height / 2))
                spin(0.5)
                info["on_zoom_result"] = s.stateSnapshot()
                let path = s.outDir + "/\(s.phase)_event_onzoom_250.png"
                _ = try? snapshotContent(s.window, to: path)
                s.screenshots.append(path)
            }
            if let onPan {
                s.vm.fitToWindow = false
                s.vm.zoom = 200
                s.vm.offset = .zero
                spin(0.35)
                onPan(CGSize(width: 40, height: 20))
                spin(0.5)
                info["on_pan_result"] = s.stateSnapshot()
            }
            out["event_catcher"] = info
        }
        plog("EVENT catcher done")

        // ---------- 5. 锚点缩放数学（NSView 左上/左下坐标系一致性） ----------
        s.vm.fitToWindow = false
        s.vm.zoom = 100
        s.vm.offset = .zero
        spin(0.45)
        let preZoomPath = s.outDir + "/\(s.phase)_anchor_pre.png"
        let preRep = try snapshotContent(s.window, to: preZoomPath)
        s.screenshots.append(preZoomPath)
        let prePA = PixelAnalysis(preRep)
        let preBB = prePA.bbox(matching: isMagenta).map { prePA.points($0) }
        if let onZoom = catcher.flatMap({ s.mirrorClosure("onZoom", from: $0,
                                                          as: ((CGFloat, CGPoint) -> Void).self) }),
           let preBB {
            // 锚点：视口内 30% 宽 / 70% 高（NSView 坐标，左下原点）
            let anchorNS = CGPoint(x: s.viewport.width * 0.3, y: s.viewport.height * 0.7)
            onZoom(2.0, anchorNS)
            spin(0.55)
            let postPath = s.outDir + "/\(s.phase)_anchor_post.png"
            let postRep = try snapshotContent(s.window, to: postPath)
            s.screenshots.append(postPath)
            let postPA = PixelAnalysis(postRep)
            let postBB = postPA.bbox(matching: isMagenta).map { postPA.points($0) }
            let anchorSwiftUI = CGPoint(x: anchorNS.x, y: s.viewport.height - anchorNS.y)
            var anchorErr: [Double] = []
            var postOriginArr: Any = NSNull()
            if let postBB2 = postBB {
                let preOrigin = CGPoint(x: preBB.minX, y: preBB.minY)
                let postOrigin = CGPoint(x: postBB2.minX, y: postBB2.minY)
                postOriginArr = arr(postOrigin)
                let f = 2.0
                let expX = anchorSwiftUI.x - (anchorSwiftUI.x - preOrigin.x) * f
                let expYTop = anchorSwiftUI.y - (anchorSwiftUI.y - preOrigin.y) * f
                anchorErr = [Double(postOrigin.x - expX), Double(postOrigin.y - expYTop)]
            }
            out["anchor_zoom"] = [
                "anchor_nsview_coords": arr(anchorNS),
                "anchor_swiftui_coords": arr(anchorSwiftUI),
                "pre_image_origin": arr(CGPoint(x: preBB.minX, y: preBB.minY)),
                "post_image_origin": postOriginArr,
                "expected_origin_error_points": anchorErr,
                "after": s.stateSnapshot(),
                "interpretation": "error≈0 → 锚点语义正确；y 方向误差大 → NSView(左下原点)与 SwiftUI(左上)坐标未换算",
            ]
        } else {
            out["anchor_zoom"] = ["skipped": "无 EventCatcherView/onZoom 或参考 bbox 缺失"]
        }
        plog("EVENT anchor done")

        s.resetToFit()
        out["monitor_hits"] = s.monitorHits
        return out
    }
}
