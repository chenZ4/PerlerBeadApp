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

    // U4. 网格输入实时联动上屏：改宽不回车，高框逐键刷新
    // （macOS SwiftUI TextField 不重绘缺陷的桥接修复回归）
    func testGridLinkageRefreshesUI() throws {
        let app = launchApp()
        XCTAssertTrue(waitForSetup(app))
        // 切到固定比例 1:1（该模式下宽=高，断言明确）
        let ratioPopup = selectRatio(app, from: "原始比例", to: "1:1")

        let wField = app.textFields.matching(
            NSPredicate(format: "placeholderValue == '宽 (颗)'")).firstMatch
        let hField = app.textFields.matching(
            NSPredicate(format: "placeholderValue == '高 (颗)'")).firstMatch
        XCTAssertTrue(wField.waitForExistence(timeout: 5))
        XCTAssertTrue(hField.waitForExistence(timeout: 5))

        // 聚焦宽框 → 全选 → 输入，全程不按回车
        wField.click()
        wField.doubleClick()
        wField.typeKey("a", modifierFlags: .command)
        wField.typeText("6")
        XCTAssertEqual(hField.value as? String, "6",
                       "输入第一个字符后高框应立即联动上屏")
        wField.typeText("0")
        XCTAssertEqual(hField.value as? String, "60",
                       "第二个字符后仍应逐键联动（无回车）")

        // U6 回归：切换比例立即按新比例重联动（1:1 的 60 → 4:3 的高 45）
        selectRatio(app, from: "1:1", to: "4:3")
        XCTAssertEqual(hField.value as? String, "45",
                       "切到 4:3 后应按宽 60 立即重联动高=45")
        _ = ratioPopup
        app.terminate()
    }

    // U5. 原始比例 + 已选图：按源图比例实时联动（模板 7×10 → aspect 0.7）
    func testOriginalRatioLinksByTemplateAspect() throws {
        let app = launchApp()
        XCTAssertTrue(waitForSetup(app))
        guard engineAvailable(app) else { throw XCTSkip("无 Python 引擎环境") }
        loadTemplate(app, name: "草莓")

        let wField = app.textFields.matching(
            NSPredicate(format: "placeholderValue == '宽 (颗)'")).firstMatch
        let hField = app.textFields.matching(
            NSPredicate(format: "placeholderValue == '高 (颗)'")).firstMatch
        XCTAssertTrue(wField.waitForExistence(timeout: 5))
        // 模板加载后默认宽高 7×10；改宽 20 → 高 = round(20×10/7) = 29
        wField.click()
        wField.doubleClick()
        wField.typeKey("a", modifierFlags: .command)
        wField.typeText("20")
        XCTAssertEqual(hField.value as? String, "29",
                       "原始比例应按模板 7:10 实时联动高=29，实际 \(hField.value ?? "nil")")
        app.terminate()
    }

    // U7. 回车提交后继续编辑仍联动（提交/回声状态不破坏后续输入）
    func testLinkageSurvivesSubmitAndRetype() throws {
        let app = launchApp()
        XCTAssertTrue(waitForSetup(app))
        selectRatio(app, from: "原始比例", to: "1:1")
        let wField = app.textFields.matching(
            NSPredicate(format: "placeholderValue == '宽 (颗)'")).firstMatch
        let hField = app.textFields.matching(
            NSPredicate(format: "placeholderValue == '高 (颗)'")).firstMatch
        XCTAssertTrue(wField.waitForExistence(timeout: 5))

        wField.click()
        wField.doubleClick()
        wField.typeKey("a", modifierFlags: .command)
        wField.typeText("9")
        XCTAssertEqual(hField.value as? String, "9")
        wField.typeKey("\r", modifierFlags: [])   // 回车提交（规范化 + 联动）
        XCTAssertEqual(hField.value as? String, "9", "回车提交后联动值保持")

        wField.typeKey("a", modifierFlags: .command)
        wField.typeText("12")
        XCTAssertEqual(hField.value as? String, "12",
                       "回车后继续输入仍应实时联动")
        app.terminate()
    }

    // MARK: - 选择器辅助

    /// 把比例下拉从 currentValue 切到 target，返回该 popup
    @discardableResult
    private func selectRatio(_ app: XCUIApplication, from currentValue: String,
                             to target: String) -> XCUIElement {
        let popup = app.popUpButtons.matching(
            NSPredicate(format: "value == %@", currentValue)).firstMatch
        XCTAssertTrue(popup.waitForExistence(timeout: 15), "比例选择器未出现")
        popup.click()
        let item = app.menuItems.matching(
            NSPredicate(format: "title == %@ OR label == %@", target, target)).firstMatch
        XCTAssertTrue(item.waitForExistence(timeout: 5), "比例菜单未找到 \(target)")
        item.click()
        return popup
    }

    /// 打开模板菜单并选择名称含 name 的模板
    private func loadTemplate(_ app: XCUIApplication, name: String) {
        let tplPopup = app.popUpButtons.matching(
            NSPredicate(format: "value == '自定义'")).firstMatch
        XCTAssertTrue(tplPopup.waitForExistence(timeout: 20), "模板选择器未出现")
        tplPopup.click()
        let item = app.menuItems.matching(
            NSPredicate(format: "title CONTAINS %@ OR label CONTAINS %@",
                        name, name)).firstMatch
        XCTAssertTrue(item.waitForExistence(timeout: 5), "模板菜单未找到 \(name)")
        item.click()
        // 等模板加载：模板 Picker 值不再等于「自定义」
        let deadline = Date().addingTimeInterval(20)
        while Date() < deadline && tplPopup.value as? String == "自定义" {
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        }
    }
}
