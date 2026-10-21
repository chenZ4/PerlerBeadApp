import AppKit

/// 编辑部风格内置素材加载。
///
/// 需同时支持三种运行方式：
/// 1) SwiftPM（swift run / swift build）：资源在 Bundle.module；
/// 2) XcodeGen 生成的普通 app target（xcodegen generate）：资源在 Bundle.main；
/// 3) 离屏 harness / 源码树调试：#filePath 向上回溯到仓库根再找 Resources。
///
/// 注意：不能直接用 Bundle.module —— XcodeGen 的普通 target 没有这个符号，
/// 会编译失败；因此用 #if SWIFT_PACKAGE 隔离。
enum EditorialAssets {

    /// 开始页封面大图（4:3）：整块左侧背景，左上清晰照片对角过渡到右下拼豆。
    static var heroPhotoToBeadsCover: NSImage? {
        loadImage("hero_photo_to_beads_cover", ext: "jpg")
    }

    static func loadImage(_ name: String, ext: String) -> NSImage? {
        // 1) QA/CI 显式指定
        if let p = ProcessInfo.processInfo.environment["PERLER_HERO_PATH"],
           !p.isEmpty, let img = NSImage(contentsOfFile: p) {
            return img
        }

        // 2) SwiftPM 资源包
        #if SWIFT_PACKAGE
        if let url = Bundle.module.url(forResource: name, withExtension: ext),
           let img = NSImage(contentsOf: url) {
            return img
        }
        #endif

        // 3) Xcode app target 的 Copy Bundle Resources
        if let url = Bundle.main.url(forResource: name, withExtension: ext),
           let img = NSImage(contentsOf: url) {
            return img
        }

        // 4) 源码树回退（swift run / 离屏 harness / 未打包调试）
        let fm = FileManager.default
        var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        for _ in 0..<9 {
            let candidates = [
                dir.appendingPathComponent("Resources/\(name).\(ext)"),
                dir.appendingPathComponent("app/Sources/PerlerApp/Resources/\(name).\(ext)"),
                dir.appendingPathComponent("Sources/PerlerApp/Resources/\(name).\(ext)"),
            ]
            for c in candidates where fm.fileExists(atPath: c.path) {
                if let img = NSImage(contentsOf: c) { return img }
            }
            let parent = dir.deletingLastPathComponent()
            if parent.path == dir.path { break }
            dir = parent
        }
        return nil
    }
}
