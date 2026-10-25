import SwiftUI

/// At the top of a draft's score: what a draft is, and "Make the full score" on the computer from the
/// same recording when the computer is there (a secondary button: the round Play stays the primary).
struct DraftNotice: View {
    @Environment(AppModel.self) private var app
    let piece: Piece

    /// The notice's words, and whether the full score can be made now.
    nonisolated static func words(computerThere: Bool) -> (text: String, action: String?, hint: String?) {
        (String(localized: "A quick draft made on this device. Your computer makes a better score, and results on the device can differ slightly from the computer's."),
         computerThere ? String(localized: "Make the full score") : nil,
         computerThere ? nil : String(localized: "Open Brasscribe on your computer to make the full score from the same recording."))
    }

    var body: some View {
        let there = app.computerThere && piece.originalURL != nil
        let w = Self.words(computerThere: there)
        VStack(alignment: .leading, spacing: Space.s3) {
            NoticeBox(systemImage: BrasscribeIcon.info.systemName, text: [w.text, w.hint].compactMap { $0 }.joined(separator: " "))
                .accessibilityIdentifier("draftNotice")
            if let action = w.action {
                Button { app.makeFullScore(from: piece) } label: {
                    Label(action, systemImage: BrasscribeIcon.computer.systemName)
                }
                .buttonStyle(SecondaryButtonStyle(minHeight: 44))
                .accessibilityIdentifier("makeFullScore")
            }
        }
        .padding(.horizontal, Space.s5)
        .padding(.bottom, Space.s2)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
