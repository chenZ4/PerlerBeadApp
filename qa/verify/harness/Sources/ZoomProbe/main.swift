import AppKit

// 独立验证离屏探针入口（同步执行：手动跑 RunLoop + 手动派发事件）
// 用法: ZoomProbe pre|post   （pre=git HEAD 基线源码, post=当前工作区源码；源码由 prepare_sources.sh 准备）

@main
struct ZoomProbeCLI {
    static func main() {
        let phase = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "pre"
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        app.finishLaunching()

        var exitCode: Int32 = 0
        MainActor.assumeIsolated {
            do {
                let root = repoRootFromEnv()
                let outDir = root + "/qa/verify/evidence"
                try ensureDir(outDir)
                plog("SETUP start phase=\(phase) root=\(root)")
                if phase == "anchor" {
                    let session = ProbeSession(repoRoot: root, outDir: outDir, phase: phase)
                    try session.setUp()
                    let anchor = try AnchorProbe.run(session)
                    try writeJSON(["phase": phase, "anchor": anchor, "notes": session.notes],
                                  to: outDir + "/anchor_probe.json")
                    print("PROBE DONE phase=anchor")
                    fflush(stdout)
                    exit(0)
                }
                if phase == "theme" {
                    let theme = try ThemeProbe.run(repoRoot: root, outDir: outDir)
                    let result: [String: Any] = ["phase": phase, "theme": theme]
                    try writeJSON(result, to: outDir + "/theme_probe.json")
                    print("PROBE DONE phase=theme json=\(outDir)/theme_probe.json")
                    fflush(stdout)
                    exit(0)
                }
                let session = ProbeSession(repoRoot: root, outDir: outDir, phase: phase)
                try session.setUp()
                plog("SETUP done viewport=\(session.viewport) refCenter=\(session.refCenter)")

                let render = try RenderProbe.run(session)
                plog("RENDER done")
                let realChart = try RealChartProbe.run(session)
                plog("REAL done")
                let gestureRepro = GestureRepro.run(session)
                plog("GESTURE REPRO done")
                let events = try EventProbe.run(session)
                plog("EVENTS done")

                let result: [String: Any] = [
                    "phase": phase,
                    "repo_root": root,
                    "render": render,
                    "real_chart": realChart,
                    "gesture_repro": gestureRepro,
                    "events": events,
                    "notes": session.notes,
                ]
                try writeJSON(result, to: outDir + "/\(phase)_probe.json")
                print("PROBE DONE phase=\(phase) json=\(outDir)/\(phase)_probe.json")
                fflush(stdout)
            } catch {
                FileHandle.standardError.write(
                    ("PROBE ERROR: \(error.localizedDescription)\u{0A}").data(using: .utf8)!)
                print("PROBE FAILED phase=\(phase)")
                fflush(stdout)
                exitCode = 1
            }
        }
        exit(exitCode)
    }
}
