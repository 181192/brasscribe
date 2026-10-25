// swift-tools-version:6.2
// The tab, engraved by alphaTab in a web view: the page, what it is told (the song, the colours, where the cursor
// stands) and what it answers (where its bars are). alphaTab is not committed: scripts/fetch-alphatab.sh puts the
// pinned release into Sources/TabKit/Resources/page/alphatab before a build.
import PackageDescription

let package = Package(
    name: "TabKit",
    platforms: [.macOS(.v26), .iOS(.v26)],
    products: [.library(name: "TabKit", targets: ["TabKit"])],
    targets: [
        .target(name: "TabKit", resources: [.copy("Resources/page")]),
        .testTarget(name: "TabKitTests", dependencies: ["TabKit"]),
    ]
)
