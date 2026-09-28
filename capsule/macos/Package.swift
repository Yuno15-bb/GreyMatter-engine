// swift-tools-version:6.0
// The capsule as a native macOS app (see README.md). Built by install.sh with
// `swift build -c release`; no dependency, nothing downloaded.
import PackageDescription

let package = Package(
    name: "Capsule",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(name: "Capsule", path: "Sources/Capsule",
                          swiftSettings: [.swiftLanguageMode(.v5)]),
    ]
)
