import AppKit
import SwiftUI

// ============================================================================
// 手势叠加最小复现：验证 ContentView.plate 上「两个 .gesture 叠加」是否导致
// 非编辑模式下 dragGesture 失效（基线 / 修复前根因证据）。
// 复现的是产品代码结构：
//   .gesture(dragGesture, including: editMode ? .none : .all)
//   .gesture(editGesture, including: editMode ? .all  : .none)
// 对照：仅单个 .gesture(dragGesture)。
// ============================================================================

final class GestureCounters: ObservableObject {
    @Published var drags: [String: Int] = [:]
    func hit(_ name: String) { drags[name, default: 0] += 1 }
}

struct ReproPane: View {
    let name: String
    let variant: Int          // 0=单个 drag; 1=双 .gesture(产品结构); 2=双 gesture + 双击; 3=双 gesture + 双击 + onDrop
    @ObservedObject var counters: GestureCounters

    private var dragG: some Gesture {
        DragGesture(minimumDistance: 1)
            .onChanged { _ in counters.hit(name) }
    }
    private var tapG: some Gesture {
        SpatialTapGesture().onEnded { _ in counters.hit(name + "_tap") }
    }

    @ViewBuilder
    var body: some View {
        let base = ZStack {
            Rectangle().fill(variant == 0 ? Color.orange
                             : (variant == 1 ? Color.purple
                                : (variant == 2 ? Color.teal : Color.brown)))
            Text(name).font(.caption).foregroundStyle(.white)
        }
        .clipped()
        .contentShape(Rectangle())

        switch variant {
        case 0:
            base.gesture(dragG, including: .all)
        case 1:
            base
                .gesture(dragG, including: .all)
                .gesture(tapG, including: .none)
        case 2:
            base
                .gesture(dragG, including: .all)
                .gesture(tapG, including: .none)
                .onTapGesture(count: 2) { }
        default:
            base
                .gesture(dragG, including: .all)
                .gesture(tapG, including: .none)
                .onTapGesture(count: 2) { }
                .onDrop(of: [.fileURL], isTargeted: nil) { _ in false }
        }
    }
}

enum GestureRepro {
    @MainActor
    static func run(_ s: ProbeSession) -> [String: Any] {
        let counters = GestureCounters()
        let window = makeWindow(NSSize(width: 500, height: 340), title: "gesture-repro", light: true)
        let root = VStack(spacing: 0) {
            ReproPane(name: "A_single_drag", variant: 0, counters: counters)
            ReproPane(name: "B_two_gestures", variant: 1, counters: counters)
            ReproPane(name: "C_two_tap2", variant: 2, counters: counters)
            ReproPane(name: "D_two_tap2_drop", variant: 3, counters: counters)
        }
        window.contentView = NSHostingView(rootView: root)
        window.center()
        window.makeKeyAndOrderFront(nil)
        spin(0.6)

        // 每个象限中心（窗口坐标，bottom-left）；4 行等高 340/4=85
        let xs: CGFloat = 250
        let ys: [CGFloat] = [340 - 42, 340 - 127, 340 - 212, 340 - 297]
        for y in ys {
            s.drag(in: window, from: CGPoint(x: xs, y: y),
                   delta: CGSize(width: 60, height: 30), steps: 6)
            spin(0.15)
        }
        spin(0.4)
        let result: [String: Any] = [
            "counters": counters.drags,
            "interpretation": "A_single_drag>0 但 B/C/D=0 → 第二个 .gesture(including: .none) 叠加会吞掉内层拖拽手势（产品 plate 根因）；若全为 0 则复现环境异常",
            "variants": [
                "A_single_drag": "仅 .gesture(drag, .all)",
                "B_two_gestures": ".gesture(drag,.all) + .gesture(tap,.none)（产品结构，非编辑模式）",
                "C_two_tap2": "B + .onTapGesture(count:2)",
                "D_two_tap2_drop": "C + .onDrop（最接近产品 plate）",
            ],
        ]
        window.close()
        s.window.makeKeyAndOrderFront(nil)
        spin(0.3)
        return result
    }
}
