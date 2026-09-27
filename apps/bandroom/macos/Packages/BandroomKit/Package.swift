// swift-tools-version: 6.0
// Bandroom's logic without UI: engine client, supervisor, status polling, pairing, host health.
import PackageDescription

let package = Package(
    name: "BandroomKit",
    defaultLocalization: "en",
    platforms: [.macOS(.v14)],
    products: [.library(name: "BandroomKit", targets: ["BandroomKit"])],
    targets: [
        .target(name: "BandroomKit", linkerSettings: [.linkedFramework("SystemConfiguration"), .linkedFramework("IOKit")]),
        .testTarget(name: "BandroomKitTests", dependencies: ["BandroomKit"]),
    ]
)
