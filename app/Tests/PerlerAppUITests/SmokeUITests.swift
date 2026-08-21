import XCTest

/// 真实 UI 层冒烟（XCUITest）：VM 层测不到的点击/拖拽/键盘路径。
/// 前提：`xcodegen generate` 生成工程后经 xcodebuild/Xcode 运行。
/// 引擎依赖：runner/本机需有可用 Python（PERLER_PYTHON 或 conda 默认路径），
/// 无引擎时相关用例 XCTSkip 而非失败。
///
/// 选择器备忘（实测视图树得出）：
/// - SwiftUI Text 的文本在 accessibility 的 **value** 上，不在 label
/// - 模板 Picker 初始值为「自定义」，按 value 定位；菜单项按 title 匹配
final class SmokeUITests: XCTestCase {

    private func launchApp() -> XCUIApplication {
        let app = XCUIApplication()
        // 把测试进程的 PERLER_PYTHON 透传给被测 app（Engine.findPython 优先读它）
        if let py = ProcessInfo.processInfo.environment["PERLER_PYTHON"], !py.isEmpty {
            app.launchEnvironment["PERLER_PYTHON"] = py
        }
        app.launch()
        return app
    }

    /// 状态栏出现引擎就绪/未找到 Python 任一即视为启动流程完成（文本在 value 上）
    private func waitForSetup(_ app: XCUIApplication, timeout: TimeInterval = 30) -> Bool {
        let ready = app.staticTexts.matching(
            NSPredicate(format: "value CONTAINS '引擎就绪'")).firstMatch
        let noPy = app.staticTexts.matching(
            NSPredicate(format: "value CONTAINS '未找到 Python'")).firstMatch
        return ready.waitForExistence(timeout: timeout)
            || noPy.waitForExistence(timeout: 1)
    }

    private func engineAvailable(_ app: XCUIApplication) -> Bool {
        !app.staticTexts.matching(
            NSPredicate(format: "value CONTAINS '未找到 Python'")).firstMatch.exists
    }

    // U1. 启动不崩溃 + 引擎初始化流程走完
    func testLaunchAndEngineSetup() {
        let app = launchApp()
        XCTAssertTrue(waitForSetup(app), "30s 内未见到引擎初始化结果")
        XCTAssertEqual(app.state, .runningForeground)
        app.terminate()
    }

    // U2. 选模板 → 点生成 → 预览出图（真实 E2E：SwiftUI→VM→引擎子进程→回显）
    func testTemplateGenerateEndToEnd() throws {
        let app = launchApp()
        XCTAssertTrue(waitForSetup(app))
        guard engineAvailable(app) else {
            throw XCTSkip("无 Python 引擎环境，跳过 E2E")
        }
        // 模板 Picker 初始值「自定义」；等模板列表加载完成（该 Popup 出现）
        let tplPopup = app.popUpButtons.matching(
            NSPredicate(format: "value == '自定义'")).firstMatch
        XCTAssertTrue(tplPopup.waitForExistence(timeout: 20), "模板选择器未出现")

        // 未选图时「生成」应禁用（参数守卫的 UI 表现）
        let generateBtn = app.buttons["生成"]
        XCTAssertTrue(generateBtn.waitForExistence(timeout: 5))
        XCTAssertFalse(generateBtn.isEnabled, "未选图片时生成按钮应禁用")

        // 打开模板菜单选「爱心」
        tplPopup.click()
        let menuItem = app.menuItems.matching(
            NSPredicate(format: "title CONTAINS '爱心' OR label CONTAINS '爱心'")).firstMatch
        XCTAssertTrue(menuItem.waitForExistence(timeout: 5), "模板菜单中未找到爱心")
        menuItem.click()

        // 模板加载后生成按钮变为可用
        let deadline = Date().addingTimeInterval(20)
        while Date() < deadline && !generateBtn.isEnabled {
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        }
        XCTAssertTrue(generateBtn.isEnabled, "模板加载后生成按钮应可用")
        generateBtn.click()

        // 状态栏出现「完成：…」（文本在 value 上），60s 上限
        let done = app.staticTexts.matching(
            NSPredicate(format: "value CONTAINS '完成：'")).firstMatch
        XCTAssertTrue(done.waitForExistence(timeout: 60), "生成未在 60s 内完成")
        app.terminate()
    }

    // U3. 预览区连续拖拽不崩溃（偏移累加修复的 UI 级回归）
    func testPreviewDragDoesNotCrash() throws {
        let app = launchApp()
        XCTAssertTrue(waitForSetup(app))
        guard engineAvailable(app) else {
            throw XCTSkip("无 Python 引擎环境，跳过拖拽冒烟")
        }
        let window = app.windows.firstMatch
        XCTAssertTrue(window.waitForExistence(timeout: 10))
        let start = window.coordinate(withNormalizedOffset: CGVector(dx: 0.7, dy: 0.5))
        // 无图空预览态下拖拽也应安全
        for dx in [0.1, -0.15, 0.05] {
            start.withOffset(CGVector(dx: dx * 300, dy: 0))
                .press(forDuration: 0.05, thenDragTo: start)
        }
        XCTAssertEqual(app.state, .runningForeground, "连续拖拽后 app 应存活")
        app.terminate()
    }
}
