// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "AudioCapture",
    platforms: [.macOS(.v15)],
    products: [
        .library(name: "AudioCapture", targets: ["AudioCapture"]),
        .executable(name: "brasscribe-capture", targets: ["brasscribe-capture"]),
    ],
    targets: [
        .target(name: "AudioCapture", swiftSettings: [.swiftLanguageMode(.v5)]),
        .executableTarget(name: "brasscribe-capture", dependencies: ["AudioCapture"],
                          swiftSettings: [.swiftLanguageMode(.v5)]),
        .testTarget(name: "AudioCaptureTests", dependencies: ["AudioCapture"]),
    ]
)
