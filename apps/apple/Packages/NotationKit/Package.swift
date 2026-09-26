// swift-tools-version:6.0
// Verovio-backed notation. Needs apps/apple/Frameworks/Verovio.xcframework, built by
// apps/apple/scripts/build-verovio.sh (not committed; LGPL-3.0 dynamic framework).
import PackageDescription

let package = Package(
    name: "NotationKit",
    platforms: [.macOS(.v15), .iOS(.v18)],
    products: [.library(name: "NotationKit", targets: ["NotationKit"])],
    dependencies: [.package(path: "../BrasscribeKit")],
    targets: [
        .binaryTarget(name: "Verovio", path: "../../Frameworks/Verovio.xcframework"),
        .target(name: "NotationKit", dependencies: [
            "Verovio",
            .product(name: "ScoreKit", package: "BrasscribeKit"),
            .product(name: "SVGRender", package: "BrasscribeKit"),
        ]),
        .testTarget(name: "NotationKitTests", dependencies: ["NotationKit"]),
    ]
)
