import SwiftUI

/// Where a part comes from, as neutral chrome: an icon and the words in a hairline pill, never a
/// colour and never a "?" (the score owns both). A 44 pt button that opens one sentence saying what
/// it means. The same words on every screen, in the PDF and on every platform.
struct SourceLabel: View {
    let kind: PartSourceKind
    /// The small pill of the part row: caption text, the 44 pt target kept by its hit area.
    var compact = false
    @State private var explaining = false

    var body: some View {
        Button { explaining = true } label: {
            HStack(spacing: Space.s2) {
                Image(systemName: kind.icon.systemName).accessibilityHidden(true)
                Text(kind.title)
                    .lineLimit(compact ? 1 : nil)
                    .fixedSize(horizontal: false, vertical: !compact)
            }
            .font(compact ? Font.Brasscribe.caption.weight(.semibold) : Font.Brasscribe.label)
            .foregroundStyle(Color.Brasscribe.text)
            .padding(.horizontal, compact ? Space.s3 : Space.s4)
            .frame(minHeight: compact ? 30 : 44)
            .overlay(Capsule().strokeBorder(Color.Brasscribe.borderStrong, lineWidth: 1))
            .padding(.vertical, compact ? 7 : 0)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(Text(kind.title))
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

/// Above the music: "Make this my part" for another part shown, and the one-line banner when your
/// part isn't your seat's own ("The small band has no 1st Baritone — showing Euphonium"). The banner
/// opens the whole sentence and can be closed; it stays closed for that score.
struct PartHeader: View {
    @Bindable var model: PracticeModel
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var explaining = false

    private var showsNotice: Bool {
        guard model.seatNoticeShort != nil, !model.seatNoticeDismissed else { return false }
        return model.myPart == nil ? model.shownPart == nil : model.shownPart == model.myPart
    }

    var body: some View {
        let makeMine = model.shownPart.map { $0 != model.myPart } ?? false
        if makeMine || showsNotice {
            VStack(alignment: .leading, spacing: Space.s1) {
                if makeMine, let id = model.shownPart {
                    Button { model.makeMine(id) } label: { Text("Make this my part") }
                        .buttonStyle(.plainText)
                        .accessibilityIdentifier("makeMine")
                }
                if showsNotice, let short = model.seatNoticeShort { banner(short) }
            }
            .padding(.horizontal, Space.s5)
            .padding(.bottom, Space.s1)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func banner(_ short: String) -> some View {
        HStack(spacing: Space.s1) {
            Button { explaining = true } label: {
                HStack(spacing: Space.s2) {
                    Image(systemName: BrasscribeIcon.info.systemName).accessibilityHidden(true)
                    Text(short).lineLimit(typeSize >= .accessibility1 ? 2 : 1).minimumScaleFactor(0.7).truncationMode(.tail)
                    Spacer(minLength: 0)
                }
                .font(Font.Brasscribe.caption)
                .foregroundStyle(Color.Brasscribe.text)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(Text(model.seatNotice ?? short))
            .accessibilityIdentifier("seatNotice")
            .popover(isPresented: $explaining) {
                Text(model.seatNotice ?? short)
                    .font(Font.Brasscribe.body)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(idealWidth: 300)
                    .padding(Space.s4)
                    .presentationCompactAdaptation(.popover)
            }
            Button { model.dismissSeatNotice() } label: {
                Image(systemName: BrasscribeIcon.close.systemName).frame(width: 44, height: 44).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .foregroundStyle(Color.Brasscribe.textMuted)
            .accessibilityLabel(Text("Close"))
            .accessibilityIdentifier("seatNoticeClose")
        }
        .padding(.leading, Space.s2)
        .background(Color.Brasscribe.surface, in: RoundedRectangle(cornerRadius: Radius.md))
        .overlay(RoundedRectangle(cornerRadius: Radius.md).strokeBorder(Color.Brasscribe.border))
    }
}
