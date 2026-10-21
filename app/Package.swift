// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "PerlerApp",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "PerlerApp",
            path: "Sources/PerlerApp",
            resources: [.process("Resources")],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .testTarget(
            name: "PerlerAppTests",
            dependencies: ["PerlerApp"],
            path: "Tests/PerlerAppTests",
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
    ]
)
