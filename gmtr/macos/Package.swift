// swift-tools-version:5.9
// The GMTR map as a native macOS app: a window around the map, no browser, no Electron.
import PackageDescription

let package = Package(
    name: "GreyMatter",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(name: "GreyMatter", path: "Sources/GreyMatter"),
    ]
)
