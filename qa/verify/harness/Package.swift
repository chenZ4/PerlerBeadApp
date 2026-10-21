// swift-tools-version: 6.0
// 独立验证离屏 harness（自动生成；只依赖系统 SwiftUI/AppKit，不引入第三方依赖）
import PackageDescription

let package = Package(
    name: "ZoomProbe",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "ZoomProbe",
            path: "Sources",
            resources: [.process("AppCopy/Resources")],
            swiftSettings: [.swiftLanguageMode(.v5)]
        )
    ]
)
