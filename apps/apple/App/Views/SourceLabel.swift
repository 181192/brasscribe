import SwiftUI

/// Where a part comes from, as neutral chrome: an icon and the words in a hairline pill, never a
/// colour and never a "?" (the score owns both). A 44 pt button that opens one sentence saying what
/// it means. The same words on every screen, in the PDF and on every platform.
struct SourceLabel: View {
    let kind: PartSourceKind
    /// "Euphonium · Arranged from the band's harmony" in Review's notice.
    var part: String?
    @State private var explaining = false

    var body: some View {
        Button { explaining = true } label: {
            HStack(spacing: Space.s2) {
                Image(systemName: kind.icon.systemName).accessibilityHidden(true)
                Text(part.map { "\($0) · \(kind.title)" } ?? kind.title)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .font(Font.Brasscribe.label)
            .foregroundStyle(Color.Brasscribe.text)
            .padding(.horizontal, Space.s4)
            .frame(minHeight: 44)
            .overlay(Capsule().strokeBorder(Color.Brasscribe.borderStrong, lineWidth: 1))
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(Text(part.map { "\($0.spokenFlats), \(kind.title)" } ?? kind.title))
        .accessibilityHint(Text("Says what this means."))
        .accessibilityIdentifier("sourceLabel")
        .popover(isPresented: $explaining) {
            Text(kind.explanation)
                .font(Font.Brasscribe.body)
                .fixedSize(horizontal: false, vertical: true)
                .frame(idealWidth: 300)
                .padding(Space.s4)
                .presentationCompactAdaptation(.popover)
        }
    }
}

/// The source in the mixer and the part list: the same icon and words, small and not a button (the
/// part view's label explains them).
struct SourceCaption: View {
    let kind: PartSourceKind
    var body: some View {
        Label { Text(kind.title) } icon: { Image(systemName: kind.icon.systemName) }
            .font(Font.Brasscribe.caption)
            .foregroundStyle(Color.Brasscribe.textMuted)
            .labelStyle(.titleAndIcon)
    }
}

/// Above the part view, in one wrapping row: where the part comes from, "Make this my part" for
/// another part, and why your part isn't your seat's own (the lineup has none).
struct PartHeader: View {
    @Bindable var model: PracticeModel

    var body: some View {
        if let id = model.shownPart {
            let mine = id == model.myPart
            let kind = model.partSources[id]
            if mine || kind != nil {
                VStack(alignment: .leading, spacing: Space.s1) {
                    FlowLayout(spacing: Space.s2) {
                        if let kind { SourceLabel(kind: kind) }
                        if !mine {
                            Button { model.makeMine(id) } label: { Text("Make this my part") }
                                .buttonStyle(.plainText)
                                .accessibilityIdentifier("makeMine")
                        }
                    }
                    if mine, let notice = model.seatNotice {
                        HelperLine(systemImage: BrasscribeIcon.info.systemName, text: notice)
                            .accessibilityIdentifier("seatNotice")
                    }
                }
                .padding(.leading, Space.s5)
                // clear of the zoom buttons that float at the score's trailing edge
                .padding(.trailing, 64)
                .padding(.bottom, Space.s2)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}
