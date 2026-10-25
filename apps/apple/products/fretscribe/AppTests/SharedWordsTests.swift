import Foundation
import Testing

/// The screens every Play app shares (features/play) say their words through each product's catalog: their keys name
/// no product, and every one, interpolated or not, has Fretscribe's bokmål, and neither its English nor its bokmål
/// names Brasscribe. The desktop program is Bandroom.
@Test func everySharedWordIsInFretscribesOwnWords() throws {
    let here = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let problems = try SharedWords.problems(shared: here.appending(path: "../../../features/play").standardizedFileURL,
                                            catalog: here.appending(path: "../App/Localizable.xcstrings").standardizedFileURL,
                                            notOurs: ["Brasscribe"])
    #expect(problems.isEmpty, "\(problems.joined(separator: "\n"))")
}
