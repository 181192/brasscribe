import Foundation

/// Where the downloads are: the one place the Play apps hold a release address. Each product is released on its
/// own, and its newest files are always in its release PRODUCT-latest, so no address names a version.
enum Releases {
    /// The repository's releases.
    static let base = "https://github.com/181192/brasscribe/releases"

    /// Bandroom, the program for the computer: the page of its newest release.
    static let bandroom = URL(string: "\(base)/tag/bandroom-latest")!

    /// An app's own file in its newest release: on a Mac the archive, which the browser downloads. On iPhone and
    /// iPad a release has only an unsigned archive that the device cannot open, so there it is the release's page.
    static func app(product: String, macFile: String) -> URL {
        #if os(macOS)
        URL(string: "\(base)/download/\(product)-latest/\(macFile)")!
        #else
        URL(string: "\(base)/tag/\(product)-latest")!
        #endif
    }
}
