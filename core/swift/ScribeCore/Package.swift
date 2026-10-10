// swift-tools-version:5.9
// brasscribe core for Apple platforms: the Rust core as a static XCFramework
// (built by core/scripts/build-all.sh) plus the UniFFI-generated Swift API.
import PackageDescription

let package = Package(
    name: "BrasscribeCore",
    platforms: [.macOS(.v13), .iOS(.v16)],
    products: [
        .library(name: "BrasscribeCore", targets: ["BrasscribeCore"]),
    ],
    targets: [
        .binaryTarget(name: "BrasscribeFFI", path: "BrasscribeFFI.xcframework"),
        .target(
            name: "BrasscribeCore",
            dependencies: ["BrasscribeFFI"],
            path: "Sources/BrasscribeCore"
        ),
        .testTarget(
            name: "BrasscribeCoreTests",
            dependencies: ["BrasscribeCore"],
            path: "Tests/BrasscribeCoreTests"
        ),
    ]
)
