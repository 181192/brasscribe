// swift-tools-version:6.0
// Pure logic and audio for Brasscribe Play. Nothing here needs Verovio, a sound font
// or the network, so `swift test` runs anywhere.
import PackageDescription

let package = Package(
    name: "BrasscribeKit",
    defaultLocalization: "en",
    platforms: [.macOS(.v15), .iOS(.v18)],
    products: [
        .library(name: "ScoreKit", targets: ["ScoreKit"]),
        .library(name: "TranscriptionKit", targets: ["TranscriptionKit"]),
        .library(name: "PlaybackKit", targets: ["PlaybackKit"]),
        .library(name: "SVGRender", targets: ["SVGRender"]),
    ],
    targets: [
        .target(name: "ScoreKit"),
        .target(name: "TranscriptionKit", dependencies: ["ScoreKit"]),
        .target(name: "PlaybackKit", dependencies: ["ScoreKit"], swiftSettings: [.swiftLanguageMode(.v5)]),
        .target(name: "SVGRender"),
        .testTarget(name: "ScoreKitTests", dependencies: ["ScoreKit"], resources: [.process("Resources")]),
        .testTarget(name: "TranscriptionKitTests", dependencies: ["TranscriptionKit"]),
        .testTarget(name: "PlaybackKitTests", dependencies: ["PlaybackKit"]),
        .testTarget(name: "SVGRenderTests", dependencies: ["SVGRender"], resources: [.copy("Resources")]),
    ]
)
