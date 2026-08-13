import SwiftUI
import AppKit

/// 无 app bundle 启动（swift run / Xcode 直跑可执行文件）时，
/// 窗口不会成为 key window：输入框能点出焦点圈，但键盘输入会
/// 落到其它应用（终端/Xcode）。这里强制常规激活策略并激活应用。
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
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
}

@main
struct PerlerApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 1100, minHeight: 700)
                .onAppear {
                    NSApp.activate(ignoringOtherApps: true)
                }
        }
        .windowStyle(.titleBar)
    }
}
