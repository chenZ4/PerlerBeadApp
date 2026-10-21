import SwiftUI
import AppKit

/// 无 app bundle 启动（swift run / Xcode 直跑可执行文件）时，
/// 窗口不会成为 key window：输入框能点出焦点圈，但键盘输入会
/// 落到其它应用（终端/Xcode）。这里强制常规激活策略并激活应用。
///
/// 另提供两个仅用于 QA 截图的环境变量（不影响正常使用）：
///   PERLER_APPEARANCE = light | dark   强制外观
///   PERLER_WINDOW_SIZE = 1280x800      设置内容区尺寸
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        applyQAAppearance()
        applyQAWindowSize()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication,
                                       hasVisibleWindows flag: Bool) -> Bool {
        NSApp.activate(ignoringOtherApps: true)
        return true
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        if let window = NSApp.windows.first(where: { $0.canBecomeKey }),
           !window.isKeyWindow {
            window.makeKeyAndOrderFront(nil)
        }
    }

    private func applyQAAppearance() {
        guard let style = ProcessInfo.processInfo.environment["PERLER_APPEARANCE"]?
            .lowercased() else { return }
        switch style {
        case "light": NSApp.appearance = NSAppearance(named: .aqua)
        case "dark": NSApp.appearance = NSAppearance(named: .darkAqua)
        default: break
        }
    }

    private func applyQAWindowSize() {
        guard let spec = ProcessInfo.processInfo.environment["PERLER_WINDOW_SIZE"] else { return }
        let parts = spec.lowercased().split(separator: "x")
        guard parts.count == 2,
              let w = Double(parts[0]), let h = Double(parts[1]),
              w > 400, h > 300 else { return }
        // 窗口可能晚于 applicationDidFinishLaunching 创建：重试直到找到内容窗口
        var attempts = 0
        func tryApply() {
            attempts += 1
            if let window = NSApp.windows.first(where: { $0.canBecomeKey && $0.isVisible }) {
                window.setContentSize(NSSize(width: w, height: h))
                window.center()
                window.title = "拼豆图纸"
                return
            }
            if attempts < 12 {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { tryApply() }
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { tryApply() }
    }
}

@main
struct PerlerApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 1100, minHeight: 700)
                .background(Tok.paper)
                .onAppear {
                    NSApp.activate(ignoringOtherApps: true)
                }
        }
        .windowStyle(.titleBar)
        .defaultSize(width: 1280, height: 800)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
    }
}