// swift-tools-version:6.2
import PackageDescription

let package = Package(
    name: "AudioCapture",
    platforms: [.macOS(.v26)],
    products: [
        .library(name: "AudioCapture", targets: ["AudioCapture"]),
        .executable(name: "scribe-capture", targets: ["scribe-capture"]),
    ],
    targets: [
        .target(name: "AudioCapture", swiftSettings: [.swiftLanguageMode(.v5)]),
        .executableTarget(name: "scribe-capture", dependencies: ["AudioCapture"],
                          swiftSettings: [.swiftLanguageMode(.v5)]),
        .testTarget(name: "AudioCaptureTests", dependencies: ["AudioCapture"]),
    ]
)
