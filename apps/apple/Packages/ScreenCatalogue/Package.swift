// swift-tools-version:6.0
// The screen catalogues' checks for the Mac apps (Play's AppTests, Bandroom's Tests): the accessibility tree read
// in-process, the checks on it, the two undocumented hooks they need, and the screenshots. Test code only: no app
// target links it.
import PackageDescription

let package = Package(
    name: "ScreenCatalogue",
    platforms: [.macOS(.v14)],
    products: [.library(name: "ScreenCatalogue", targets: ["ScreenCatalogue"])],
    targets: [
        .target(name: "ScreenCatalogue"),
        .testTarget(name: "ScreenCatalogueTests", dependencies: ["ScreenCatalogue"]),
    ]
)
