// swift-tools-version:5.9
// The scribe core for Apple platforms: the Rust core as a static XCFramework
// (built by core/scripts/build-all.sh) plus the UniFFI-generated Swift API.
import PackageDescription

let package = Package(
    name: "ScribeCore",
    platforms: [.macOS(.v13), .iOS(.v16)],
    products: [
        .library(name: "ScribeCore", targets: ["ScribeCore"]),
    ],
    targets: [
        .binaryTarget(name: "ScribeFFI", path: "ScribeFFI.xcframework"),
        .target(
            name: "ScribeCore",
            dependencies: ["ScribeFFI"],
            path: "Sources/ScribeCore"
        ),
        .testTarget(
            name: "ScribeCoreTests",
            dependencies: ["ScribeCore"],
            path: "Tests/ScribeCoreTests"
        ),
    ]
)
