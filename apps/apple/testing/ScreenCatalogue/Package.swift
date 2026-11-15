// swift-tools-version:6.2
// The screen catalogues' checks for the Mac apps (Play's AppTests, Bandroom's Tests) and the iPhone (Play's AppTests on
// the simulator): the accessibility tree read in-process, the checks on it, the hooks they need (the tree built in the
// process, Increase Contrast answered in it on the Mac), the rule for when a screenshot counts, and the screenshots.
// Test code only: no app target links it.
import PackageDescription

let package = Package(
    name: "ScreenCatalogue",
    platforms: [.macOS(.v26), .iOS(.v26)],
    products: [.library(name: "ScreenCatalogue", targets: ["ScreenCatalogue"])],
    targets: [
        .target(name: "ScreenCatalogue"),
        .testTarget(name: "ScreenCatalogueTests", dependencies: ["ScreenCatalogue"]),
    ]
)
