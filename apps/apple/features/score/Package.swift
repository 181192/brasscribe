// swift-tools-version:6.2
// Verovio-backed notation. Needs apps/apple/Frameworks/Verovio.xcframework, built by
// apps/apple/scripts/build-verovio.sh (not committed; LGPL-3.0 dynamic framework).
import PackageDescription

let package = Package(
    name: "NotationKit",
    platforms: [.macOS(.v26), .iOS(.v26)],
    products: [.library(name: "NotationKit", targets: ["NotationKit"])],
    dependencies: [.package(path: "../../services")],
    targets: [
        .binaryTarget(name: "Verovio", path: "../../Frameworks/Verovio.xcframework"),
        .target(name: "NotationKit", dependencies: [
            "Verovio",
            .product(name: "ScoreKit", package: "services"),
            .product(name: "SVGRender", package: "services"),
        ]),
        .testTarget(name: "NotationKitTests", dependencies: ["NotationKit"]),
    ]
)
